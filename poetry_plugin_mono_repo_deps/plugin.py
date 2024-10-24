from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, TypeVar, cast

from cleo.events.console_event import ConsoleEvent
from cleo.events.console_events import COMMAND
from cleo.events.event import Event
from cleo.events.event_dispatcher import EventDispatcher
from cleo.io.io import IO
from poetry.console.application import Application
from poetry.core.packages.dependency import Dependency
from poetry.core.packages.package import Package
from poetry.plugins.application_plugin import ApplicationPlugin
from poetry.poetry import Poetry
from poetry.repositories.lockfile_repository import LockfileRepository
from poetry.utils.helpers import merge_dicts

T = TypeVar("T")


def _get_as_type(values: dict[str, Any], key: str, type: type[T]) -> T:
    value = values[key]
    if not isinstance(value, type):
        raise ValueError(f"{key} should be of type {type}")
    return value


ALLOWED_CONSTRAINTS = [">=", "~=", "=", "==", "^"]

TOML_SECTION = "tool.poetry-monorepo.deps"


@dataclass
class Config:
    # would be nice to use pydantic, but don't want to bring in new dependencies that might conflict with other plugins
    enabled: bool
    commands: list[str]
    constraint: str
    source_types: list[str]
    only_develop: bool

    default_config = {
        "enabled": True,
        "commands": ["build", "export"],
        "constraint": "~=",
        "source_types": ["file", "directory"],
        "only_develop": False,
    }

    @staticmethod
    def from_dict(values: dict[str, Any]) -> Config:
        config = deepcopy(Config.default_config)
        merge_dicts(config, values)
        enabled = _get_as_type(config, "enabled", bool)
        commands = [str(x) for x in _get_as_type(config, "commands", List)]
        constraint = _get_as_type(config, "constraint", str)
        source_types = [str(x) for x in _get_as_type(config, "source_types", List)]
        only_develop = _get_as_type(config, "only_develop", bool)
        return Config(
            enabled=enabled,
            commands=commands,
            constraint=constraint,
            source_types=source_types,
            only_develop=only_develop,
        )


def load_config(poetry: Poetry) -> Config | None:
    toml_sections = TOML_SECTION.split(".")
    toml_doc = poetry.pyproject.data
    for subsection in toml_sections[:-1]:
        toml_doc = toml_doc.get(subsection, {})
    # the last item (deps) needs to be present, can be empty, to enable the plugin:
    config: dict[str, Any] | None = toml_doc.get(toml_sections[-1])
    if config is not None and config.get("enabled", True):
        return Config.from_dict(config)
    else:
        return None


class MonoRepoDepsPlugin(ApplicationPlugin):
    def __init__(self) -> None:
        super().__init__()

    def activate(self, application: Application) -> None:
        self._application = application
        dispatcher = application.event_dispatcher
        if dispatcher is not None:
            dispatcher.add_listener(COMMAND, self.handle_command)
        else:  # pragma: no cover
            pass

    def handle_command(self, event: Event, _event_name: str, _dispatcher: EventDispatcher) -> None:
        try:
            poetry = self._application.poetry
        except RuntimeError:
            # should only happen if poetry runs outside poetry folder structure
            # as we modify poetry lock files, the plugin can only work in poetry folders
            # and is only relevant for commands that work in poetry folders
            # thus, either the command is not relevant
            # or, the command would fail itself
            return

        config = load_config(poetry)

        event = cast(ConsoleEvent, event)  # because we listen to COMMANDs
        io = event.io
        if config is None:  # pragma: no cover
            if io.is_debug():  # pragma: no cover
                io.write_line(
                    "<debug>Not replacing path dependencies by named dependencies as no tool configuration section "
                    "found.</debug>"
                )
            return
        command = event.command
        if command.name not in config.commands:
            if io.is_debug():  # pragma: no cover
                io.write_line(
                    "<debug>Not replacing path dependencies with named dependencies for command "
                    f"{command.name}.</debug>"
                )
            return

        if io.is_debug():  # pragma: no cover
            io.write_line("<debug>Replacing path dependencies with named dependencies.</debug>")

        # for build
        self.update_locked_repository(io, config)
        # for export
        self.update_lock_data(config)
        return None

    def update_locked_repository(self, io: IO, config: Config) -> None:
        """Updates the lockers locked repository, necessary for commands like `build`"""
        constraint = config.constraint
        poetry = self._application.poetry
        locked_repository = poetry._locker.locked_repository()
        for name in poetry.package.dependency_group_names():
            group = poetry.package.dependency_group(name)
            for dep in group.dependencies:
                if is_to_be_replaced_dependency(config, dep):
                    name = dep.name
                    # get the locked package to retrieve the current version
                    package = find_package(locked_repository, name)
                    if package is not None:
                        new = create_named_dependency(constraint, dep, package)
                        # new = Dependency(name, version or "*", extras=dep.extras)
                        io.write_line(
                            f"Replacing path dependency {dep.to_pep_508()} in group "
                            f"{group.name} with {new.to_pep_508()}"
                        )
                        group.remove_dependency(name)
                        group.add_dependency(new)
                    else:  # pragma: no cover
                        io.write_error_line(f"Failed to find version for path dependency {name}")

    def update_lock_data(self, config: Config) -> None:
        """Updates the lockers internal lock data, necessary for commands like `export`"""
        poetry = self._application.poetry
        locked_packages = cast(List[Dict[str, Any]], poetry._locker.lock_data["package"])
        for info in locked_packages:
            if is_to_be_replaced_package_lock(config, info):
                modify_locked_package_to_named(config, info, locked_packages)


def is_to_be_replaced_package_lock(config: Config, locked_package_data: dict[str, Any]) -> bool:
    source = locked_package_data.get("source", {})
    source_type = source.get("type")
    can_be_develop = source_type == "directory"
    is_develop = can_be_develop and locked_package_data.get("develop", False)
    must_be_develop = config.only_develop
    return (source_type in config.source_types) and not (must_be_develop and can_be_develop and not is_develop)


def is_to_be_replaced_dependency_lock(config: Config, locked_dependency_data: str | dict[str, Any]) -> bool:
    # Could look like:
    #   {path = "../lib-a", develop = true}
    #   { version = "0.1.2", optional = true, markers = "extra == \"an_extra\""}
    #   { version = "0.1.2", extras = ["foo", "bar"]}
    #   or just the version constraint as a string:
    #   *
    #   "0.1.2"
    #   ">=0.1.1, <0.1.3"
    if not isinstance(locked_dependency_data, dict):
        return False  # pragma: no cover (won't happen as we already checked it being a dict)

    source_types = (
        (["directory", "file"] if "path" in locked_dependency_data else [])
        + (["url"] if "url" in locked_dependency_data else [])
        + (["git"] if "git" in locked_dependency_data else [])
    )
    matches_source_type = any((source_type in config.source_types) for source_type in source_types)  # pragma: no cover
    can_be_develop = "path" in locked_dependency_data
    is_develop = can_be_develop and locked_dependency_data.get("develop", False)
    must_be_develop = config.only_develop
    return matches_source_type and not (must_be_develop and can_be_develop and not is_develop)


def is_to_be_replaced_dependency(config: Config, dep: Dependency) -> bool:
    can_be_develop = hasattr(dep, "_develop")
    is_develop = can_be_develop and dep._develop  # type: ignore[attr-defined]
    must_be_develop = config.only_develop
    is_to_be_replaced = (dep._source_type in config.source_types) and not (
        must_be_develop and can_be_develop and not is_develop
    )
    return is_to_be_replaced


def find_package(locked_repository: LockfileRepository, name: str) -> Package | None:
    package: Package | None = None
    for locked in locked_repository.packages:  # pragma: no cover
        if locked.name == name:
            package = locked
            break
    return package


def create_named_dependency(constraint: str, dep: Dependency, package: Package) -> Dependency:
    name = package.name
    version = package.version
    dep_str = constraint + version.text
    return Dependency(
        name,
        dep_str,
        optional=dep.is_optional(),
        groups=dep.groups,
        allows_prereleases=dep.allows_prereleases(),
        extras=dep.extras,
    )


def modify_locked_package_to_named(
    config: Config, info: dict[str, Any], all_locked_packages: list[dict[str, Any]]
) -> None:
    if is_to_be_replaced_package_lock(config, info):
        _modify_locked_package_to_named(info)
        # remove path and develop from dependencies of dependencies
        for dep_name, dep in info.get("dependencies", {}).items():
            if is_to_be_replaced_dependency_lock(config, dep):
                dep_version = get_current_locked_version(all_locked_packages, dep_name, "*")
                _modify_locked_dependency_to_named(dep, dep_version)


def get_current_locked_version(locked_packaged: list[dict[str, Any]], name: str, default: str) -> str:
    for package in locked_packaged:
        if package.get("name", "").lower() == name.lower():
            return cast(str, package.get("version", default))
    return default


def _modify_locked_package_to_named(info: dict[str, Any]) -> None:
    # just deleting the develop and source will make exports only export the name
    if "develop" in info:  # pragma: no cover
        del info["develop"]
    if "source" in info:  # pragma: no cover
        del info["source"]


def _modify_locked_dependency_to_named(dep: dict[str, Any] | str, dep_version: str) -> None:
    if isinstance(dep, str):
        return  # pragma: no cover # it is just a version constraint
    del_dict_keys(dep, ["path", "develop", "url"])
    if "git" in dep:
        del_dict_keys(dep, ["git", "rev", "branch", "tag", "subdirectory"])
    dep["version"] = dep.get("version", dep_version)


def del_dict_keys(d: dict[str, Any], keys: list[str]) -> None:
    """Delete all keys from the passed dict, if they exist."""
    for key in keys:
        if key in d:
            del d[key]
