"""Migrate a GDS IDEA CDK repo from manual version bumps to auto-tagging.

Usage:
    uvx --from git+https://github.com/co-cddo/gds-idea-migrate-auto-version migrate

Run this from the root of the repo you want to migrate.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import tomlkit


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RELEASE_WORKFLOW = """\
name: Release

on:
  push:
    branches: [dev]

permissions:
  contents: write
  pull-requests: read

jobs:
  release:
    uses: co-cddo/gds-idea-workflows-catalogue/.github/workflows/auto_tag_release.yml@main
    secrets: inherit
"""

BRANCH_NAME = "auto-version-bump"

COMMIT_MESSAGE = """\
switch to hatch-vcs and auto-tag release on merge to dev

- Replace uv-build backend with hatchling + hatch-vcs for tag-based versioning
- Add release.yml workflow calling auto_tag_release from workflow catalogue
- Disable ci_pyproject_version check (no longer needed with VCS versioning)
- Add generated _version.py to .gitignore

Version is now derived from git tags automatically. On merge to dev,
a new patch tag is created by default. Use bump:minor or bump:major
PR labels for larger version increments.\
"""

PR_BODY = """\
## What

Replaces manual version bumping with automatic tag-based versioning.

## Changes

- **Build backend**: `uv-build` -> `hatchling` + `hatch-vcs` (version derived from git tags)
- **New workflow**: `release.yml` calls `auto_tag_release.yml` from the workflow catalogue on push to `dev`
- **Disabled**: `ci_pyproject_version` check (no hardcoded version to check)
- **`.gitignore`**: Added `src/<package>/_version.py` (auto-generated at build time)

## How it works after merge

1. PRs no longer need a manual version bump
2. On merge to `dev`, a new git tag is auto-created:
   - Default: patch bump (e.g. `v0.1.14` -> `v0.1.15`)
   - Label PR `bump:minor` for minor bump
   - Label PR `bump:major` for major bump
3. `importlib.metadata.version()` continues to work -- version comes from package metadata at build time

## Notes

- A seed tag has been pushed to establish the version history
- `uv` remains the package manager -- only the build backend changed
- Other branches can rebase on `dev` after this merges and drop their version bump commits\
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess command."""
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def fatal(msg: str) -> None:
    """Print an error and exit."""
    print(f"\n  ERROR: {msg}\n", file=sys.stderr)
    sys.exit(1)


def info(msg: str) -> None:
    """Print an info message."""
    print(f"  {msg}")


def header(msg: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Precondition checks
# ---------------------------------------------------------------------------


def check_prerequisites() -> None:
    """Verify the environment is ready for migration."""
    # Must be in a git repo
    if not Path(".git").is_dir():
        fatal("Not a git repository. Run this from the root of the repo you want to migrate.")

    # pyproject.toml must exist
    if not Path("pyproject.toml").is_file():
        fatal("No pyproject.toml found in the current directory.")

    # Must have a clean working tree
    result = run(["git", "status", "--porcelain"])
    if result.stdout.strip():
        fatal("Working tree is not clean. Please commit or stash your changes first.")

    # gh CLI must be available
    result = run(["which", "gh"], check=False)
    if result.returncode != 0:
        fatal("GitHub CLI (gh) is not installed. Install it: https://cli.github.com/")

    # uv must be available
    result = run(["which", "uv"], check=False)
    if result.returncode != 0:
        fatal("uv is not installed. Install it: https://docs.astral.sh/uv/")

    # origin/dev must exist
    run(["git", "fetch", "origin", "dev"], check=False)
    result = run(["git", "rev-parse", "origin/dev"], check=False)
    if result.returncode != 0:
        fatal("origin/dev branch not found. This script expects a 'dev' branch on the remote.")


def check_not_already_migrated() -> None:
    """Check if the repo has already been migrated."""
    pyproject = tomlkit.parse(Path("pyproject.toml").read_text())

    # Check if already using hatch-vcs
    hatch_version = pyproject.get("tool", {}).get("hatch", {}).get("version", {})
    if hatch_version.get("source") == "vcs":
        fatal("This repo already uses hatch-vcs. Nothing to do.")

    # Check if release.yml already exists
    if Path(".github/workflows/release.yml").is_file():
        fatal(".github/workflows/release.yml already exists. Already migrated?")


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------


def detect_package_info() -> tuple[str, str, str, str]:
    """Detect package name, module name, current version, and source layout.

    Returns:
        (package_name, module_name, current_version, source_dir)
        source_dir is "src" if using src layout, or "." if flat layout
    """
    pyproject = tomlkit.parse(Path("pyproject.toml").read_text())

    # Package name from [project]
    project = pyproject.get("project", {})
    package_name = project.get("name", "")
    if not package_name:
        fatal("Could not find project name in pyproject.toml")

    # Current version
    current_version = project.get("version", "")
    if not current_version:
        fatal("Could not find a hardcoded version in pyproject.toml. Is it already dynamic?")

    # Module name and source dir: check [tool.uv.build-backend] first
    uv_backend = pyproject.get("tool", {}).get("uv", {}).get("build-backend", {})
    module_name = uv_backend.get("module-name", "")
    source_dir = uv_backend.get("source-dir", "")

    if not module_name:
        # Infer from package name (replace hyphens with underscores)
        module_name = package_name.replace("-", "_")

    # Detect source layout
    if source_dir:
        # Explicitly configured (e.g. source-dir = "src")
        module_path = Path(source_dir) / module_name
    elif (Path("src") / module_name).is_dir():
        # Standard src layout
        source_dir = "src"
        module_path = Path("src") / module_name
    elif Path(module_name).is_dir():
        # Flat layout (module at root)
        source_dir = "."
        module_path = Path(module_name)
    else:
        fatal(
            f"Cannot find module '{module_name}' in either src/{module_name}/ or {module_name}/.\n"
            f"  Check that the module directory exists and matches the package name."
        )

    if not module_path.is_dir():
        fatal(f"Expected module directory {module_path} does not exist.")

    return package_name, module_name, current_version, source_dir


def edit_pyproject(module_name: str, source_dir: str) -> None:
    """Edit pyproject.toml to use hatchling + hatch-vcs."""
    pyproject = tomlkit.parse(Path("pyproject.toml").read_text())

    # Build the module path for config
    if source_dir and source_dir != ".":
        version_file = f"{source_dir}/{module_name}/_version.py"
        packages_entry = f"{source_dir}/{module_name}"
    else:
        version_file = f"{module_name}/_version.py"
        packages_entry = module_name

    # 1. Replace build-system
    pyproject["build-system"] = tomlkit.table()
    pyproject["build-system"]["requires"] = ["hatchling", "hatch-vcs"]
    pyproject["build-system"]["build-backend"] = "hatchling.build"

    # 2. Remove [tool.uv.build-backend] if it exists
    tool = pyproject.get("tool", {})
    uv_tool = tool.get("uv", {})
    if "build-backend" in uv_tool:
        del uv_tool["build-backend"]
        # If [tool.uv] is now empty (no other keys), we could remove it
        # but it likely has other things like [tool.uv.sources], so leave it

    # 3. Make version dynamic
    project = pyproject["project"]
    if "version" in project:
        del project["version"]
    # Add dynamic field
    if "dynamic" not in project:
        # Insert dynamic after name
        items = list(project.items())
        new_project = tomlkit.table()
        for key, value in items:
            new_project[key] = value
            if key == "name":
                new_project["dynamic"] = ["version"]
        pyproject["project"] = new_project
    else:
        if "version" not in project["dynamic"]:
            project["dynamic"].append("version")

    # 4. Add [tool.hatch.*] sections
    if "hatch" not in pyproject.get("tool", {}):
        if "tool" not in pyproject:
            pyproject["tool"] = tomlkit.table()

    # Ensure tool.hatch exists
    tool = pyproject["tool"]
    if "hatch" not in tool:
        tool["hatch"] = tomlkit.table()
        tool["hatch"].is_super_table = True

    hatch = tool["hatch"]

    # [tool.hatch.version]
    if "version" not in hatch:
        hatch["version"] = tomlkit.table()
    hatch["version"]["source"] = "vcs"

    # [tool.hatch.build] -> [tool.hatch.build.hooks.vcs]
    if "build" not in hatch:
        hatch["build"] = tomlkit.table()
        hatch["build"].is_super_table = True

    build = hatch["build"]
    if "hooks" not in build:
        build["hooks"] = tomlkit.table()
        build["hooks"].is_super_table = True

    hooks = build["hooks"]
    if "vcs" not in hooks:
        hooks["vcs"] = tomlkit.table()
    hooks["vcs"]["version-file"] = version_file

    # [tool.hatch.build.targets.wheel]
    if "targets" not in build:
        build["targets"] = tomlkit.table()
        build["targets"].is_super_table = True

    targets = build["targets"]
    if "wheel" not in targets:
        targets["wheel"] = tomlkit.table()
    targets["wheel"]["packages"] = [packages_entry]

    # Write back
    Path("pyproject.toml").write_text(tomlkit.dumps(pyproject))


def edit_gitignore(module_name: str, source_dir: str) -> None:
    """Add _version.py to .gitignore."""
    gitignore_path = Path(".gitignore")

    if source_dir and source_dir != ".":
        entry = f"{source_dir}/{module_name}/_version.py"
    else:
        entry = f"{module_name}/_version.py"

    if gitignore_path.is_file():
        content = gitignore_path.read_text()
        if entry in content:
            info(f".gitignore already contains {entry}")
            return
        # Append
        if not content.endswith("\n"):
            content += "\n"
        content += f"\n# Version file (generated by hatch-vcs)\n{entry}\n"
        gitignore_path.write_text(content)
    else:
        gitignore_path.write_text(f"# Version file (generated by hatch-vcs)\n{entry}\n")


def edit_pr_workflow() -> None:
    """Turn off run-version-check in the PR workflow."""
    workflow_path = Path(".github/workflows/ci_pr_cdk_app.yml")

    if not workflow_path.is_file():
        info("No ci_pr_cdk_app.yml found - skipping version check edit")
        return

    content = workflow_path.read_text()

    # Find the ci_pyproject_version job and flip run-version-check to false
    # Pattern: the job that calls ci_pyproject_version.yml with run-version-check: true
    new_content = re.sub(
        r"(ci_pyproject_version:.*?run-version-check:\s*)true",
        r"\1false",
        content,
        flags=re.DOTALL,
    )

    if new_content == content:
        info("ci_pyproject_version already has run-version-check: false (or not found)")
    else:
        workflow_path.write_text(new_content)


def create_release_workflow() -> None:
    """Create .github/workflows/release.yml."""
    workflow_dir = Path(".github/workflows")
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "release.yml").write_text(RELEASE_WORKFLOW)


def regenerate_lock() -> None:
    """Run uv lock to update the lock file."""
    result = run(["uv", "lock"], check=False)
    if result.returncode != 0:
        info("Warning: uv lock failed. You may need to run it manually.")
        if result.stderr:
            info(f"  {result.stderr.strip()}")


def create_seed_tag(version: str) -> None:
    """Create a seed tag on origin/dev."""
    tag = f"v{version}"

    # Check if tag already exists on remote
    result = run(["git", "ls-remote", "--tags", "origin", tag], check=False)
    if result.stdout.strip():
        info(f"Tag {tag} already exists on remote - skipping tag creation")
        return

    # Create tag on origin/dev
    run(["git", "tag", tag, "origin/dev"])
    info(f"Created tag {tag} on origin/dev")


def commit_and_pr() -> None:
    """Commit changes, push, and create PR."""
    # Stage all changes
    run(["git", "add", "-A"])

    # Commit
    run(["git", "commit", "-m", COMMIT_MESSAGE])

    # Push branch
    result = run(["git", "push", "origin", BRANCH_NAME], check=False)
    if result.returncode != 0:
        fatal(f"Failed to push branch: {result.stderr}")

    # Push tag
    tag_result = run(["git", "tag", "--list", "v*"])
    tags = tag_result.stdout.strip().split("\n")
    for tag in tags:
        tag = tag.strip()
        if tag:
            run(["git", "push", "origin", tag], check=False)

    # Create PR
    result = run([
        "gh", "pr", "create",
        "--base", "dev",
        "--head", BRANCH_NAME,
        "--title", "Switch to hatch-vcs and auto-tag release on merge to dev",
        "--body", PR_BODY,
    ], check=False)

    if result.returncode == 0:
        pr_url = result.stdout.strip()
        info(f"PR created: {pr_url}")
    else:
        info(f"Warning: PR creation failed: {result.stderr}")
        info("You can create it manually with: gh pr create --base dev")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the migration script."""
    header("GDS IDEA - Migrate to Auto-Versioning")

    # Preconditions
    info("Checking prerequisites...")
    check_prerequisites()
    check_not_already_migrated()

    # Detect package info
    package_name, module_name, current_version, source_dir = detect_package_info()

    # Compute display paths
    if source_dir and source_dir != ".":
        version_file_path = f"{source_dir}/{module_name}/_version.py"
    else:
        version_file_path = f"{module_name}/_version.py"

    info(f"Package:         {package_name}")
    info(f"Module:          {module_name}")
    info(f"Source layout:   {source_dir + '/' if source_dir != '.' else '(flat)'}")
    info(f"Current version: {current_version}")

    # Show plan
    header("This script will make the following changes")

    info("1. pyproject.toml:")
    info("   - Build backend: uv-build -> hatchling + hatch-vcs")
    info("   - Remove [tool.uv.build-backend] section")
    info(f"   - Remove hardcoded version ({current_version}), add dynamic = [\"version\"]")
    info("   - Add [tool.hatch.version], [tool.hatch.build.hooks.vcs], [tool.hatch.build.targets.wheel]")
    info("")
    info("2. .gitignore:")
    info(f"   - Add {version_file_path}")
    info("")
    info("3. .github/workflows/ci_pr_cdk_app.yml:")
    info("   - Set run-version-check: false on ci_pyproject_version job")
    info("")
    info("4. .github/workflows/release.yml (NEW):")
    info("   - Calls auto_tag_release.yml from workflow catalogue on push to dev")
    info("")
    info("5. uv.lock:")
    info("   - Regenerated to reflect dynamic version")
    info("")
    info("6. Git:")
    info(f"   - Create seed tag v{current_version} on origin/dev")
    info(f"   - Create branch '{BRANCH_NAME}', commit, and push")
    info("   - Create PR targeting dev")
    info("")
    info("After merge, every subsequent merge to dev will auto-create a new patch tag.")
    info("Use PR labels bump:minor or bump:major for larger bumps.")

    # Confirm
    print()
    response = input("  Proceed? [y/N] ").strip().lower()
    if response not in ("y", "yes"):
        info("Aborted.")
        sys.exit(0)

    # Execute
    header("Migrating...")

    # Ensure we're on a fresh branch from origin/dev
    info("Creating branch from origin/dev...")
    # Delete the branch if it already exists locally (e.g. from a previous failed run)
    run(["git", "branch", "-D", BRANCH_NAME], check=False)
    run(["git", "checkout", "-b", BRANCH_NAME, "origin/dev"])

    info("Editing pyproject.toml...")
    edit_pyproject(module_name, source_dir)

    info("Editing .gitignore...")
    edit_gitignore(module_name, source_dir)

    info("Editing PR workflow...")
    edit_pr_workflow()

    info("Creating release.yml...")
    create_release_workflow()

    info("Regenerating uv.lock...")
    regenerate_lock()

    info(f"Creating seed tag v{current_version}...")
    create_seed_tag(current_version)

    info("Committing and creating PR...")
    commit_and_pr()

    # Done
    header("Migration complete!")

    info("Next steps:")
    info("  1. Review and merge the PR")
    info("  2. The next merge to dev will auto-create a new version tag")
    info("  3. Other branches can rebase on dev and drop version bump commits")
    info("")
    info("Version bump labels for PRs:")
    info("  (no label)   -> patch bump (default)")
    info("  bump:minor   -> minor bump")
    info("  bump:major   -> major bump")


if __name__ == "__main__":
    main()
