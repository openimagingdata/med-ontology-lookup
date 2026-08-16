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
