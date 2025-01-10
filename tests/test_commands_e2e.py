from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path
from tarfile import TarFile
from zipfile import ZipFile

import pytest

from tests.fixtures import TestSetup, module_setups, package_name_of
from tests.helpers import POETRY_VERSION, run_test_app

_logger = logging.getLogger(__name__)


@pytest.mark.parametrize("module_dir", module_setups.keys())
def test_export_locked(fixture_simple_a: Path, tmp_path: Path, module_dir: str) -> None:
    setup = module_setups[module_dir]
    os.chdir(fixture_simple_a / module_dir)

    # export should contain the dependency as a name
    requirements_path = tmp_path / "reqs.txt"
    _out, err = run_test_app(["poetry", "export", "-vvv", "--output", str(requirements_path)])
    assert err == ""
    requirements_content = requirements_path.read_text()
    _logger.info("Resulting requirement file:")
    _logger.info(requirements_content)
    for dep in (setup.deps or []) + (setup.transitive_deps or []):
        fixed_str = f"""{dep.to_pep_508()} ; python_version >= "3.8" and python_version < "4.0\""""
        named_path_str = (
            f"{dep.name} @ {(fixture_simple_a / 'lib-a').as_uri()}"
            " ; python_version >= \"3.8\" and python_version < \"4.0\""
        )
        path_str = f"""-e {(fixture_simple_a / 'lib-a').as_uri()} ; python_version >= "3.8" and python_version < "4.0"""
        if setup.enabled:
            assert fixed_str in requirements_content
            assert named_path_str not in requirements_content
            assert path_str not in requirements_content
        else:
            assert fixed_str not in requirements_content
            assert path_str in requirements_content or named_path_str in requirements_content


@pytest.mark.parametrize("module_dir", module_setups.keys())
def test_ignored_command(fixture_simple_a: Path, tmp_path: Path, module_dir: str) -> None:
    """Running on a completely different command."""
    module_setups[module_dir]
    os.chdir(fixture_simple_a / module_dir)

    # should have no effect on lock file
    _out, err = run_test_app(["poetry", "lock"])
    assert err == ""
    text = (tmp_path / "simple_a" / module_dir / "poetry.lock").read_text()
    _logger.info(text)
    setup = module_setups[module_dir]
    groups_def = """groups = ["main"]\n""" if POETRY_VERSION >= 2 else ""
    for dep in setup.deps or []:
        assert (
            f"""[package]]
name = "{dep.name}"
version = "{dep.version}"
description = "Example library"
optional = false
python-versions = "^3.8"
{groups_def}files = []
develop = true
"""
            in text
        )
        assert (
            f"""[package.source]
type = "directory"
url = "../{dep.name}"
"""
        ) in text


@pytest.mark.parametrize("module_dir", module_setups.keys())
def test_build_artifact(fixture_simple_a: Path, tmp_path: Path, module_dir: str) -> None:
    setup = module_setups[module_dir]
    package_name = package_name_of(module_dir)
    os.chdir(fixture_simple_a / module_dir)

    _out, err = run_test_app(["poetry", "build", "-vvv"])
    # using the --output argument is nice, but that needs poetry >=1.8.0
    # to be able to test with 1.7.0, deriving the dist path from the cwd
    dist_path = Path(os.getcwd()) / "dist"
    assert err == ""

    with ZipFile(dist_path / f"{package_name}-0.0.1-py3-none-any.whl") as whl:
        metadata_path = zipfile.Path(whl) / f"{package_name}-0.0.1.dist-info" / "METADATA"
        metadata_content = metadata_path.read_text().splitlines()
        validate_package_metadata(setup, metadata_content)

    with TarFile.open(dist_path / f"{package_name}-0.0.1.tar.gz") as tar:
        pkg_info_stream = tar.extractfile(f"{package_name}-0.0.1/PKG-INFO")
        assert pkg_info_stream is not None
        with pkg_info_stream:
            pkg_info_bytes = pkg_info_stream.readlines()
            pkg_info_content = list(b.decode("utf-8").strip(os.linesep) for b in pkg_info_bytes)
            validate_package_metadata(setup, pkg_info_content)


def validate_package_metadata(setup: TestSetup, content: list[str]) -> None:
    _logger.info("Validating package metadata:")
    _logger.info("\n".join(content))
    # path dependency should be removed if enabled
    for dep in setup.deps or []:
        path_str = f"Requires-Dist: {dep.name} @ "
        if setup.enabled:
            assert not any([line.startswith(path_str) for line in content])
        else:
            assert any([line.startswith(path_str) for line in content])

    # named dependency should be inserted if enabled
    for dep in setup.deps or []:
        fixed_str = f"Requires-Dist: {dep.full_name} {dep.version_range()}"
        if setup.enabled:
            assert fixed_str in content
        else:
            assert fixed_str not in content
    # transitive dependencies should not be added
    for dep in setup.transitive_deps or []:
        fixed_str = f"Requires-Dist: {dep.full_name} {dep.version_range()}"
        assert fixed_str not in content


def test_outside_project_version(tmp_path: Path) -> None:
    os.chdir(tmp_path)  # run from folder without pyproject.toml

    args = ["poetry", "--version"]
    out_value, err_value = run_test_app(args)
    _logger.info(out_value)
    assert err_value == ""
    assert out_value.startswith("Poetry (version ")


def test_outside_project_show_plugins(tmp_path: Path) -> None:
    os.chdir(tmp_path)  # run from folder without pyproject.toml
    args = ["poetry", "self", "show", "plugins"]
    out_value, err_value = run_test_app(args)
    _logger.info(out_value)
    assert err_value == ""
    assert "poetry-plugin-mono-repo-deps" in out_value
    assert (
        "Poetry plugin to replace path dependencies in mono repos with named dependency specifications at build time"
        in out_value
    )


def test_outside_project_cache(tmp_path: Path) -> None:
    os.chdir(tmp_path)  # run from folder without pyproject.toml
    args = ["poetry", "cache", "list"]
    _out_value, err_value = run_test_app(args)
    _logger.info(_out_value)
    assert err_value == "No caches found"


def test_outside_project_search(tmp_path: Path) -> None:
    os.chdir(tmp_path)  # run from folder without pyproject.toml
    args = ["poetry", "search", "requests"]
    _out_value, err_value = run_test_app(args)
    _logger.info(_out_value)
    assert err_value == ""
