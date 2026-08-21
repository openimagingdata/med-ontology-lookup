---
name: med-ontology-lookup
description: >
  Look up medical terms and codes in RadLex, SNOMED-CT, FMA, LOINC, and UMLS via the
  molu CLI / med-ontology-lookup Python library (BioPortal + UMLS APIs). Use when
  coding radiology findings, mapping clinical terms to ontology IDs, resolving
  CUIs, crosswalking between vocabularies, checking parents/children, or when
  the user asks for medical ontology lookup or mentions RadLex, SNOMED, FMA,
  UMLS, LOINC, BioPortal, or coding clinical/radiology terms.
---

# Medical ontology lookup

Use the **`molu`** CLI via **`uv run molu`** (or `med_ontology_lookup.OntologyLookup`
in Python) for term/code lookups. Do not scrape BioPortal/UTS UIs.

## Prerequisites

- From the repo root, prefer: `uv run molu …` (installs/uses the project env).
- Or: `uv sync --extra dev` then `molu` on PATH.
- Env vars (at least one) must already be in the process environment. The tool does not load `.env`.
  - `BIOPORTAL_API_KEY` (or `BIOONTOLOGY_API_KEY`) — [BioPortal account](https://bioportal.bioontology.org/account)
  - `UMLS_API_KEY` — [UTS profile](https://uts.nlm.nih.gov/uts/profile) (UMLS license required)
  - To inject a file: `uv run --env-file=.env molu …`

If a command fails with a missing-key error, tell the user which key to set.

## Agent workflow

1. **Classify the input**
   - Free text → `uv run molu search` or `uv run molu lookup`
   - `C` + 7+ digits → CUI → `uv run molu get` / `uv run molu crosswalk`
   - `RID…` → RadLex code → `uv run molu get -o RADLEX` or `uv run molu lookup`
   - Long digit string → likely SNOMED → `uv run molu get -o SNOMEDCT` or crosswalk with `--from-source SNOMEDCT_US`
   - `FMA:123` / `FMA_123` → FMA

2. **Search first for terms**
   ```bash
   uv run molu search "ground glass opacity" -o RADLEX,SNOMEDCT -n 15 -f json
   ```
   Prefer JSON (`-f json`) when parsing programmatically.

3. **Confirm a candidate**
   ```bash
   uv run molu get RID43255 -o RADLEX -f json
   uv run molu get C0032326 -f json
   ```

4. **Crosswalk when mapping systems**
   ```bash
   uv run molu crosswalk C0032326 --to-sources SNOMEDCT_US,FMA,RADLEX -f json
   uv run molu crosswalk 36118008 --from-source SNOMEDCT_US -f json
   ```

5. **Hierarchy when level is ambiguous**
   ```bash
   uv run molu parents <id> -o RADLEX -f json
   uv run molu children <id> -o SNOMEDCT -f json
   ```

6. **Smart one-shot**
   ```bash
   uv run molu lookup "pneumothorax" -f json
   uv run molu lookup C0032326 -f json
   uv run molu lookup RID43255 -f json
   ```

## Defaults

| Setting | Value |
|---|---|
| BioPortal ontologies | `RADLEX`, `SNOMEDCT`, `FMA`, `LOINC` |
| UMLS crosswalk SABs | `SNOMEDCT_US`, `FMA`, `RADLEX`, `LNC` |
| Search backend (`auto`) | All configured backends (BioPortal + UMLS when both keys set) |
| Semantic types | Short-hands (`disease`, `anatomy`); `-t` keeps untyped hits, `-T` requires a match; `uv run molu search --print-types` |

## Selection guidance

- Prefer **exact label matches** when present (`exact_match` in JSON).
- Prefer the ontology the user asked for (e.g. RadLex for imaging findings).
- For clinical interoperability, include **SNOMEDCT** / **SNOMEDCT_US**.
- For anatomy, include **FMA**.
- For labs/observations, include **LOINC**.
- Report **code + ontology + preferred label + CUI** (when available) in answers.
- Do not invent codes. If search is empty, say so and try alternate synonyms or the other backend (`-b umls` / `-b bioportal` / `-b both`).

## Python (when embedding)

```python
from med_ontology_lookup import OntologyLookup

async with OntologyLookup() as client:
    hits = await client.search("pneumothorax", ontologies=["RADLEX", "SNOMEDCT"])
    concept = await client.get("C0032326")
    xwalk = await client.crosswalk("C0032326")
```

## More detail

See [references/cli.md](references/cli.md) for full CLI flags and ID conventions.
