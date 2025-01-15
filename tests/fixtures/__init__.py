from __future__ import annotations

from dataclasses import dataclass

from tests.helpers import POETRY_VERSION as POETRY_VERSION


@dataclass
class Dep:
    name: str
    version: str = "0.0.1"
    extras: list[str] | None = None
    extras_environment_markers: list[str] | None = None

    def to_pep_508(self) -> str:
        return f"{self.name}{self._extras_suffix()}=={self.version}{self._environment_marker_suffix()}"

    def _extras_suffix(self) -> str:
        if self.extras and len(self.extras) > 0:
            return "[" + ",".join(self.extras) + "]"
        return ""

    def _environment_marker_suffix(self) -> str:
        if self.extras_environment_markers:
            return " ; " + " or ".join(f'extra == "{extra}"' for extra in self.extras_environment_markers)
        return ""

    def version_range(self) -> str:
        major, minor, *_ = self.version.split(".")
        if int(major) == 0:
            upper_bound = f"{major}.{int(minor) + 1}.0"
        else:
            upper_bound = f"{int(major) + 1}.0.0"
        return f"(>={self.version},<{upper_bound})"

    def metadata_line(self) -> str:
        return (
            f"Requires-Dist: {self.name}{self._extras_suffix()} {self.version_range()}"
            + self._environment_marker_suffix()
        ).rstrip()

    def export_line(self) -> str:
        py_version_marker = """ ; python_version >= "3.8" and python_version < "4.0\""""
        return f"{self.name}{self._extras_suffix()}=={self.version}{py_version_marker}"


@dataclass
class TestSetup:
    # class name begins 'Test': tell pytest that it does not contain testcases.
    __test__ = False

    enabled: bool = True
    deps: list[Dep] | None = None
    transitive_deps: list[Dep] | None = None

    @property
    def has_deps(self) -> bool:
        return self.deps is not None and len(self.deps) > 0


# Maps module_dir to whether the MonoRepoDeps plugin is enabled in its pyproject.toml
# This also allows the pytest parametrization to become test_name[module_dir]


module_setups = {
    "lib-auto-enabled": TestSetup(enabled=True, deps=[Dep(name="lib-a")]),
    "lib-disabled": TestSetup(enabled=False, deps=[Dep(name="lib-a")]),
    "lib-enabled": TestSetup(enabled=True, deps=[Dep(name="lib-a")]),
    "lib-enabled-extras": TestSetup(enabled=True, deps=[Dep(name="lib-a", extras=["attrs"])]),
    "lib-enabled-optional": TestSetup(
        enabled=True, deps=[Dep(name="lib-a", extras_environment_markers=["asset-utils", "utils"])]
    ),
    "lib-enabled-no-commands": TestSetup(enabled=False, deps=[Dep(name="lib-a")]),
    "lib-independent": TestSetup(enabled=True, deps=[]),
    "lib-missing": TestSetup(enabled=False, deps=[Dep(name="lib-a")]),
    "lib-nested": TestSetup(
        enabled=True,
        deps=[Dep(name="lib-b")],
        transitive_deps=[Dep(name="lib-a"), Dep(name="dummy-poetry", version="1.2.3")],
    ),
}


def package_name_of(module_dir: str) -> str:
    return module_dir.replace("-", "_")
