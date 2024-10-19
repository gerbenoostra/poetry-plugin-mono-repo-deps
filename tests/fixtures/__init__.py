from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Dep:
    name: str
    version: str = "0.0.1"
    extras: list[str] | None = None

    def to_pep_508(self) -> str:
        return f"{self.name}{self.extras_suffix()}=={self.version}"

    @property
    def full_name(self) -> str:
        return f"{self.name}{self.extras_suffix()}"

    def extras_suffix(self) -> str:
        if self.extras and len(self.extras) > 0:
            return "[" + ",".join(self.extras) + "]"
        return ""


@dataclass
class TestSetup:
    # class name begins 'Test': tell pytest that it does not contain testcases.
    __test__ = False

    enabled: bool = True
    deps: list[Dep] | None = None

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
    "lib-enabled-no-commands": TestSetup(enabled=False, deps=[Dep(name="lib-a")]),
    "lib-independent": TestSetup(enabled=True, deps=[]),
    "lib-missing": TestSetup(enabled=False, deps=[Dep(name="lib-a")]),
    "lib-nested": TestSetup(enabled=True, deps=[Dep(name="lib-b")]),
}


def package_name_of(module_dir: str) -> str:
    return module_dir.replace("-", "_")
