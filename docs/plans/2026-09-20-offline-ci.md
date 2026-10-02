# Offline CI and Reproducible Development Checks

**Status:** implementation complete; awaiting hosted verification
**Date:** 2026-09-20
**Issue:** [#2 — Add offline CI and reproducible development checks](https://github.com/openimagingdata/med-ontology-lookup/issues/2)

## Goal

Make every pull request run the same credential-free checks contributors can run locally: locked
formatting, linting, type checking, tests on Python 3.11–3.14, distribution validation, and smoke
tests against the installed wheel rather than the source checkout.

## Plan

- [x] Write this executable plan under `docs/plans/` before changing CI, task, dependency, or
  contributor-documentation surfaces.
- [x] Inspect the merged Taskfile, locked development dependencies, supported Python range,
  packaging configuration, current documentation, and issue #2 acceptance criteria.
- [x] Research current official guidance for uv in GitHub Actions, Task installation, immutable
  action pinning, supported-Python matrices, and clean distribution builds.
- [x] Reconcile issue #2 with the already-adopted `ty` and Taskfile decisions so its contract no
  longer calls for Pyright.
- [x] Extend `Taskfile.yml` with independently callable static-analysis and package-verification
  tasks while keeping each task a thin wrapper over locked `uv` commands.
- [x] Add any package-validation tool to the `dev` dependency group and refresh `uv.lock` so local
  and hosted checks use the same resolved toolchain.
- [x] Add a least-privilege GitHub Actions workflow with:
  - one static-analysis job;
  - an independent Python 3.11, 3.12, 3.13, and 3.14 test matrix;
  - one clean build, metadata, installed-wheel import, and CLI smoke job;
  - no provider credentials or live provider requests.
- [x] Pin every external action to a full commit SHA with its release tag in a comment, enable uv
  caching from `uv.lock`, disable matrix fail-fast, bound job runtime, and cancel superseded branch
  runs.
- [x] Update README contributor commands and the project review so the documented local equivalents
  and CI status match the workflow exactly.
- [x] Run the focused tasks and full local verification, validate the workflow structure, and check
  the worktree diff for accidental secrets or unrelated changes.
- [x] Update this plan and `DEV_LOG.md` with the final decisions and evidence. Update
  `CHANGELOG.md` only if installed-library or CLI behavior changes.
- [x] Perform a final documentation review and reconcile README, the project review, `DEV_LOG.md`,
  and `CHANGELOG.md` with the implemented behavior.
- [ ] After explicit commit authorization, publish the branch, open a pull request, inspect a
  successful GitHub Actions run, and mark this plan complete.

## Finalization on 2026-10-02

The user authorized completing, committing, publishing, and merging issue #2.

- [x] Resolve Hatchling through `uv.lock` and build using the synchronized development environment.
- [x] Install the wheel with locked runtime dependencies and verify its import outside the checkout.
- [x] Validate workflow syntax and security, and rerun the affected checks.
- [ ] Open the PR, inspect its review and all six hosted jobs, and address confirmed findings.
- [ ] Record hosted verification, merge the PR, verify the main-branch run, and close the plan.

## Current decisions

- Use the existing Taskfile as the local/CI interface; workflows invoke named tasks rather than
  duplicating Python commands in YAML.
- Use `ty`, not the stale Pyright wording in issue #2. `ty` and Ruff remain resolved by `uv.lock`.
- Use the official `astral-sh/setup-uv` and `go-task/setup-task` actions. Pin all actions by full
  immutable SHA, following GitHub secure-use guidance.
- Let `astral-sh/setup-uv` select each matrix interpreter and manage the uv cache. Do not combine it
  with redundant `actions/setup-python` or pip caching.
- Build with `uv run --locked -- uv build --no-build-isolation --clear`. Hatchling and its
  dependencies come from the synchronized development environment, and stale artifacts are cleared.
- Install the wheel into an isolated environment and run smoke commands outside the project
  environment so the source checkout cannot mask packaging defects. Export runtime dependencies
  from `uv.lock`, install them with hash validation, and install the wheel without resolving again.

## Research record

- uv recommends `astral-sh/setup-uv`, supports selecting matrix Python versions through that action,
  and provides lock-aware built-in caching:
  <https://docs.astral.sh/uv/guides/integration/github/>.
- Task documents `go-task/setup-task` as its official GitHub Actions installer:
  <https://taskfile.dev/docs/installation>.
- GitHub states that a full-length commit SHA is the only immutable way to pin an action:
  <https://docs.github.com/en/actions/reference/security/secure-use>.
- uv documents `uv build --clear` for removing stale output before building:
  <https://docs.astral.sh/uv/reference/cli/#uv-build>.
- Releases verified on 2026-09-20: `actions/checkout` v7.0.1,
  `astral-sh/setup-uv` v10.1.0, and `go-task/setup-task` v2.2.0.
- uv documents preinstalled build dependencies and exporting locked dependencies:
  <https://docs.astral.sh/uv/reference/cli/>.

## Constraints

- Required CI must never depend on BioPortal, UMLS, Aperture, repository secrets, or live network
  calls after dependencies and actions are installed.
- The workflow must not publish packages, create releases, mutate repository contents, or request
  write permissions.
- Development-tool changes belong in the standardized `dev` dependency group and lockfile, not in
  the installed package dependencies.
- Hosted verification cannot be claimed complete until the committed workflow has run on GitHub.

## Local verification

- `task static` passed the lockfile, Ruff formatting, Ruff lint, and `ty` checks.
- `task verify` passed all 121 tests independently on Python 3.11, 3.12, 3.13, and 3.14; built a
  clean wheel and source distribution; passed Twine metadata validation; and passed isolated-wheel
  import and `molu --help` smoke checks.
- `zizmor` 1.30.1 reported no findings after checkout credential persistence was disabled in every
  job.
- `git diff --check` passed. `CHANGELOG.md` remains unchanged because the installed library and CLI
  behavior did not change.
- On 2026-10-02, `task verify` passed again with the locked build backend and runtime dependencies.
  actionlint 1.7.12 and zizmor 1.30.1 passed. The wheel import resolved to the temporary environment's
  `site-packages`; both `molu --help` and `molu version` passed.
