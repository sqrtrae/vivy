#!/usr/bin/env just --justfile
export PATH := join(justfile_directory(), ".env", "bin") + ":" + env_var('PATH')

alias s := sync
alias u := upgrade
alias t := test
alias ty := type-check
alias f := format

sync:
  uv sync --all-extras --all-groups --locked

upgrade:
  uv lock --upgrade

test:
  uv run pytest

type-check:
  uv run pyright

format:
  uv run ruff check --fix --config ./pyproject.toml
  uv run ruff format --config ./pyproject.toml
