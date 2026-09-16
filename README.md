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
uv sync
```

Or with pip:

```bash
pip install -e .
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

### Provider failures and fallback

Remote failures use a stable library exception contract. `ProviderError` represents one failed
provider call; `ProviderAggregateError` represents an operation in which every attempted provider
call failed. Both inherit from `ProviderFailureError` and expose one or more credential-safe
`ProviderFailure` records:

```python
from med_ontology_lookup import OntologyLookup, ProviderFailureError

async with OntologyLookup() as mol:
    try:
        results = await mol.search("pneumothorax")
    except ProviderFailureError as exc:
        for failure in exc.failures:
            print(failure.provider, failure.operation, failure.category, failure.http_status)
```

Fallback is limited to adapter-classified concept absence or an explicitly unsupported operation.
Authentication, authorization, rate limits, upstream failures, transport failures, invalid JSON,
and malformed successful responses remain visible to callers. A `404` at a custom provider or
proxy endpoint is not assumed to mean that a concept is absent.

When at least one concurrent search succeeds, the result remains usable even if it is empty.
Partial failures are available as structured `SearchResults.failures`; the existing human-readable
`SearchResults.warnings` field remains available. When every call fails, search raises
`ProviderAggregateError`.

With `--output json`, CLI provider errors are written to stderr with exit status 1:

```json
{
  "error": {
    "code": "provider_failure",
    "message": "All attempted provider calls failed (1 failure)",
    "failures": [
      {
        "provider": "bioportal",
        "operation": "search",
        "category": "authentication",
        "endpoint": "https://data.bioontology.org/search",
        "http_status": 401,
        "status_origin": "unknown",
        "ontology": "RADLEX"
      }
    ]
  }
}
```

Failure output excludes response bodies, URL credentials, query parameters, and exception chains
that could retain provider credentials.

## Agent skill

Portable skill package: [`skills/med-ontology-lookup/`](skills/med-ontology-lookup/).

Point your agent runtime at that directory (or copy/symlink it into the runtime’s skills path). It documents when and how to run `uv run molu` for ontology lookups—not tied to any single agent product.

## Development

The repository's check commands are collected in `Taskfile.yml`. With
[Task](https://taskfile.dev/) installed:

```bash
uv sync
task check         # lockfile, format, lint, types, and current-Python tests
task test-matrix   # tests on Python 3.11, 3.12, 3.13, and 3.14
task verify        # standard checks, Python matrix, and package build
task fix           # safe Ruff fixes and formatting
```

Each task is a thin wrapper around a locked `uv` command; `task --list` shows the individual
commands. The lockfile resolves the type checker and formatter/linter versions, so the same versions
run locally and in automation while `pyproject.toml` expresses the compatible lower bounds.

Tests mock HTTP with `respx` (no live API keys required).

## License notes

This tool only calls remote APIs. **SNOMED CT** and **UMLS** content are subject to their respective licenses; obtain a UMLS license before using UMLS/SNOMED data in production. RadLex and FMA have their own terms via BioPortal.

## Roadmap

Start with the [current project review and proposal](docs/project-review-and-proposal.md),
which prioritizes contract hardening, delegated authentication through proxies such as
Tailscale Aperture, release readiness, agent workflows, and bounded graph operations.
The longer-term [product and graph roadmap](docs/product-roadmap.md) describes the target:
an agent-ready terminology gateway with a **radiology default profile** (RadLex +
LOINC/RSNA Playbook + SNOMED + FMA), bounded graph traversal, typed mappings,
and native MCP tools. The completed v1 plan is in
[docs/plans/2026-08-11-v1-core-lookups.md](docs/plans/2026-08-11-v1-core-lookups.md).
