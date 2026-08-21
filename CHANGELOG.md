# Changelog

## 0.1.2 — 2026-08-16

- Read API keys from the process environment only (no automatic `.env` load). Use `uv run --env-file=.env molu …` if you want a file.
- Redact UMLS `apiKey` from CLI/HTTP error messages.
- BioPortal class-existence checks raise on 401/429/5xx instead of treating them as missing; failed IRI resolutions are not cached.
- Search maps UMLS SABs (`SNOMEDCT_US`, `LNC`) to BioPortal acronyms.
- Partial backend/ontology failures print as warnings instead of disappearing.
- Empty `BIOPORTAL_API_KEY=` no longer shadows `BIOONTOLOGY_API_KEY`.

## 0.1.1 — 2026-08-12

- CLI entry point renamed to **`molu`** (use `uv run molu …`).
- Agent skill lives under portable **`skills/med-ontology-lookup/`** (not a vendor-specific directory).
- Default ontologies now include **LOINC** (with RadLex, SNOMEDCT, FMA).
- BioPortal search queries **each ontology separately** and interleaves results so large sources (SNOMED) no longer hide RadLex/FMA/LOINC hits.
- Semantic type filters use **short-hands** (`disease`, `finding`, `anatomy`, …); `molu search --print-types` prints the table (no T-codes in the UX).
- `-t` / `--types` keeps untyped hits; `-T` / `--types-strict` requires a matching type.
- Accept `BIOONTOLOGY_API_KEY` as an alias for the BioPortal key.
- Search uses all configured backends by default; surface API errors instead of empty silent results.

## 0.1.0 — 2026-08-11

- Initial release: library + CLI for medical ontology lookups.
- BioPortal backend: search, get class, parents, children (default ontologies: RADLEX, SNOMEDCT, FMA).
- UMLS backend: search, get CUI, definitions, atoms/crosswalk, source parents/children.
- Unified `OntologyLookup` facade with term/code/CUI auto-detection (`lookup`).
- Agent skill at `skills/med-ontology-lookup/` (runtime-agnostic).
- Configure via `BIOPORTAL_API_KEY` and `UMLS_API_KEY`.
