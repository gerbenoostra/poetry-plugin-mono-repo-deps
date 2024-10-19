from __future__ import annotations

from pathlib import Path

import pytest
from poetry.core.packages.package import Package
from poetry.factory import Factory

from poetry_plugin_mono_repo_deps.plugin import (
    ALLOWED_CONSTRAINTS,
    Config,
    create_named_dependency,
    modify_locked_package_to_named,
)
from tests.helpers import prepare_test_poetry


def test_config_empty() -> None:
    assert Config.from_dict({}) == Config(
        enabled=True,
        commands=["build", "export"],
        constraint="~=",
        source_types=["file", "directory"],
        only_develop=False,
    )


@pytest.mark.parametrize("field_name", ["enabled", "commands", "constraint", "source_types", "only_develop"])
def test_config_missing_required_value(field_name: str) -> None:
    with pytest.raises(ValueError) as e_info:
        Config.from_dict({field_name: None})
    assert str(e_info.value).startswith(f"{field_name} should be of type")


@pytest.mark.parametrize("constraint", ALLOWED_CONSTRAINTS)
@pytest.mark.parametrize(
    "package",
    [
        Package(
            "git-package",
            "1.2.3",
            source_type="git",
            source_url="https://github.com/python-poetry/poetry.git",
            source_reference="develop",
            source_resolved_reference="123456",
        ),
        Package(
            "git-package-subdir",
            "1.2.3",
            source_type="git",
            source_url="https://github.com/python-poetry/poetry.git",
            source_reference="develop",
            source_resolved_reference="123456",
            source_subdirectory="subdir",
        ),
        Package(
            "url-package",
            "1.0",
            source_type="url",
            source_url="https://example.org/url-package-1.0-cp39-manylinux_2_17_x86_64.whl",
        ),
        Package(
            "url-package",
            "1.0",
            source_type="url",
            source_url="https://example.org/url-package-1.0-cp39-win_amd64.whl",
        ),
    ],
)
def test_named_dependency_for_package(constraint: str, package: Package) -> None:
    create_named_dependency(constraint, package.to_dependency(), package)


@pytest.mark.parametrize("constraint", ALLOWED_CONSTRAINTS)
def test_named_dependency_for_package_with_deps(constraint: str) -> None:
    expected_constraint_result = {
        "~=": ">=1.0.0,<1.1.0",
        "^": ">=1.0.0,<2.0.0",
        ">=": ">=1.0.0",
        "=": "==1.0.0",
        "==": "==1.0.0",
    }
    package_a = Package("A", "1.0.0")
    package_a.add_dependency(Factory.create_dependency("B", "^1.0"))
    package_a.files = [{"file": "foo", "hash": "456"}, {"file": "bar", "hash": "123"}]
    dep = create_named_dependency(constraint, package_a.to_dependency(), package_a)
    assert dep.to_pep_508() == f"a ({expected_constraint_result[constraint]})"


@pytest.mark.parametrize("constraint", ALLOWED_CONSTRAINTS)
def test_named_dependency_for_package_with_files(constraint: str) -> None:
    package_a2 = Package("A", "2.0.0")
    package_a2.files = [{"file": "baz", "hash": "345"}]
    create_named_dependency(constraint, package_a2.to_dependency(), package_a2)


def test_nested_dependency() -> None:
    package_a = Package("A", "1.0.0")
    package_a.files = [{"file": "baz", "hash": "345"}]
    package_b = Package("B", "1.0.0")
    package_b.add_dependency(package_a.to_dependency())
    dep = create_named_dependency("~=", package_b.to_dependency(), package_b)
    assert dep is not None


def test_lock_to_name_files(fixture_simple_a: Path) -> None:
    """Verifies that a package with dependency can be modified."""
    poetry = prepare_test_poetry(fixture_simple_a / "lib-a")
    package_a = Package("A", "1.0.0")
    package_a.add_dependency(Factory.create_dependency("B", "^1.0"))
    package_a.files = [{"file": "foo", "hash": "456"}, {"file": "bar", "hash": "123"}]
    locked_packages = poetry._locker._lock_packages([package_a])
    modify_locked_package_to_named(
        Config(
            enabled=True,
            commands=["build", "export"],
            constraint="~=",
            source_types=["file", "directory"],
            only_develop=False,
        ),
        locked_packages[0],
        locked_packages,
    )
    assert locked_packages[0] == {
        "name": "A",
        "version": "1.0.0",
        "files": [{"file": "bar", "hash": "123"}, {"file": "foo", "hash": "456"}],
        "dependencies": {"B": "^1.0"},
        "description": "",
        "optional": False,
        "python-versions": "*",
    }


def test_lock_to_name_for_path_dependency(fixture_simple_a: Path) -> None:
    """Verifies that a package's path source will be removed."""
    poetry = prepare_test_poetry(fixture_simple_a / "lib-a")
    package_a = Package("A", "1.0.0", source_type="directory", source_url="../lib-a")
    locked_packages = poetry._locker._lock_packages([package_a])
    modify_locked_package_to_named(
        Config(
            enabled=True,
            commands=["build", "export"],
            constraint="~=",
            source_types=["file", "directory"],
            only_develop=False,
        ),
        locked_packages[0],
        locked_packages,
    )
    assert locked_packages[0] == {
        "name": "A",
        "version": "1.0.0",
        "description": "",
        "files": [],
        "optional": False,
        "python-versions": "*",
    }


def test_lock_to_name_for_transitive_path_dependency(fixture_simple_a: Path) -> None:
    """When both a package and its dependency is to modified (without extras)"""
    poetry = prepare_test_poetry(fixture_simple_a / "lib-a")
    package_a = Package("A", "1.0.0", source_type="directory", source_url="../lib-a")
    package_b = Package("B", "1.0.0", source_type="directory", source_url="../lib-b")
    package_b.add_dependency(package_a.to_dependency())
    locked_packages = poetry._locker._lock_packages([package_a, package_b])
    modify_locked_package_to_named(
        Config(
            enabled=True,
            commands=["build", "export"],
            constraint="~=",
            source_types=["file", "directory"],
            only_develop=False,
        ),
        locked_packages[1],
        locked_packages,
    )
    assert locked_packages[1] == {
        "name": "B",
        "version": "1.0.0",
        "dependencies": {"a": {"version": "1.0.0"}},
        "description": "",
        "files": [],
        "optional": False,
        "python-versions": "*",
    }


def test_lock_to_name_for_transitive_path_dependency_with_extras(fixture_simple_a: Path) -> None:
    """When both a package and its dependency is to modified (and it has extras)"""
    poetry = prepare_test_poetry(fixture_simple_a / "lib-a")
    package_a = Package("A", "1.0.0", source_type="directory", source_url="../lib-a", features=["foo"])
    package_b = Package("B", "1.0.0", source_type="directory", source_url="../lib-b")
    package_b.add_dependency(package_a.to_dependency())
    locked_packages = poetry._locker._lock_packages([package_a, package_b])
    modify_locked_package_to_named(
        Config(
            enabled=True,
            commands=["build", "export"],
            constraint="~=",
            source_types=["file", "directory"],
            only_develop=False,
        ),
        locked_packages[1],
        locked_packages,
    )
    assert locked_packages[1] == {
        "name": "B",
        "version": "1.0.0",
        "dependencies": {"a": {"extras": ["foo"], "version": "1.0.0"}},
        "description": "",
        "files": [],
        "optional": False,
        "python-versions": "*",
    }


def test_lock_to_name_for_transitive_non_path_dependency(fixture_simple_a: Path) -> None:
    """When a package is to modified, but its dependency not."""
    poetry = prepare_test_poetry(fixture_simple_a / "lib-a")
    package_a = Package("A", "1.0.0")
    package_b = Package("B", "1.0.0")
    package_b.add_dependency(package_a.to_dependency())
    locked_packages = poetry._locker._lock_packages([package_a, package_b])
    modify_locked_package_to_named(
        Config(
            enabled=True,
            commands=["build", "export"],
            constraint="~=",
            source_types=["file", "directory"],
            only_develop=False,
        ),
        locked_packages[1],
        locked_packages,
    )
    assert locked_packages[1] == {
        "name": "B",
        "version": "1.0.0",
        "dependencies": {"a": "1.0.0"},
        "description": "",
        "files": [],
        "optional": False,
        "python-versions": "*",
    }


def test_lock_to_name_for_unknown_dependency_version(fixture_simple_a: Path) -> None:
    """When a package's dependency is to modified, but we don't know which version it has."""
    poetry = prepare_test_poetry(fixture_simple_a / "lib-a")
    package_a = Package("A", "1.0.0", source_type="directory", source_url="../lib-a")
    package_b = Package("B", "1.0.0", source_type="directory", source_url="../lib-b")
    package_b.add_dependency(package_a.to_dependency())
    locked_packages = poetry._locker._lock_packages([package_b])
    modify_locked_package_to_named(
        Config(
            enabled=True,
            commands=["build", "export"],
            constraint="~=",
            source_types=["file", "directory"],
            only_develop=False,
        ),
        locked_packages[0],
        locked_packages,
    )
    assert locked_packages[0] == {
        "name": "B",
        "version": "1.0.0",
        "dependencies": {"a": {"version": "*"}},
        "description": "",
        "files": [],
        "optional": False,
        "python-versions": "*",
    }


def test_lock_to_name_for_version_dependency(fixture_simple_a: Path) -> None:
    """When a package is to modified, but its dependency is only specified by its version (thus as a string instead of a
    dict)"""
    poetry = prepare_test_poetry(fixture_simple_a / "lib-a")
    package_a = Package("A", "1.0.0")
    package_b = Package("B", "1.0.0", source_type="directory", source_url="../lib-b")
    package_b.add_dependency(package_a.to_dependency())
    locked_packages = poetry._locker._lock_packages([package_b])
    modify_locked_package_to_named(
        Config(
            enabled=True,
            commands=["build", "export"],
            constraint="~=",
            source_types=["file", "directory"],
            only_develop=False,
        ),
        locked_packages[0],
        locked_packages,
    )
    assert locked_packages[0] == {
        "name": "B",
        "version": "1.0.0",
        "dependencies": {"a": "1.0.0"},
        "description": "",
        "files": [],
        "optional": False,
        "python-versions": "*",
    }


def test_lock_to_name_with_git_dependency(fixture_simple_a: Path) -> None:
    """When a package is to modified, but its dependency is only specified by its version (thus as a string instead of a
    dict)"""
    poetry = prepare_test_poetry(fixture_simple_a / "lib-a")
    package_a = Package(
        "A", "1.0.0", source_type="git", source_url="https://github.com/urllib3/urllib3.git", source_reference="HEAD"
    )
    package_b = Package("B", "1.0.0", source_type="directory", source_url="../lib-b")
    package_b.add_dependency(package_a.to_dependency())
    locked_packages = poetry._locker._lock_packages([package_a, package_b])
    for locked_package in locked_packages:
        modify_locked_package_to_named(
            Config(
                enabled=True,
                commands=["build", "export"],
                constraint="~=",
                source_types=["file", "directory", "git"],
                only_develop=False,
            ),
            locked_package,
            locked_packages,
        )
    assert locked_packages[0] == {
        "name": "A",
        "version": "1.0.0",
        "description": "",
        "files": [],
        "optional": False,
        "python-versions": "*",
    }

    assert locked_packages[1] == {
        "name": "B",
        "version": "1.0.0",
        "dependencies": {"a": {"version": "1.0.0"}},
        "description": "",
        "files": [],
        "optional": False,
        "python-versions": "*",
    }
