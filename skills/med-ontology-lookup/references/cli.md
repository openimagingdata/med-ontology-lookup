# molu CLI reference

Always prefer:

```bash
uv run molu <command> …
```

## Commands

| Command | Purpose |
|---|---|
| `molu search <query>` | Free-text search |
| `molu get <id>` | Concept by CUI or code |
| `molu crosswalk <query>` | CUI/code/term → source codes (UMLS) |
| `molu parents <id> -o ONTOLOGY` | Immediate parents |
| `molu children <id> -o ONTOLOGY` | Immediate children |
| `molu lookup <query>` | Auto-detect kind and run get or search |
| `molu version` | Package version |

## Common flags

| Flag | Applies to | Description |
|---|---|---|
| `-o / --ontologies` | search, lookup | Comma-separated BioPortal acronyms |
| `-o / --ontology` | get, parents, children | Single ontology/source |
| `-b / --backend` | search, get, parents, children | `auto` \| `bioportal` \| `umls` \| `both` |
| `-n / --limit` | search, lookup | Max hits |
| `--exact` | search, lookup | Exact match only |
| `--types` / `-t` | search | Type short-hands; **keeps** hits with empty/missing types |
| `--types-strict` / `-T` | search | Type short-hands; **drops** hits without a matching type |
| `--print-types` | search | Print short-hand semantic type table and exit |
| `--from-source` | crosswalk | SAB of input code |
| `--to-sources` | crosswalk | Target SABs |
| `-f / --output` | all | `table` (default) or `json` |

```bash
uv run molu search --print-types
```

## Ontology IDs

### BioPortal acronyms

| Acronym | Vocabulary |
|---|---|
| `RADLEX` | RadLex radiology lexicon |
| `SNOMEDCT` | SNOMED CT (BioPortal) |
| `FMA` | Foundational Model of Anatomy |
| `LOINC` | Logical Observation Identifier Names and Codes |

### UMLS source abbreviations (SABs)

| SAB | Notes |
|---|---|
| `SNOMEDCT_US` | US SNOMED CT edition in UMLS |
| `FMA` | Anatomy |
| `RADLEX` | Present for some concepts |
| `LNC` | LOINC |

Friendly names (`SNOMEDCT`, `SNOMED`, `LOINC`) are normalized to UMLS SABs on the UMLS client.

## Input shapes

| Pattern | Kind | Example |
|---|---|---|
| `C` + 7+ digits | CUI | `C0032326` |
| `RID` + digits | RadLex | `RID43255` |
| `FMA:digits` / `FMA_digits` | FMA | `FMA:7088` |
| 6–18 digit integer | Likely SNOMED | `36118008` |
| `digits-digits` | LOINC | `8867-4` |
| Multi-word / plain word | Term | `ground glass opacity` |

## Env vars

```bash
export BIOPORTAL_API_KEY=...   # or BIOONTOLOGY_API_KEY
export UMLS_API_KEY=...
# or: uv run --env-file=.env molu …
```

The tool reads the process environment only; it does not open `.env`.

Optional: `BIOPORTAL_BASE_URL`, `UMLS_BASE_URL`, `UMLS_VERSION` (default `current`).

## Example agent sequences

**Imaging finding → RadLex + SNOMED**

```bash
uv run molu search "subpleural nodule" -o RADLEX,SNOMEDCT -f json
uv run molu get <best_radlex_id> -o RADLEX -f json
uv run molu crosswalk <cui_if_known> --to-sources SNOMEDCT_US,RADLEX -f json
```

**Code in → labels and peers**

```bash
uv run molu lookup 36118008 -f json
uv run molu crosswalk 36118008 --from-source SNOMEDCT_US -f json
uv run molu parents 36118008 -o SNOMEDCT -f json
```
