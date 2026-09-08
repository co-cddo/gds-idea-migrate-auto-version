# gds-idea-migrate-auto-version

One-command migration from manual version bumps to automatic tag-based versioning for GDS IDEA CDK repos.

## Usage

From the root of the repo you want to migrate:

```bash
uvx --from git+https://github.com/co-cddo/gds-idea-migrate-auto-version migrate
```

The script will:

1. Show you exactly what it's going to change
2. Ask for confirmation
3. Make the changes, commit, push, and create a PR

## What it does

| Before | After |
|--------|-------|
| Hardcoded `version = "x.y.z"` in `pyproject.toml` | Version derived from git tags at build time |
| Manual version bump required on every PR | No version editing needed |
| `uv-build` backend | `hatchling` + `hatch-vcs` backend |
| CI fails if you forget to bump | CI doesn't check (nothing to check) |

This is the default path, for repos with a real importable package at the
root (a `src/<module>/` or `<module>/` directory matching the package name
in `pyproject.toml`).

### App-shaped repos (no importable root package)

Some repos' root `pyproject.toml` doesn't describe an installable package at
all -- e.g. a CDK app (`cdk.json`, `app.py`, `stacks/`) whose real runtime
code lives in a separate sibling sub-project with its own `pyproject.toml`
(a Dash/Flask app under `app_src/`, say). There's no module for `hatch-vcs`
to version in that case, and nothing in the repo reads this file's version
at build/runtime either -- its only consumer was the manual-bump check
itself.

The script detects this automatically (no importable module found, and no
explicit `[tool.uv.build-backend]` override says otherwise) and takes a
lighter path instead:

| Before | After |
|--------|-------|
| Hardcoded `version = "x.y.z"` in `pyproject.toml` | Version history lives entirely in git tags / GitHub Releases |
| Manual version bump required on every PR | No version editing needed |
| Build backend unchanged | Build backend unchanged (there's nothing to build) |
| CI fails if you forget to bump | CI doesn't check (nothing to check) |

`pyproject.toml`'s `version` field is kept (PEP 440/`uv` require a
numeric-leading version string to be present, dynamic or not) but replaced
with a static placeholder plus an explanatory comment, e.g.:

```toml
version = "0.0.0+automatic"  # Versioning is automatic via git tags (see .github/workflows/release.yml) -- do not bump manually
```

This does not change how you find out what's actually deployed -- if the
repo already derives that some other way (e.g. a git-SHA-derived env var
baked into the running container), that's untouched.

**Note:** a repo can have `cdk.json` *and* a real importable package at the
same time (e.g. a Lambda deployed via CDK that's also a proper installable
library) -- detection is based on whether a module directory actually
exists, not on whether the repo looks like a CDK app, so that case still
gets the full `hatch-vcs` treatment above.

## After migration

| Action | Result |
|--------|--------|
| Merge a PR to `dev` | Patch bump (e.g. `v0.1.13` -> `v0.1.14`) |
| Add label `bump:minor` before merging | Minor bump (e.g. `v0.1.14` -> `v0.2.0`) |
| Add label `bump:major` before merging | Major bump (e.g. `v0.2.0` -> `v1.0.0`) |

No labels = patch bump by default.

## Prerequisites

- The repo uses the `gds-idea-workflows-catalogue`
- The repo has a `pyproject.toml` with a hardcoded `version` field
- The repo has an `origin/dev` branch
- You have `uv`, `gh` (GitHub CLI), and `git` available
- Your working tree is clean (no uncommitted changes)

## How it works under the hood

1. **`hatch-vcs`** reads the latest `v*` git tag and uses it as the package version at build time
2. **`auto_tag_release.yml`** (from the workflow catalogue) runs on push to `dev`, reads PR labels, increments the version, and creates a new git tag + GitHub Release
3. **`importlib.metadata.version("your_package")`** continues to work - it reads from installed package metadata which hatchling populates from the tag
