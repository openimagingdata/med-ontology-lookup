# Plan: med-ontology-lookup v1 — Core Lookups

**Status:** complete  
**Date:** 2026-08-11  
**Goal:** Python library + CLI + agent skills for medical ontology term lookups via BioPortal and UMLS.

## Scope (v1)

| Capability | Backend | Notes |
|---|---|---|
| Search (term → ranked hits) | BioPortal + UMLS | Multi-ontology; exact match; semantic types |
| Get by ID / CUI | BioPortal + UMLS | Label, synonyms, definition, semantic types, UI link |
| CUI crosswalk | UMLS | CUI ↔ source codes (SNOMED, FMA, RadLex, …) |
| Parents / children (1 hop) | BioPortal (+ UMLS source IDs) | Disambiguate hierarchy level |
| Code / term / CUI auto-detect | Library | Route `RID…`, `C00…`, numeric codes vs free text |

**Default ontologies:** RADLEX, SNOMEDCT, FMA (BioPortal); UMLS search with optional SAB filters (`SNOMEDCT_US`, `FMA`, `RADLEX`).

**Out of scope for v1 (follow-ons):** text annotator, path-to-root dumps, local cache, bulk export, relationship graphs beyond is-a parents/children.

## Inspiration

Pattern from [findingmodel bioontology.py](https://github.com/openimagingdata/findingmodel/blob/75afd39a400419dcfaf7c8d4a34f065b4d804e0d/packages/findingmodel-ai/src/findingmodel_ai/search/bioontology.py):

- Async `httpx` client with optional injected client + context manager
- Pydantic models for results
- `Authorization: apikey token=…` for BioPortal
- Pagination helpers; parallel multi-query

## Architecture

```
CLI / agent skills
        │
        ▼
  OntologyLookup (facade)
   ├── detect_input()  → term | code | cui
   ├── BioPortalClient → search, get, parents, children
   └── UMLSClient      → search, get CUI, atoms/crosswalk, source parents/children
```

### Package layout

```
src/med_ontology_lookup/
  __init__.py          # public API
  models.py            # Concept, SearchHit, CrosswalkResult, …
  config.py            # API keys from env
  detect.py            # input kind detection
  service.py           # OntologyLookup facade
  clients/bioportal.py
  clients/umls.py
  cli.py               # typer CLI
```

### Config / secrets

| Env var | Purpose |
|---|---|
| `BIOPORTAL_API_KEY` | BioPortal REST API |
| `UMLS_API_KEY` | NLM UTS API key |

Either key may be missing; features requiring that backend raise a clear error.

### CLI surface

```
molu search "ground glass opacity" [--ontologies RADLEX,SNOMEDCT] [--backend bioportal|umls|both] [--exact] [--limit N]
molu get <id> [--ontology RADLEX|SNOMEDCT|FMA|UMLS]
molu crosswalk <cui_or_code> [--from-source SNOMEDCT_US] [--to-sources SNOMEDCT_US,FMA,RADLEX]
molu parents <id> --ontology RADLEX
molu children <id> --ontology RADLEX
molu lookup <query>   # auto-detect + sensible default action
# Prefer: uv run molu …
```

### Agent skills

- `skills/med-ontology-lookup/` — when/how to use the CLI and library for medical term coding (portable agent skill)
- Reference: CLI cheatsheet, ontology ID conventions, recommended agent workflow

## Implementation phases

1. **Plan doc** (this file) ✓
2. **Scaffold** — pyproject, package skeleton, models, config
3. **BioPortal client** — search, get class, parents, children
4. **UMLS client** — search, get CUI, atoms (crosswalk), source parents/children
5. **Facade + detect** — unified `OntologyLookup`
6. **CLI** — typer commands, JSON/table output
7. **Skills** — SKILL.md + CLI reference
8. **Tests** — unit tests with httpx mocks; detect tests
9. **Docs** — README, CHANGELOG, DEV_LOG; mark plan complete

## Success criteria

- `molu search "pneumothorax" --ontologies RADLEX` returns structured hits (with API key)
- `molu get C0009044` (or equivalent) resolves via UMLS
- `molu crosswalk C0009044` lists source codes
- `molu lookup RID43255` auto-routes as code lookup
- Agent skill documents the workflow agents should follow
- Tests pass offline with mocked HTTP

## Documentation updates (end of plan)

- [x] Mark this plan **complete**
- [x] README covers install, keys, library, CLI
- [x] CHANGELOG v0.1.0 entry for external users
- [x] DEV_LOG notes design decisions

## Follow-ons (explicitly deferred)

1. BioPortal text annotator
2. Path-to-root / deeper hierarchy
3. Match-quality scoring for agent ranking
4. Local cache / rate-limit handling
5. Parallel batch multi-term search as first-class CLI command
