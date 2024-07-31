# Poetry plugin to Pin Path dependencies

[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)
[![codecov](https://codecov.io/gh/gerbenoostra/poetry-plugin-mono-repo-deps/graph/badge.svg?token=O6NQ6H0IVN)](https://codecov.io/gh/gerbenoostra/poetry-plugin-mono-repo-deps)

A [**Poetry**](https://python-poetry.org/) plugin for Poetry mono repositories, that will replace path dependencies with named dependency specifications.

A mono repository contains multiple Python packages, which can depend on each other.
These are typically path dependencies with the `develop = true` attribute.
This allows for easy development and local running.
However, when the packages are published to a PyPi repo, these dependencies should be named dependencies.
By publishing the packages with named dependencies, one can easily install the packages and their dependencies.

This plugin will replace path dependencies (`name @ path`) with named dependency specifications (`name ~= version`).
By default, this is done when building artifacts ([`poetry build`](https://python-poetry.org/docs/main/cli/#build)) and exporting the locked dependency list ([`poetry export`](https://github.com/python-poetry/poetry-plugin-export)).
The plugin can however be configured to modify any other command registered by Poetry or other plugins.

## An example using build and export

Suppose you have a single folder with 2 Python packages, where one (`app-b`) depends on the other (`lib-a`).

The used library has the following in its Poetry section:

```toml
# repo/A/pyproject.toml
[tool.poetry]
name = "lib-a"
version = "0.0.1"
```

The application package depends on the previous library as follows:

```toml
# repo/B/pyproject.toml
[tool.poetry]
name = "app-B"

[tool.poetry.dependencies]
library-a = {path = "../A", develop=true}
```

### Poetry build

By default, building the above project with Poetry (`poetry build`), will result in a build artifact (`tar.gz`/`whl`) containing a path dependency in its metadata similar to:

```
Requires-Dist: lib-a @ file:///your/local/checkout/project/root/lib-a
```

This prevents sharing the build and reusing the build artifact on other systems, as it expects to find `lib-a` at that specific path.

Using this Mono-Repo-Deps plugin, the Poetry build will result in the following dependency:

```
Requires-Dist: lib-a (>=0.0.1,<0.1.0)
```

### Poetry export

By default, exporting the full dependency list (`poetry export`) results in a dependency list (`requirements.txt`) that also contain path dedendencies with full paths:

```
lib-a @ file:///your/local/checkout/project/root/lib-a
```

Again, by using this Mono-Repo-Deps plugin, these will become:

```
lib-a==0.1.0
```

## Installation

You can install the plugin as explained in the [Poetry documentation about plugin usage](https://python-poetry.org/docs/main/plugins/#using-plugins).

Which can be summarized as:

If you used PipX to install Poetry:

```shell
pipx inject poetry poetry-plugin-mono-repo-deps
```

If you used Pip to install Poetry:

```shell
pip install poetry-plugin-mono-repo-deps
```

On non-Windows devices, you can also use Poetry's `self add` which will also validate compatibility:

```shell
poetry self add poetry-plugin-mono-repo-deps
```

## Usage:

As plugins are installed systemwide, **this plugin is by default disabled** to not unintentionally modify the existing behavior of Poetry.

Enable the plugin by adding the following (empty) section to your `pyproject.toml`:

```toml
# repo/B/pyproject.toml
[tool.poetry-monorepo.deps]
```

This is equivalent to adding the following default settings:

```toml
[tool.poetry-monorepo.deps]
enabled = true
commands = ["build", "export"]
constraint = "~="
source_types = ["file", "directory"]
only_develop = false
```

Possible alternative values can be found in the following section:

## Configuration:

### `enabled`

**Type**: `boolean`

**Default**: `true`

**Allowed values**: `true`, `false`

Whether the plugin should be activated for commands on this project.

### `commands`

**Type**: `List[string]`

**Default**: `["build", "export"]`

**Allowed values**: Any CLI command registered with Poetry (could also be provided by other plugins).

The intercepted poetry commands.
The plugin will intercept the command and update the internal representation of dependencies, changing the path dependencies to named dependency specifications.

### `constraint`

**Type**: `string`

**Default**: `~=`

**Allowed values**: `==`, `>=` , `~=` , `^` (All [valid Poetry version constraints](https://python-poetry.org/docs/dependency-specification/)).

The version constraint that is applied to the current version of the dependency.

For example, when the dependency has version `0.0.1`, and the default constraint string `~=` is used, it will result in a named dependency with version `>=0.1.0, <0.1.0`.

### `source_types`

**Type**: `List[string]`

**Default**: `["file", "directory"]` (local Path dependencies)

**Allowed values**: `["file", "directory", "url", "git"]`. (Any `source_type` attribute of Poetry's internal Dependency object, which includes the lowercase VCS identifier, like `git`).

The type of dependencies that should be replaced with their named version specification.

### `only_develop`

**Type**: `boolean`

**Default**: `false`

Enable to only replace `develop` dependencies, which, as currently implemented in Poetry, are only `directory` [Path dependencies](https://python-poetry.org/docs/main/dependency-specification/#path-dependencies).

This filter is **only applied to directory path** dependencies, as only those can have the `develop` mark.

If you configure `source_types` to be any Path dependency (ie. `file` or `directory`), all file path dependencies will be translated, while only the directory dependencies annotated with `develop = true` will be translated.

## Caveats

Currently, the plugin has only been verified to work with the `poetry build` and `poetry export` commands.
Though theoretically it should work with any other (plugin's) command, your mileage may vary.

## How it works

If enabled, this plugin registers itself to run before specific commands.
When these commands are run, it will modify the internal lock file representation that Poetry uses, replacing the path dependency objects with regular dependencies.

The idea came from the [Python Poetry Monorepo without Limitations](https://gerben-oostra.medium.com/python-poetry-mono-repo-without-limitations-dd63b47dc6b8) blog post on Medium, which describes how a simple script can modify the `pyproject.toml` before a build step, resulting in named dependencies in the build artifacts.
This plugin only temporarily modifies the structure, in memory, just for the command you run it on.

## Contributing

We recommend using PyEnv to select the right Python version:

```console
pyenv local && poetry env use $(which python)
make venv
```

We use [pre-commit](https://pre-commit.com/), which most recent version requires Python >=3.9, while this project aims to work on Python >=3.8.
Therefore install pre-commit on your system yourself (using Homebrew / PipX)

Tests can be run with `make test`, linting with `make lint`

## License

This project is licensed under the terms of the MIT open-source license. Please refer to [MIT](https://github.com/gerbenoostra/poetry-plugin-mono-repo-deps/blob/HEAD/LICENSE) for the full terms.
