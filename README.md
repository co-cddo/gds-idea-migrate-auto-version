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
