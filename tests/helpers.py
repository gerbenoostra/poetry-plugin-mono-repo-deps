from __future__ import annotations

import logging
import os
import re
from io import StringIO
from pathlib import Path
from typing import Any

from cleo.commands.command import Command
from cleo.io.inputs.argv_input import ArgvInput
from cleo.io.io import IO
from cleo.io.outputs.output import Verbosity
from cleo.io.outputs.stream_output import StreamOutput
from cleo.testers.command_tester import CommandTester
from poetry.console.application import Application
from poetry.core.packages.package import Package
from poetry.factory import Factory
from poetry.installation import Installer
from poetry.installation.executor import Executor
from poetry.installation.operations.operation import Operation
from poetry.packages.locker import Locker
from poetry.poetry import Poetry
from poetry.utils.env import Env
from tomlkit.toml_document import TOMLDocument

_logger = logging.getLogger(__name__)


class PoetryTestApplication(Application):
    def __init__(self, poetry: Poetry) -> None:
        super().__init__()
        self._poetry = poetry

    def reset_poetry(self) -> None:
        assert self._poetry is not None
        poetry = self._poetry
        self._poetry = Factory().create_poetry(self._poetry.file.path.parent)
        self._poetry.set_pool(poetry.pool)
        self._poetry.set_config(poetry.config)
        self._poetry.set_locker(TestLocker(poetry.locker.lock, self._poetry.pyproject.data))


class TestLocker(Locker):
    # class name begins 'Test': tell pytest that it does not contain testcases.
    __test__ = False

    def __init__(self, project_path: Path, pyproject_data: dict[str, Any] = {}) -> None:
        super().__init__(project_path / "poetry.lock", pyproject_data)
        self._locked = False
        self._write = False

    def write(self, write: bool = True) -> None:
        self._write = write

    def is_locked(self) -> bool:
        return self._locked

    def locked(self, is_locked: bool = True) -> TestLocker:
        self._locked = is_locked

        return self

    def mock_lock_data(self, data: dict[str, Any]) -> None:
        self.locked()

        self._lock_data = data

    def is_fresh(self) -> bool:
        return True

    def _write_lock_data(self, data: TOMLDocument) -> None:
        if self._write:
            _logger.info("Writing lock data")
            super()._write_lock_data(data)
            self._locked = True
            return
        else:
            _logger.info("Not writing lock data")

        self._lock_data = data

    def _get_content_hash(self) -> str:
        return "123456789"


def prep_command(
    command: str,
    app: PoetryTestApplication,
    env: Env,
    poetry: Poetry | None = None,
    installer: Installer | None = None,
    executor: Executor | None = None,
) -> Command:
    command_obj = app.find(command)
    tester = CommandTester(command_obj)

    # Setting the formatter from the application
    # TODO: Find a better way to do this in Cleo
    app_io = app.create_io()
    formatter = app_io.output.formatter
    tester.io.output.set_formatter(formatter)
    tester.io.error_output.set_formatter(formatter)

    if poetry:
        app._poetry = poetry
    else:
        poetry = app.poetry

    if hasattr(command_obj, "set_env"):
        command_obj.set_env(env)

    if hasattr(command_obj, "set_installer"):
        installer = installer or Installer(
            tester.io,
            env,
            poetry.package,
            poetry.locker,
            poetry.pool,
            poetry.config,
            executor=executor or TestExecutor(env, poetry.pool, poetry.config, tester.io),
        )
        command_obj.set_installer(installer)

    return command_obj


class TestExecutor(Executor):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self._installs: list[Package] = []
        self._updates: list[Package] = []
        self._uninstalls: list[Package] = []

    @property
    def installations(self) -> list[Package]:
        return self._installs

    @property
    def updates(self) -> list[Package]:
        return self._updates

    @property
    def removals(self) -> list[Package]:
        return self._uninstalls

    def _do_execute_operation(self, operation: Operation) -> int:
        rc: int = super()._do_execute_operation(operation)

        if not operation.skipped:
            _logger.info(f"Running {operation.job_type} for {operation.package}")
            getattr(self, f"_{operation.job_type}s").append(operation.package)
        else:
            _logger.info(f"Skipping {operation.job_type} for {operation.package}")

        return rc

    def _execute_install(self, operation: Operation) -> int:
        return 0

    def _execute_update(self, operation: Operation) -> int:
        return 0

    def _execute_remove(self, operation: Operation) -> int:
        return 0


def prepare_test_app(path: Path) -> PoetryTestApplication:
    poetry = Factory().create_poetry(path)
    test_app = PoetryTestApplication(poetry)
    io = test_app.create_io()
    io.output.set_verbosity(Verbosity.DEBUG)
    _logger.info("Loading plugins")
    test_app._load_plugins(io)
    test_app.auto_exits(False)
    return test_app


def prepare_test_poetry(proj_path: Path) -> Poetry:
    locker = TestLocker(proj_path)
    _logger.info("Creating test poetry")
    poetry = Factory().create_poetry(proj_path)
    poetry._locker = locker
    return poetry


try:
    # Since Poetry==2.0.0, we need to pass a dict
    # We try to stay as long as possible compatible with Poetry<2.0.0 too
    from poetry.packages.transitive_package_info import TransitivePackageInfo

    POETRY_VERSION = 2

    def lock_packages(poetry: Poetry, packages: list[Package]) -> list[dict[str, Any]]:
        """Wraps locker to keep it consistent across Poetry 2.0.0 & Poetry <2.0.0."""
        locked_packages = poetry._locker._lock_packages(
            # following arg-type ignore is for mypy with poetry<2.0
            # but need an unused-ignore for mypy with poetry>=2.0
            {package: TransitivePackageInfo(0, {"main"}, {}) for package in packages}  # type: ignore[arg-type,unused-ignore]
        )
        return locked_packages
except ImportError:
    POETRY_VERSION = 1

    def lock_packages(poetry: Poetry, packages: list[Package]) -> list[dict[str, Any]]:
        # following arg-type ignore is for mypy with poetry>=2.0
        # but need an unused-ignore for mypy with poetry<2.0
        return poetry._locker._lock_packages(packages)  # type: ignore[arg-type,unused-ignore]


export_warning = "Warning: poetry-plugin-export will not be installed by default in a future version of Poetry.\nIn order to avoid a breaking change and make your automation forward-compatible, please install poetry-plugin-export explicitly. See https://python-poetry.org/docs/plugins/#using-plugins for details on how to install a plugin.\nTo disable this warning run 'poetry config warnings.export false'.\n"  # noqa: E501 Line too long


def run_test_app(args: list[str]) -> tuple[str, str]:
    test_app = Application()

    out = StringIO()
    err = StringIO()
    out_stream = StreamOutput(out)
    out_stream.set_verbosity(Verbosity.DEBUG)
    err_stream = StreamOutput(err)
    instr = ArgvInput(args)
    io = IO(instr, out_stream, err_stream)
    _logger.info("Loading plugins")
    test_app._load_plugins(io)
    test_app.auto_exits(False)
    _logger.info("Running poetry test app")
    test_app.run(
        instr,
        out_stream,
        err_stream,
    )
    out_stream.flush()
    err_stream.flush()
    out_value = out.getvalue()
    _logger.info("Poetry run output:")
    _logger.info(out_value)
    err_value = err.getvalue()
    _logger.info("Poetry run error output:")
    _logger.info(err_value)
    # clear python detect warning
    err_value = re.sub(
        "Trying to detect current active python executable as specified in the config.\nFound: .*\n", "", err_value
    )
    err_value = err_value.replace(export_warning, "")
    err_value = os.linesep.join(
        [line for line in err_value.splitlines() if not line.startswith("Creating virtualenv ")]
    )
    return out_value, err_value


class AppRunner:
    def __init__(self, app: Application) -> None:
        self._test_app = app

    def run(self, args: list[str]) -> tuple[str, str]:
        out = StringIO()
        err = StringIO()
        out_stream = StreamOutput(out)
        err_stream = StreamOutput(err)
        instr = ArgvInput(args)
        instr.bind(self._test_app.definition)
        _logger.info("Running poetry test app")
        self._test_app.run(
            instr,
            out_stream,
            err_stream,
        )
        out_stream.flush()
        err_stream.flush()
        out_value = out.getvalue()
        _logger.info("Poetry run output:")
        _logger.info(out_value)
        err_value = err.getvalue()
        _logger.info("Poetry run error output:")
        _logger.info(err_value)
        err_value = err_value.replace(export_warning, "")
        err_value = os.linesep.join(
            [line for line in err_value.splitlines() if not line.startswith("Creating virtualenv ")]
        )
        return out_value, err_value
