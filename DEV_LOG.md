# Development log

## 2026-08-11 — v0.1 scaffold

### Decisions

- **Standalone package** rather than extracting from findingmodel; inspired by findingmodel’s async BioPortal client (httpx + Pydantic + context manager).
- **Two backends, one facade**: BioPortal for multi-ontology class search/hierarchy; UMLS for CUI hub and crosswalk. `backend=auto` prefers BioPortal for search when both keys exist.
- **v1 surface**: search, get, crosswalk, parents/children, input auto-detect. Deferred: annotator, path-to-root, local cache, relationship graphs.
- **Ontology defaults**: RADLEX, SNOMEDCT, FMA (BioPortal); crosswalk SABs SNOMEDCT_US, FMA, RADLEX.
- **CLI name** `molu` (med ontology lookup) via Typer + Rich tables / JSON; run with `uv run molu`.
- **Agent skill** lives in-repo under `skills/` (not vendor-specific dirs like `.grok/`) so any agent runtime can load it.

### Layout

```
src/med_ontology_lookup/
  clients/bioportal.py
  clients/umls.py
  service.py      # OntologyLookup
  detect.py
  models.py
  config.py
  cli.py
```

### Keys

- BioPortal: `Authorization: apikey token=…`
- UMLS: `apiKey` query parameter on each request (current NLM auth model)
- Also accept `BIOONTOLOGY_API_KEY` as alias for BioPortal (findingmodel convention) — see config if added.

### 2026-08-12 — empty search after BioPortal key fix

- BioPortal `/search` returned **400** because `include` contained `obsolete` (only allowed on class detail: prefLabel, synonym, definition, notation, cui, semanticType, properties).
- Facade swallowed exceptions → empty table / `backend: null`. Fixed include list; re-raise when all backends fail.

### 2026-08-12 — balanced ontologies + semantic type UX

- Multi-ontology BioPortal search ranked SNOMED over RADLEX even for exact RadLex matches (“right hepatic duct”). Fix: `search_balanced` queries each ontology in parallel, then round-robins.
- Result merge interleaves by **ontology** (not only backend) so RADLEX/FMA/LOINC/SNOMED/UMLS stay visible.
- LOINC added to default BioPortal ontologies and UMLS crosswalk SABs (`LNC`).
- Semantic types: `resolve_semantic_types()` accepts names/aliases; CLI `molu semantic-types` for discovery.
- CLI renamed from `mol` → `molu` (uv-first usage).

### 2026-08-12 — review fixes

- BioPortal short codes (RID…, SNOMED, FMA digits) resolved to full IRIs before `/classes/{cls}` (and parents/children).
- Search merge keeps API relevance order within ontology groups (exact-first partition only).
- Crosswalk no longer falls back to all preferred atoms when `to_sources` is empty for that filter.
- `_short_code` prefers URI fragments over path segments.
- LOINC/digit-leading compact codes recognized by `detect_input` (e.g. `8867-4`).

### 2026-08-16 — review follow-up

- WIP commit `8dd0a08`, then: redact `apiKey` in errors; `_class_exists` raises on auth/rate-limit/5xx; no cache of resolve misses; exact IRI/code match only; search SAB→BioPortal map; `SearchResults.warnings`; blank API keys treated as unset (`env_ignore_empty`).
- Confidence tests: SAB mapping, partial-ontology warnings, Settings alias fallback, resolve suffix false-positive.
- Settings no longer auto-load `.env`; keys come from the process environment (`uv run --env-file=.env` if needed).

### 2026-08-16 — product and graph roadmap research

- Position the package as an agent-ready medical terminology graph gateway, not an ontology repository or general graph database.
- Sequence reliability and version/provenance contracts before bounded graph traversal, typed mappings, similarity, or local graph analytics.
- Recommend native MCP tools/resources, domain profiles, text annotation and batch operations, a common node/edge envelope, FHIR terminology semantics, and SSSOM-compatible mapping evidence.
- Keep OLS/OAK/Snowstorm/FHIR servers as adapters or optional backends instead of rebuilding their storage and reasoning machinery.

### 2026-08-17 — profile defaults (roadmap)

- Default profile is **`radiology`**: RadLex + LOINC (Playbook-weighted) + SNOMED CT + FMA; UMLS as hub.
- LOINC/RSNA Radiology Playbook is first-class for orderables; findings/anatomy stay RadLex-led.
- **`anatomy`** includes RadLex alongside FMA, Uberon, SNOMED.
- ICD-10-CM/PCS: `clinical` / `billing-us` / explicit add-on — not radiology default.
- CPT: UMLS-only, license-gated `billing-us`; BioPortal does not serve CPT.

### 2026-09-03 — project review and authentication proxy proposal

- Confirmed the v0.1 implementation as a sound lookup nucleus and prioritized contract hardening before MCP or broader graph work.
- Proposed explicit `direct` and `delegated` provider authentication modes so the same lookup interface can use local API keys or a credential-injecting proxy such as Tailscale Aperture.
- Kept proxy behavior at the HTTP/authentication seam: endpoint selection and credential handling change, while search, lookup, and graph semantics do not.
- Identified UMLS user-license validation as a deployment gate for shared proxy credentials rather than assuming technical reachability implies license compliance.
- Recorded release-readiness, agent workflow, and bounded graph phases in `docs/project-review-and-proposal.md`.

### 2026-09-05 — reviewed implementation backlog

- Had the proposal and issue breakdown independently reviewed with `gpt-6-astra`, then incorporated its contract, sequencing, and security concerns.
- Moved offline CI alongside typed provider-failure handling as parallel foundation work; separated live contracts and release publication into later explicit checkpoints.
- Tightened delegated authentication so final outgoing requests cannot inherit client-side provider credentials and every paginated request remains under its Aperture connector prefix.
- Created tracking issue [#1](https://github.com/openimagingdata/med-ontology-lookup/issues/1) and dependency-ordered implementation issues [#2–#12](https://github.com/openimagingdata/med-ontology-lookup/issues?q=is%3Aissue%20state%3Aopen%20sort%3Acreated-asc).

### 2026-09-14 — typed provider failures and fallback policy

- Added a public adapter-to-facade failure contract carrying provider, operation, category,
  sanitized endpoint, optional HTTP status, conservative status origin, and ontology context.
- Limited fallback to typed `not_found` and `unsupported_operation` outcomes. Authentication,
  authorization, rate-limit, upstream, transport, and malformed-response failures remain visible.
- Retained canonical provider `404` handling for resource endpoints as a narrow compatibility rule,
  while custom endpoint `404` responses remain unknown-origin HTTP failures. Kept the BioPortal
  bare-code `400` probe only for its bounded parsed `not a valid IRI` signal.
- Replaced broad concurrent exception collection with a helper that records only typed provider
  failures, counts valid empty calls as successes, and propagates unexpected exceptions and task
  cancellation after cleaning up sibling tasks.
- Added minimum success-payload validation beside each adapter mapper, structured partial failures
  on search results, and credential-safe CLI JSON errors. The executable plan incorporates two
  rounds of independent `gpt-6-astra` review.

### 2026-09-14 — adopt `ty` for reproducible type checks

- Replaced the undocumented local Pyright invocation with `ty>=0.0.80` in the locked development
  dependencies and made `uv run ty check` the documented repository check.
- Kept exact tool versions in `uv.lock` rather than duplicating them as direct constraints in
  `pyproject.toml`; upgrades remain explicit and independently verified.
- Confirmed that current `uv` also provides an experimental `uv check` command backed by `ty`, but
  it does not yet orchestrate Ruff, pytest, builds, and smoke checks. Nox was rejected as too much
  overlapping environment machinery for this project.
- Added a thin Taskfile over locked `uv` commands. `task check` is the normal lock/format/lint/type/
  test entry point; `task test-matrix` covers Python 3.11–3.14; `task verify` adds the matrix and
  package build. Development tools now use the standardized PEP 735 `dev` dependency group, which
  `uv` syncs by default, with exact Ruff and `ty` versions resolved in `uv.lock`.
