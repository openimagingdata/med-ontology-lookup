# Project Review and Authentication Proxy Proposal

**Status:** complete
**Date:** 2026-09-03
**Goal:** Turn the repository audit into a coherent, prioritized product and engineering proposal, including optional use of Tailscale Aperture so upstream credentials can remain at a trusted proxy instead of in each client environment.

## Plan

- [x] Record this plan before beginning proposal work.
- [x] Verify Tailscale Aperture's current deployment, routing, and credential-injection contract from primary sources.
- [x] Reconcile the existing implementation, tests, release state, and product roadmap into one evidence-backed assessment.
- [x] Define a small configuration and transport seam supporting direct authenticated providers and trusted credential-injecting proxies without leaking deployment concerns into lookup operations.
- [x] Produce a prioritized proposal with phases, acceptance criteria, risks, and explicit non-goals.
- [x] Review all relevant documentation: link the proposal from the README, update this plan and the development log to reflect the final state, and update the changelog only if released user behavior changed.

## Deliverables

- A durable review/proposal document under `docs/`.
- A concrete direct-versus-proxy configuration contract.
- A sequenced backlog that begins with contract hardening and release readiness.
- Documentation reconciled with the final proposal.

## Completion notes

Completed 2026-09-03. The durable result is `docs/project-review-and-proposal.md`.
The README links to it and `DEV_LOG.md` records the resulting product and deployment
decisions. `CHANGELOG.md` was not changed because the work proposes future behavior but does
not change the released package.
