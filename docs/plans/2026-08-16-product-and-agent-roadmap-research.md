# Product and Agent Roadmap Research

Status: complete

## Goal

Clarify the project's intended role, identify gaps against current biomedical terminology and ontology tooling, and recommend a prioritized roadmap with particular attention to graph operations and agent-friendly interfaces.

## Plan

- [x] Record this plan before beginning repository analysis or external research.
- [x] Inventory the package's current goals, interfaces, data sources, guarantees, tests, and documentation; account for the active review findings without modifying the in-progress implementation.
- [x] Research current primary documentation and representative implementations for biomedical terminology APIs, ontology graph access, interoperability standards, and agent/tool interfaces.
- [x] Compare the project to that landscape and identify high-value user and agent workflows, missing primitives, risks, and non-goals.
- [x] Produce a phased, dependency-aware roadmap with concrete API/tool shapes and acceptance criteria.
- [x] Review and update relevant documentation: complete this plan, add a durable research/roadmap document, and update `DEV_LOG.md` or `CHANGELOG.md` only if their established purpose and format call for it.

## Research questions

1. What problem is the package solving today, for whom, and through which interfaces?
2. Which gaps make current lookups unreliable, hard to compose, or difficult for an agent to discover and use safely?
3. Which graph primitives unlock real clinical, research, and coding workflows without turning the package into a graph database?
4. Which standards and response conventions would maximize interoperability and provenance?
5. What should be built now, later, or explicitly left to external infrastructure?

## Deliverables

- A concise statement of project goals and boundaries.
- A source-grounded landscape and gap analysis.
- A prioritized feature roadmap, including ontology graph capabilities.
- Concrete recommendations for agent-facing schemas, tools, examples, and evaluation coverage.

## Completion notes

Completed 2026-08-16. The durable result is `docs/product-roadmap.md`; the README now
links to it. The development log records the product decision. No changelog entry was
added because this research changes documentation and direction, not released behavior.

Addendum 2026-08-17: default profile is `radiology` (RadLex + LOINC Playbook +
SNOMED + FMA); `anatomy` includes RadLex; ICD is opt-in/`clinical`; CPT is
license-gated `billing-us` only (not BioPortal).
