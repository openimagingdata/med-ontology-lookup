# med-ontology-lookup

Python library and CLI for looking up medical terms in **RadLex**, **SNOMED-CT**, **FMA**, and **UMLS** using the [BioPortal](https://bioportal.bioontology.org/) and [UMLS Terminology Services](https://uts.nlm.nih.gov/) REST APIs.

## Features (v0.1)

- **Search** free-text terms across RadLex, SNOMED-CT, FMA, LOINC, and UMLS  
- **Balanced multi-ontology results** (per-ontology BioPortal queries so SNOMED does not crowd out RadLex)  
- **Get** a concept by CUI, RadLex RID, SNOMED code, or FMA id  
- **Crosswalk** via UMLS CUIs to codes in other vocabularies  
- **Parents / children** (one hop) for hierarchy checks  
- **Semantic type filters by short-hand** (`-t disease` keeps untyped hits; `-T` requires a match)  
- **Auto-detect** whether input is a term, code, or CUI (`molu lookup`)  
- **Agent skill** under `skills/med-ontology-lookup/` (portable across agent runtimes)

## Install

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv sync --extra dev
```

Or with pip:

```bash
pip install -e ".[dev]"
```

Requires Python 3.11+.

## API keys

| Variable | Where to get it |
|---|---|
| `BIOPORTAL_API_KEY` | [BioPortal account](https://bioportal.bioontology.org/account). `BIOONTOLOGY_API_KEY` is an alias. Leave the primary unset rather than empty. |
| `UMLS_API_KEY` | [UTS profile](https://uts.nlm.nih.gov/uts/profile) (UMLS license) |

Export them in the shell, or let uv inject a file (the tool does **not** read `.env` itself):

```bash
export BIOPORTAL_API_KEY=…
export UMLS_API_KEY=…
uv run molu search "pneumothorax"

# or
uv run --env-file=.env molu search "pneumothorax"
```

You can use either key alone; crosswalk and CUI resolution need UMLS. Multi-ontology class search and BioPortal hierarchy need BioPortal. With both keys set, `molu search` (backend `auto`) queries **both** APIs and merges results.

## CLI

Prefer **`uv run molu`** so the project environment and entry point stay in sync:

```bash
# Search (defaults: RADLEX, SNOMEDCT, FMA, LOINC + UMLS when keys set)
uv run molu search "ground glass opacity" -n 10
uv run molu search "pneumothorax" -o SNOMEDCT --exact -f json
uv run molu search "fever" -t disease,finding          # keep untyped hits too
uv run molu search "fever" -T disease                  # require matching type
uv run molu search --print-types

# Get by id
uv run molu get C0032326
uv run molu get RID43255 -o RADLEX

# Crosswalk (UMLS)
uv run molu crosswalk C0032326 --to-sources SNOMEDCT_US,FMA,RADLEX
uv run molu crosswalk 36118008 --from-source SNOMEDCT_US

# Hierarchy
uv run molu parents RID43255 -o RADLEX
uv run molu children 36118008 -o SNOMEDCT

# Auto-detect
uv run molu lookup "subpleural nodule" -f json
uv run molu lookup C0032326
```

After `uv sync` / install, `molu` is also available on the environment PATH.

## Library

```python
import asyncio
from med_ontology_lookup import OntologyLookup

async def main():
    async with OntologyLookup() as mol:
        hits = await mol.search("pneumothorax", ontologies=["RADLEX", "SNOMEDCT"])
        for h in hits.results:
            print(h.ontology, h.code, h.pref_label, h.exact_match)

        concept = await mol.get("C0032326")
        print(concept.pref_label, concept.semantic_types)

        xwalk = await mol.crosswalk("C0032326")
        for sc in xwalk.source_codes:
            print(sc.source, sc.code, sc.name)

asyncio.run(main())
```

## Agent skill

Portable skill package: [`skills/med-ontology-lookup/`](skills/med-ontology-lookup/).

Point your agent runtime at that directory (or copy/symlink it into the runtime’s skills path). It documents when and how to run `uv run molu` for ontology lookups—not tied to any single agent product.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests mock HTTP with `respx` (no live API keys required).

## License notes

This tool only calls remote APIs. **SNOMED CT** and **UMLS** content are subject to their respective licenses; obtain a UMLS license before using UMLS/SNOMED data in production. RadLex and FMA have their own terms via BioPortal.

## Roadmap

See the [product and graph roadmap](docs/product-roadmap.md) for the recommended direction:
an agent-ready terminology gateway with a **radiology default profile** (RadLex +
LOINC/RSNA Playbook + SNOMED + FMA), bounded graph traversal, typed mappings,
and native MCP tools. The completed v1 plan is
in [docs/plans/2026-08-11-v1-core-lookups.md](docs/plans/2026-08-11-v1-core-lookups.md).
