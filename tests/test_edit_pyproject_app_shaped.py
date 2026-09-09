"""Tests for the two pyproject.toml edit paths.

`edit_pyproject` (the pre-existing hatch-vcs rewrite for real packages)
is left untested here -- it's unchanged behaviour, already proven by its
use on `gds-idea-app-kit`/`gds-idea-app-auth`/`gds-idea-ai-pqs`. These
tests cover the new `edit_pyproject_app_shaped` path, and confirm the
two paths don't interfere with each other's inputs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from migrate_auto_version.main import (
    APP_VERSION_COMMENT,
    APP_VERSION_PLACEHOLDER,
    edit_pyproject_app_shaped,
)


def test_replaces_the_hardcoded_version_with_the_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "gds-idea-app-measuring-inclusion"
version = "0.1.10"
description = "Add your description here"
""".lstrip()
    )

    edit_pyproject_app_shaped()

    result = (tmp_path / "pyproject.toml").read_text()
    assert f'version = "{APP_VERSION_PLACEHOLDER}"' in result
    assert APP_VERSION_COMMENT in result
    # Everything else is untouched
    assert 'name = "gds-idea-app-measuring-inclusion"' in result
    assert 'description = "Add your description here"' in result


def test_does_not_touch_build_system_or_uv_build_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unlike `edit_pyproject`, this path has no package to version, so it
    must leave any existing build-system config completely alone."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "gds-idea-app-measuring-inclusion"
version = "0.1.10"

[build-system]
requires = ["uv_build"]
build-backend = "uv_build"

[tool.uv]
package = false
""".lstrip()
    )

    edit_pyproject_app_shaped()

    result = (tmp_path / "pyproject.toml").read_text()
    assert 'build-backend = "uv_build"' in result
    assert "hatchling" not in result
    assert "hatch-vcs" not in result
    assert "package = false" in result


def test_placeholder_is_pep440_valid_and_starts_with_a_digit() -> None:
    """`uv`/PEP 440 reject a version string that doesn't start with a
    digit -- confirmed directly against `uv lock` during development.
    This just guards against someone changing the constant to something
    that breaks that again.
    """
    assert APP_VERSION_PLACEHOLDER[0].isdigit()
