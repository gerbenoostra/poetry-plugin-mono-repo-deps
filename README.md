# Poetry plugin to Pin Path dependencies

A [**Poetry**](https://python-poetry.org/) plugin for Poetry mono repositories.
Poetry mono-repositories rely on path dependencies for dependencies within the mono repo.
During building, this plugin will replace these dependencies in the final artifact (zip/wheel) with named dependencies.
It uses the semantical compatible version range.

For example, if you have 2 libraries in a mono-repo.

One common utility library:

```{toml}
# repo/A/pyproject.toml
[tool.poetry]
name = "library-A"
version = "3.2.1"
```

And another library or application that depends on the common utility:

```{toml}
# repo/B/pyproject.toml
[tool.poetry]
name = "app-B"

[tool.poetry.dependencies]
library-a = {path = "../A", develop=true}
```

When building App-B to a wheel/zip, it will define the dependency of B->A as follows:

```
library-a~=3.2.1
```

## Installation

Add the plugin to poetry:

```shell
poetry self add poetry-plugin-pin-path-deps
```

If you used pipx to install Poetry, you can use:

```
pipx inject poetry poetry-plugin-pin-path-deps
```

If you used pip to install Poetry, you can use:

```
pip install poetry-plugin-pin-path-deps
```

## Development of the plugin

We recommend to use pyenv to select the right python version:

```
pyenv local && poetry env use $(which python)
make venv
```

We use pre-commit, which works on python>=3.9, while this project aims to work on python>=3.8.
Therefore install it on your system yourself (using brew / pipx)
