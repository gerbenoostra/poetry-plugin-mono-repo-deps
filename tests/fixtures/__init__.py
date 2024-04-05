from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TestSetup:
    # class name begins 'Test': tell pytest that it does not contain testcases.
    __test__ = False

    enabled: bool = True
    has_dep: bool = True
    extras: list[str] | None = None

    def dep_name(self) -> str:
        return "lib-a" + self.extras_suffix()

    def extras_suffix(self) -> str:
        if self.extras and len(self.extras) > 0:
            return "[" + ",".join(self.extras) + "]"
        return ""


# Maps module_dir to whether the MonoRepoDeps plugin is enabled in its pyproject.toml
# This also allows the pytest parametrization to become test_name[module_dir]


module_setups = {
    "lib-auto-enabled": TestSetup(enabled=True),
    "lib-disabled": TestSetup(enabled=False),
    "lib-enabled": TestSetup(enabled=True),
    "lib-enabled-extras": TestSetup(enabled=True, extras=["attrs"]),
    "lib-enabled-no-commands": TestSetup(enabled=False),
    "lib-independent": TestSetup(enabled=True, has_dep=False),
    "lib-missing": TestSetup(enabled=False),
}


def package_name_of(module_dir: str) -> str:
    return module_dir.replace("-", "_")
