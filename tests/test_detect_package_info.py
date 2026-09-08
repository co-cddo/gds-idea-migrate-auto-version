"""Tests for `detect_package_info`'s repo-shape detection.

These are the cases that matter in practice:

- A normal library repo with a `src/<module>/` layout (e.g.
  `gds-idea-app-kit`) -- should be detected as before.
- A flat-layout library repo (`<module>/` at root, no `src/`).
- An app-shaped repo with *no* importable root package (e.g. a
  `gds-idea-app-*` CDK app whose real code lives in a separate
  sub-project) -- should come back as `source_dir=None`, not `fatal()`.
- A repo that's *both* a CDK app *and* a real package (e.g.
  `gds-idea-ai-pqs` -- a Lambda deployed via CDK, but with a real
  `src/pqs/` package and an explicit `module-name` override) -- must
  still be detected as a library, not fall back to the app-shaped path,
  purely because it also happens to have a `cdk.json`. This is why
  detection is based on "does a module directory actually exist",
  not "does this look like a CDK app".
- An explicit `source-dir` override pointing at a directory that
  doesn't exist -- a real misconfiguration, must still be fatal, not
  silently treated as app-shaped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from migrate_auto_version.main import detect_package_info


def _write_pyproject(tmp_path: Path, content: str) -> None:
    (tmp_path / "pyproject.toml").write_text(content)


def test_detects_a_standard_src_layout_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "widget_lib").mkdir(parents=True)
    _write_pyproject(
        tmp_path,
        """
        [project]
        name = "widget-lib"
        version = "1.2.3"
        """,
    )

    package_name, module_name, current_version, source_dir = detect_package_info()

    assert package_name == "widget-lib"
    assert module_name == "widget_lib"
    assert current_version == "1.2.3"
    assert source_dir == "src"


def test_detects_a_flat_layout_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "widget_lib").mkdir()
    _write_pyproject(
        tmp_path,
        """
        [project]
        name = "widget-lib"
        version = "1.2.3"
        """,
    )

    *_rest, source_dir = detect_package_info()

    assert source_dir == "."


def test_honours_an_explicit_module_name_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors gds-idea-ai-pqs: package name doesn't match the module dir name."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "pqs").mkdir(parents=True)
    _write_pyproject(
        tmp_path,
        """
        [project]
        name = "gds-idea-ai-pqs"
        version = "0.3.2"

        [tool.uv.build-backend]
        module-name = "pqs"
        """,
    )

    package_name, module_name, _current_version, source_dir = detect_package_info()

    assert package_name == "gds-idea-ai-pqs"
    assert module_name == "pqs"
    assert source_dir == "src"


def test_a_cdk_app_with_a_real_package_is_detected_as_a_library_not_app_shaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gds-idea-ai-pqs case: has cdk.json AND a real src/pqs/ package.

    Detection must key off "does a module exist", not "is this a CDK
    app" -- otherwise this exact repo would be wrongly routed to the
    app-shaped fallback and lose its real, working hatch-vcs setup.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cdk.json").write_text("{}")
    (tmp_path / "app.py").touch()
    (tmp_path / "src" / "pqs").mkdir(parents=True)
    _write_pyproject(
        tmp_path,
        """
        [project]
        name = "gds-idea-ai-pqs"
        version = "0.3.2"

        [tool.uv.build-backend]
        module-name = "pqs"
        """,
    )

    *_rest, source_dir = detect_package_info()

    assert source_dir == "src"


def test_a_cdk_app_with_no_importable_package_falls_back_to_app_shaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gds-idea-app-measuring-inclusion case: cdk.json, no package."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cdk.json").write_text("{}")
    (tmp_path / "app.py").touch()
    (tmp_path / "stacks").mkdir()
    _write_pyproject(
        tmp_path,
        """
        [project]
        name = "gds-idea-app-measuring-inclusion"
        version = "0.1.10"
        """,
    )

    package_name, _module_name, current_version, source_dir = detect_package_info()

    assert package_name == "gds-idea-app-measuring-inclusion"
    assert current_version == "0.1.10"
    assert source_dir is None


def test_an_explicit_source_dir_override_that_does_not_exist_is_still_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit override is a promise about where to look -- if it's
    wrong, that's a real misconfiguration, not "no package here"."""
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
        [project]
        name = "widget-lib"
        version = "1.2.3"

        [tool.uv.build-backend]
        module-name = "widget_lib"
        source-dir = "lib"
        """,
    )

    with pytest.raises(SystemExit):
        detect_package_info()


def test_missing_project_name_is_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_pyproject(tmp_path, """
        [project]
        version = "1.2.3"
        """)

    with pytest.raises(SystemExit):
        detect_package_info()


def test_missing_version_is_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_pyproject(tmp_path, """
        [project]
        name = "widget-lib"
        """)

    with pytest.raises(SystemExit):
        detect_package_info()
