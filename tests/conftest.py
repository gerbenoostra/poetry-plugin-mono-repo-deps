from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path
from typing import Any, Protocol

import keyring
import pytest
from cleo.io.buffered_io import BufferedIO
from cleo.io.io import IO
from keyring.backends.fail import Keyring as FailKeyring
from poetry.config.config import Config as BaseConfig
from poetry.config.dict_config_source import DictConfigSource
from poetry.utils.env import MockEnv
from pytest_mock import MockerFixture

_logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True, scope="session")
def set_logging() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("poetry").setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)


class FixtureDirGetter(Protocol):
    def __call__(self, name: str) -> Path: ...


@pytest.fixture
def fixture_copy(fixture_base: Path, tmp_path: Path) -> FixtureDirGetter:
    def copy(name: str) -> Path:
        dest = tmp_path / name
        _logger.info(f"Copying {name} to {dest}")
        shutil.copytree(fixture_base / name, dest)
        return dest

    return copy


@pytest.fixture
def fixture_simple_a(fixture_copy: FixtureDirGetter) -> Path:
    return fixture_copy("simple_a")


class Config(BaseConfig):
    _config_source: DictConfigSource
    _auth_config_source: DictConfigSource

    def get(self, setting_name: str, default: Any = None) -> Any:
        self.merge(self._config_source.config)
        self.merge(self._auth_config_source.config)

        return super().get(setting_name, default=default)

    def raw(self) -> dict[str, Any]:
        self.merge(self._config_source.config)
        self.merge(self._auth_config_source.config)

        return super().raw()

    def all(self) -> dict[str, Any]:
        self.merge(self._config_source.config)
        self.merge(self._auth_config_source.config)

        return super().all()


@pytest.fixture
def config_cache_dir(tmp_path: Path) -> Path:
    path = tmp_path / ".cache" / "pypoetry"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def config_source(config_cache_dir: Path) -> DictConfigSource:
    source = DictConfigSource()
    source.add_property("cache-dir", str(config_cache_dir))

    return source


@pytest.fixture
def auth_config_source() -> DictConfigSource:
    source = DictConfigSource()

    return source


@pytest.fixture(autouse=True)
def config(
    config_source: DictConfigSource,
    auth_config_source: DictConfigSource,
    mocker: MockerFixture,
) -> Config:
    keyring.set_keyring(FailKeyring())

    c = Config()
    c.merge(config_source.config)
    c.set_config_source(config_source)
    c.set_auth_config_source(auth_config_source)

    mocker.patch("poetry.config.config.Config.create", return_value=c)
    mocker.patch("poetry.config.config.Config.set_config_source")

    return c


@pytest.fixture(scope="session")
def fixture_base() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixture_dir(fixture_base: Path) -> FixtureDirGetter:
    def _fixture_dir(name: str | Path) -> Path:
        return fixture_base / name

    return _fixture_dir


@pytest.fixture
def env(tmp_path: Path) -> MockEnv:
    path = tmp_path / ".venv"
    path.mkdir(parents=True)
    return MockEnv(path=path, is_venv=True)


@pytest.fixture()
def io() -> IO:
    return BufferedIO()
