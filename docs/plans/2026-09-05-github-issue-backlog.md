# GitHub Issue Backlog

**Status:** complete
**Date:** 2026-09-05
**Goal:** Incorporate independent review of the project proposal and create a dependency-ordered, independently reviewable GitHub backlog for trustworthy lookup contracts and delegated authentication.

## Plan

- [x] Record this plan before editing the proposal or creating GitHub issues.
- [x] Obtain an independent `gpt-6-astra` review of the proposal and proposed issue breakdown.
- [x] Reconcile the durable proposal with accepted review findings, including sequencing, fallback classification, backend selection, collection semantics, crosswalk scope, delegated credential guarantees, and diagnostic uncertainty.
- [x] Create one self-contained tracking issue and focused implementation issues with scope, acceptance criteria, dependencies, non-goals, verification, and documentation obligations.
- [x] Verify the created issue hierarchy and links without assuming the locally committed proposal is already available on GitHub.
- [x] Review and update this plan and `DEV_LOG.md`; update `CHANGELOG.md` only if released behavior changed.

## Backlog shape

Tracking: [#1 — Deliver trustworthy lookup contracts and delegated authentication](https://github.com/openimagingdata/med-ontology-lookup/issues/1)

1. [#2 — Offline CI and reproducible development checks](https://github.com/openimagingdata/med-ontology-lookup/issues/2).
2. [#3 — Typed provider failures and operation-aware fallback](https://github.com/openimagingdata/med-ontology-lookup/issues/3).
3. [#4 — Explicit backend selection and readiness](https://github.com/openimagingdata/med-ontology-lookup/issues/4).
4. [#5 — Shared identifier/source normalization and identity preservation](https://github.com/openimagingdata/med-ontology-lookup/issues/5).
5. [#6 — Bounded, honest collection semantics](https://github.com/openimagingdata/med-ontology-lookup/issues/6).
6. [#7 — Request and terminology provenance with explicit version uncertainty](https://github.com/openimagingdata/med-ontology-lookup/issues/7).
7. [#8 — Ambiguity-preserving, evidence-labeled UMLS expansion](https://github.com/openimagingdata/med-ontology-lookup/issues/8).
8. [#9 — Direct and delegated provider endpoints](https://github.com/openimagingdata/med-ontology-lookup/issues/9).
9. [#10 — Opt-in live provider and Aperture contract checks](https://github.com/openimagingdata/med-ontology-lookup/issues/10).
10. [#11 — Bounded provider diagnostics](https://github.com/openimagingdata/med-ontology-lookup/issues/11).
11. [#12 — Hardened release preparation and explicit publication checkpoint](https://github.com/openimagingdata/med-ontology-lookup/issues/12).

## Completion notes

The tracking issue and eleven focused issues were created and checked on GitHub. Their bodies are
self-contained because commit `3683738`, which first records the repository proposal, has not
been pushed to `origin/main`. No product code or released behavior changed, so `CHANGELOG.md` did
not require an entry.

An independent `gpt-6-astra` review changed the backlog materially: required offline CI moved to
the foundation alongside typed failures; backend selection and collection semantics gained
explicit owners; generic mapping work was removed from the immediate UMLS expansion issue; and
delegated authentication now guarantees credential absence in final outgoing requests while
preserving the Aperture connector prefix through pagination.
