default: help
.PHONY: help clean pre-commit lint test bump
VENV_DIR = .venv

help:
	@grep -E '^[a-zA-Z0-9 -]+:.*#'  Makefile | sort | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done

venv: ${VENV_DIR}/.touchfile

${VENV_DIR}/.touchfile: poetry.lock
	poetry sync || poetry install --sync
	touch ${VENV_DIR}/.touchfile

poetry.lock: pyproject.toml
	poetry lock --no-update || poetry lock
	touch poetry.lock

clean:
	rm -rf ${VENV_DIR}
	poetry run ruff clean

pre-commit: .git/hooks/pre-commit .git/hooks/commit-msg

.git/hooks/pre-commit:
	pre-commit install

.git/hooks/commit-msg:
	pre-commit install --hook-type commit-msg

lint: venv
	poetry run ruff check poetry_plugin_mono_repo_deps tests
	poetry run mypy --config-file pyproject.toml poetry_plugin_mono_repo_deps tests

test: venv
	NO_COLOR=1 poetry run python -m pytest --cov poetry_plugin_mono_repo_deps --cov-config pyproject.toml --cov-report xml:coverage/coverage.xml --cov-report term-missing  --junitxml=coverage/report.xml -vv -p no:toolbox tests

bump: venv
	poetry run cz bump --retry
