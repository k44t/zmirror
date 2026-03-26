# AGENTS Guide for zmirror

This file is for coding agents working in this repository.

## Project overview

- `zmirror` is a Python CLI + daemon for managing ZFS mirror backup devices (including LUKS/dm-crypt backed devices).
- The daemon consumes udev/ZED-like events, updates in-memory/cache entity state, then schedules and executes shell commands (`zpool`, `zfs`, `cryptsetup`, etc.).
- Configuration is YAML-driven (`example-config.yml` is the canonical reference).

## Repo layout

- `zmirror/zmirror.py`: CLI parser and command wiring.
- `zmirror/daemon.py`: unix-socket server + event loop + event dispatch.
- `zmirror/dataclasses.py`: core domain model (entities, requests, operations, state transitions).
- `zmirror/entities.py`: config/cache initialization and system probing wrappers.
- `zmirror/user_commands.py`: user/daemon command handlers.
- `zmirror/commands.py`: command queue and execution wrapper.
- `tests/commands/` and `tests/requests/`: high-coverage event-sequence behavior tests.
- `tests/util/`: test stubs/helpers that replace system interactions.

## Setup and local validation

- Install deps: `poetry install`
- Run tests: `poetry run pytest`
- Run one test module: `poetry run pytest tests/commands/test_commands.py`
- Run CLI entrypoint: `poetry run python -m zmirror --help`

## Coding conventions used here

- Use 2-space indentation in Python files (see `.pylintrc`).
- Prefer existing patterns over refactors; this codebase has intentionally stateful/event-driven flow.
- Keep functions and variables `snake_case`.
- Avoid adding broad architectural abstractions unless they remove concrete duplication already present.
- Keep logging explicit and operational (many tests and debugging flows depend on observable behavior).

## Safety and behavior constraints

- Do not run destructive storage commands on a real host during development.
- Tests are designed to stub command execution; favor tests over manual system-level verification.
- Preserve request/state semantics: `EntityState`, `Operation`, `RequestType`, and cache/config entity mapping are tightly coupled.
- Be careful when changing event handling order in `daemon.py`; many tests assert exact command sequencing.

## When making changes

- Limit edits to the smallest coherent unit.
- If CLI behavior changes, update argparse wiring in `zmirror/zmirror.py` and related handlers in `zmirror/user_commands.py`.
- If state transition logic changes, add or update sequence tests in `tests/commands/` or `tests/requests/`.
- If config fields or defaults change, keep `example-config.yml` aligned.

## Known practical notes

- Development commonly depends on a local path dependency `../kpyutils` from `pyproject.toml`.
- The deployed stow package directory for this project is `/#/system/zmirror`.
- Systemd units for this package are under `/#/system/zmirror/etc/systemd/system/` (for example, `zmirror-local-fs.service`).
- The repository may contain generated/temp artifacts (`temp/`, `__pycache__/`, etc.); avoid relying on them.
