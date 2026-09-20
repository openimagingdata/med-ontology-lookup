# Adopt `ty` and Evaluate Check Task Running

**Status:** complete
**Date:** 2026-09-14

## Goal

Make the repository's type check reproducible with a locked `ty` development dependency, replace
the stale Pyright references, and determine the smallest current task-running approach for the
project's local and CI checks.

## Plan

- [x] Record this executable plan in `docs/plans/` before changing project configuration.
- [x] Inspect the current dependency, lockfile, documentation, and check-command surfaces.
- [x] Research current official guidance for `ty`, `uv`, Taskfile, and credible Python-native
  check orchestration options; choose based on reproducibility, maintenance, and local/CI parity.
- [x] Add `ty` as a development dependency and replace Pyright commands/references with
  `uv run ty check`.
- [x] Add the selected thin Taskfile over locked `uv` commands, including standard checks, safe
  fixes, the supported-Python test matrix, builds, and a full verification entry point.
- [x] Run `ty`, tests, Ruff, build/metadata, installed-wheel, CLI, and supported-Python checks.
- [x] Update this plan, relevant reference documentation, `DEV_LOG.md`, and `CHANGELOG.md` where an
  outside user-visible change actually exists.
- [x] Perform a final documentation review, mark this plan complete, and record the authorized
  Taskfile decision.

## Completion notes

`ty>=0.0.80` is now a development dependency, with version 0.0.80 resolved exactly in `uv.lock`.
The lockfile and `uv run --locked` make the checker reproducible without duplicating the resolved
version as a direct project constraint. The project proposal, issue #3 plan, README, and development
log now use `uv run ty check` rather than an environment-dependent Pyright command.

The former published `dev` extra was moved to the standardized PEP 735 `dev` dependency group.
`uv` includes that group in `uv sync` and `uv run` by default, so Taskfile checks bootstrap their
locked tools from a clean checkout without publishing test tools as an installable package extra.

Current `uv` includes an experimental `uv check`, which invokes `ty`, plus `uv format`, which
invokes Ruff's formatter. It does not currently provide arbitrary project task aliases or aggregate
Ruff, pytest, build, and smoke checks under `uv check`.

For this small `uv`-managed package, Nox would duplicate environment and dependency orchestration.
Poe could keep aliases and composition in `pyproject.toml`, but Taskfile supplies the requested
thin, language-neutral command graph without taking ownership of environments. The added
`Taskfile.yml` delegates every Python operation to locked `uv` commands: `task check` covers the
normal offline gate, `task test-matrix` covers Python 3.11–3.14, `task fix` applies Ruff changes,
and `task verify` combines checks, the matrix, and package builds.

Final verification completed with Task 3.53.1, `ty` 0.0.80, and Ruff 0.16.7. `task verify` passed:
the lockfile was current, format/lint/type checks were clean, all 121 tests passed on the active
environment and independently on Python 3.11, 3.12, 3.13, and 3.14, and both distribution artifacts
built successfully. Twine metadata validation, installed-wheel imports, CLI smoke checks, and
`git diff --check` also passed. `CHANGELOG.md` did not need another entry because this changes only
developer tooling, not installed-library or CLI behavior.
