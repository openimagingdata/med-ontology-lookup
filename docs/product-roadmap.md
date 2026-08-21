# Product direction: an agent-ready medical terminology graph gateway

**Research date:** 2026-08-16  
**Status:** recommended direction

## Executive decision

`med-ontology-lookup` should become the small, dependable layer that lets people and
agents resolve medical language to versioned concepts, inspect the clinically relevant
part of an ontology graph, and translate identifiers without learning each terminology
provider's API.

The useful product is not another ontology repository or general graph database. Its
distinctive value is the combination of:

1. a **radiology default profile** spanning RadLex, LOINC (including the
   LOINC/RSNA Radiology Playbook), SNOMED CT, FMA, and UMLS as the CUI hub;
2. one normalized, provenance-preserving contract over remote and optional local backends;
3. bounded graph operations designed for questions and agent context, not graph dumps;
4. explicit uncertainty, mapping direction, source version, and partial-failure reporting;
5. equal support for Python, CLI/JSON, and a self-describing agent protocol.

The current search/get/crosswalk/one-hop hierarchy implementation is the right nucleus.
Reliability and result semantics are the gate to expanding it.

## Goals and boundaries

### Product goals

- Resolve a term, CUI, CURIE, code, or IRI into a canonical concept reference.
- Find and rank candidate concepts across a deliberately selected set of terminologies.
- Validate whether a code is active and appropriate in a named ontology edition/version.
- Explain a concept through its hierarchy and typed relationships.
- Translate across code systems while preserving mapping direction, scope, provenance,
  and strength instead of treating every cross-reference as equivalence.
- Annotate clinical text and process batches using the same normalized models.
- Return compact, deterministic, machine-readable evidence that an agent can cite and
  another program can reproduce.

### Non-goals

- Ontology authoring, collaborative editing, or classification/reasoning from arbitrary OWL.
- Hosting full licensed terminology distributions by default.
- Replacing Snowstorm, a FHIR terminology server, BioPortal, OLS, UMLS, or OAK.
- Making clinical decisions or asserting that a lexical match is clinically correct.
- Hiding meaningful differences between editions, code systems, mappings, or backends.

## What the current project already gets right

- A single async facade over BioPortal and UMLS.
- Normalized Pydantic responses for search, concept details, crosswalks, and hierarchy.
- Balanced multi-ontology search rather than letting the largest source dominate.
- Medical shorthand for semantic types.
- Structured JSON CLI output and a portable in-repository agent skill.
- Graceful use of either credential and visible partial-backend warnings.

The current review fixes also identify product invariants that should be made explicit:
short codes must resolve to canonical IRIs, backend relevance must survive merging,
requested source filters must never leak, identifiers must round-trip correctly, and
auto-detection must cover documented code forms.

## What current standards and tools imply

| Evidence | Product implication |
|---|---|
| [FHIR terminology services](https://hl7.org/fhir/terminology-service.html) center on lookup, validate, subsumes, value-set expand, and concept-map translate. | Add these concepts to the public facade even when an underlying backend is not a FHIR server. |
| [FHIR ConceptMap](https://hl7.org/fhir/conceptmap.html) says mappings are directional, contextual, and may have multiple targets. | Replace the current flat crosswalk semantics with typed, scoped mapping assertions. |
| [BioPortal's API](https://data.bioontology.org/documentation) already exposes annotator, mappings, paths-to-root, tree, ancestors, descendants, parents, and children endpoints. | Most first-wave graph and annotation features can be thin, bounded backend adapters. |
| [UMLS source hierarchy](https://documentation.uts.nlm.nih.gov/rest/parents-and-children/) and [source relations](https://documentation.uts.nlm.nih.gov/rest/source-asserted-identifiers/relations/) expose deeper traversal and labeled non-hierarchical relations. | Preserve source-asserted edges and distinguish source-code graphs from CUI relations. |
| [SNOMED CT ECL](https://docs.snomed.org/snomed-ct-specifications/snomed-ct-expression-constraint-language/appendices/appendix-d-ecl-quick-reference) covers ancestor/descendant sets, immediate parents, attributes, cardinalities, and refinements. | A SNOMED-capable adapter should eventually accept or compile a safe subset of ECL instead of emulating it with repeated HTTP calls. |
| [SNOMED terminology guidance](https://docs.snomed.org/snomed-ct-practical-guides/snomed-ct-terminology-services-guide/4-terminology-service-types/4.1-select-edition-and-version) requires edition/version selection because results change across releases. | Ontology/version must be first-class request and response fields, not implicit backend state. |
| [OBO Graphs](https://github.com/geneontology/obographs) models ontologies as property-labeled nodes and edges with metadata. | Adopt a small compatible graph model and offer OBO Graph JSON export rather than inventing an opaque graph blob. |
| [OHDSI CONCEPT_ANCESTOR](https://www.ohdsi.org/web/wiki/doku.php?id=documentation%3Acdm%3Aconcept_ancestor) stores closure plus minimum and maximum levels of separation. | Distances and reflexive/non-reflexive traversal are analytically useful and belong in graph responses. |
| [OAK](https://incatools.github.io/ontology-access-kit/guide/index.html) separates ontology interfaces from implementations and adds traversal, mappings, and semantic similarity. | Keep the facade capability-based and consider OAK as an optional local backend rather than rebuilding its local ontology machinery. |
| [SSSOM](https://mapping-commons.github.io/sssom/dev/) represents a mapping as subject/predicate/object plus provenance, confidence, and justification. | Use SSSOM-compatible mapping records; a CUI alone is evidence of connection, not proof of exact equivalence. |
| The current [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) supports input/output JSON Schema, structured content, errors, pagination, and behavior annotations; [resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources) expose URI-addressed context. | Ship a native MCP server with narrow typed tools, plus ontology catalog/version/capability resources. |
| [OBO identifier](https://obofoundry.org/principles/fp-003-uris.html) and [versioning](https://obofoundry.org/principles/fp-004-versioning.html) principles emphasize persistent identifiers and immutable retrievable releases. | Return both compact IDs and canonical IRIs, and record the exact terminology release whenever the provider exposes it. |

## The graph contract

Start with a backend-neutral graph envelope. It should remain useful if the backend is
BioPortal, UMLS, OLS, a FHIR terminology server, Snowstorm, or a local OAK adapter.

### Core records

```text
ConceptRef
  id                 canonical CURIE/code for display and input
  iri                canonical IRI when one exists
  ontology           normalized code-system key
  version            edition/release identifier, nullable only when unavailable

OntologyNode
  ref, preferred_label, synonyms, definition, semantic_types
  active, obsolete, replaced_by[]
  source_backend, retrieved_at, source_url

OntologyEdge
  subject, predicate, object
  predicate_label
  direction
  asserted_or_inferred
  mapping_metadata   optional SSSOM-compatible metadata
  source_backend, ontology_version, source_url

GraphResult
  seeds[], nodes[], edges[]
  truncated, next_cursor, warnings[]
  request parameters and backend capabilities used
```

Do not flatten `is_a`, `part_of`, attribute relationships, UMLS `RO/PAR/CHD`, and
cross-ontology mappings into one generic `related_to` edge. Preserve the provider's raw
predicate alongside a normalized predicate.

### First graph operations

| Operation | Why it matters | Required controls |
|---|---|---|
| `ancestors` / `descendants` | Cohort expansion, concept generalization, navigation | `max_depth`, `include_self`, predicate set, `max_nodes`, cursor |
| `paths_to_root` | Explain why a concept belongs under a category | path count, maximum depth, preferred roots/predicates |
| `subsumes(a, b)` | Direct, cheap answer to “is A a kind of B?” | ontology and version; FHIR-aligned result (`equivalent`, `subsumes`, `subsumed_by`, `not_subsumed`) with inability to determine represented separately |
| `relations` | Anatomy, finding-site, component, method, and other non-`is_a` semantics | direction, predicate filter, source-asserted vs inferred |
| `shortest_path(a, b)` | Explain connections and diagnose questionable mappings | allowed predicates, directionality, maximum depth |
| `subgraph` / `neighborhood` | Supply bounded context to an agent or visualization | depth, predicates, direction, `max_nodes`, `max_edges`, token/detail budget |

Implement specific operations before exposing a free-form graph query language. They are
easier for agents to select, easier to bound, and map directly to current backend APIs.

### Second-wave graph operations

- `common_ancestors` and `most_informative_common_ancestor` for disambiguation.
- Pairwise term similarity using ancestor Jaccard first, then optional information-content
  measures; OAK documents both approaches in its
  [similarity guide](https://incatools.github.io/ontology-access-kit/guide/similarity.html).
- Value-set or root expansion with semantic, active-status, and depth filters.
- Mapping graph traversal with explicit `exact`, `broader`, `narrower`, and `related`
  semantics. [SKOS](https://www.w3.org/TR/skos-reference/) and SSSOM should supply the
  normalized vocabulary.
- Release-to-release concept and neighborhood diff: activated, inactivated, relabeled,
  reparented, remapped, and replacement concepts.
- Export to OBO Graph JSON, JSON-LD, edge-list JSONL, and GraphML/DOT for downstream tools.

## Agent accessibility

The existing skill is helpful documentation, but it still makes an agent reason about
shell invocation, environment location, output parsing, and backend limitations. Add a
native MCP server as a thin package extra, while retaining CLI and Python parity.

### MCP tools

Prefer a small set of explicit, read-only tools:

```text
ontology_search
ontology_get
ontology_validate
ontology_crosswalk
ontology_annotate
ontology_ancestors
ontology_relations
ontology_path
ontology_subgraph
```

Each tool should have strict input and output JSON Schemas, enums for common ontology keys,
bounded defaults, cursor pagination, and structured errors. Tool descriptions must say
when *not* to use the tool. Mark them read-only and idempotent in protocol annotations.

### MCP resources

```text
ontology://catalog
ontology://profiles
ontology://semantic-types
ontology://{ontology}/capabilities
ontology://{ontology}/releases
ontology://{ontology}/{version}/license
```

These let the host or agent discover what is available without spending a tool call on a
failed lookup. The skill then becomes a concise workflow guide over the native tools,
instead of a CLI manual.

### Response behavior for agents

- Always include `query_interpretation` and the normalized identifier used.
- Separate `backend_rank`, `exact_label_match`, and any project-defined score; never
  present a heuristic score as calibrated clinical confidence.
- Return provenance and version on every node, edge, annotation, and mapping.
- Return `truncated`, `next_cursor`, and applied limits instead of silently clipping.
- Make partial results explicit with typed warnings and retriable/non-retriable errors.
- Support `detail=minimal|standard|full` so agents can control context size.
- Preserve candidate ambiguity. An agent should confirm among candidates rather than have
  `lookup` silently guess a code system.
- Supply one-shot `explain` output assembled from concept details, selected paths, mappings,
  and warnings for common agent questions, but keep the underlying primitives available.

### Installation and discovery

- Publish a package usable via `pip`, `uv tool install`, and `uvx`, so an agent is not
  required to start in this repository.
- Add `molu doctor` for credential, connectivity, supported-source, and version diagnostics.
- Add `molu capabilities --format json` and keep it identical to the MCP catalog.
- Offer an optional HTTP/OpenAPI service only when multi-user deployment is needed; do not
  make a daemon mandatory for local use.
- Add an uncredentialed open-ontology backend, preferably OLS, for immediately useful
  installation. Keep licensed SNOMED/UMLS behavior opt-in and visible.

## Other high-value features

### Domain profiles, not an ever-growing default search

Use named profiles to control ontologies, ranking, semantic filters, and
playbook-aware mapping. Profiles are inspectable configuration, not hidden boosts.

**`radiology` is the default.** This package started as radiology-term lookup
(RadLex + SNOMED + FMA) and should stay that way unless the caller asks
otherwise. LOINC belongs in that default because radiology *orderables* live in
the LOINC/RSNA Radiology Playbook, while findings, anatomy, and report language
live in RadLex.

| Profile | Default? | Sources | Role |
|---|---|---|---|
| `radiology` | **yes** | RadLex, LOINC (Playbook-weighted), SNOMED CT, FMA; UMLS as hub | Findings, anatomy, imaging procedures/orderables |
| `anatomy` | no | FMA, RadLex, Uberon, SNOMED CT | Body structures; RadLex imaging anatomy sits next to FMA |
| `laboratory` | no | LOINC, SNOMED CT | Labs/observations outside imaging playbook |
| `clinical` | no | SNOMED CT, UMLS, ICD-10-CM where licensed | Problems, diagnoses, general clinical coding |
| `billing-us` | no, opt-in | CPT (UMLS only, license-gated), ICD-10-CM, ICD-10-PCS, SNOMED CT | US billing/procedure codes; never implicit |
| `medication` | no | RxNorm, SNOMED CT | Drugs |
| `phenotype` | no | HPO, SNOMED CT, UMLS | Phenotypes |
| `oncology` | no | NCIt, SNOMED CT, ICD-O where available | Cancer concepts |

CLI/library default should be equivalent to `--profile radiology` (today's
`RADLEX,SNOMEDCT,FMA,LOINC` plus UMLS when keyed). `--profile` / `profile=`
becomes the named switch; `--ontologies` remains an override.

#### LOINC/RSNA Radiology Playbook (first-class in `radiology`)

The [LOINC/RSNA Radiology Playbook](https://loinc.org/committee/radiology/) is
the joint Regenstrief–RSNA terminology for **imaging procedures / orderables**.
RadLex Playbook (RPID) was folded into LOINC; new procedure codes are LOINC
format, not new RPIDs.

Implications for this product:

- In `radiology` search, rank **procedure/orderable** queries toward LOINC
  Playbook terms and **finding/anatomy** queries toward RadLex (plus SNOMED/FMA).
- Crosswalk should know Playbook correspondences (LOINC ↔ historic RPID ↔
  RadLex anatomy/modality attributes) and say so in mapping provenance.
- Detect `RPID…` as well as LOINC `8867-4`-shaped codes.
- Do not treat every LOINC hit as radiology; prefer Playbook / radiology class
  when the profile is `radiology`.
- A later `laboratory` profile uses the rest of LOINC without Playbook bias.

#### CPT and ICD — include, but not in the radiology default

**ICD-10-CM** (diagnoses) and **ICD-10-PCS** (inpatient procedures) are
available via BioPortal (`ICD10CM`, `ICD10PCS`) and UMLS, under the UMLS
license. They belong in:

- `clinical` (ICD-10-CM as a first-class diagnosis system);
- `billing-us` (CM + PCS together);
- optional **add-on** to a radiology session (`--ontologies …,ICD10CM`) when
  someone is coding a report impression to a billable diagnosis.

They should **not** join the radiology default search. ICD's size and
billing-oriented labels would crowd RadLex/SNOMED findings the same way
unscoped SNOMED already can.

**CPT** is different. It is AMA-licensed. [BioPortal no longer serves
CPT](https://www.bioontology.org/why-bioportal-no-longer-offers-the-current-procedural-terminology-cpt/).
UMLS can return CPT atoms only when the caller's UTS license includes CPT
(often a separate entitlement). Therefore:

- Never put CPT in `radiology` or any default search.
- Expose CPT only through `billing-us` (or an explicit `--ontologies CPT`)
  **and** only via the UMLS backend.
- `molu doctor` / capabilities must report `cpt: unavailable` unless the UMLS
  key is known to authorize CPT; failed CPT calls must say “license,” not
  “no hits.”
- Do not cache or ship CPT content. Mapping Playbook/LOINC/SNOMED → CPT is
  valuable for US radiology ops but is a **curated/SSSOM overlay**, not a
  casual UMLS co-CUI dump (those co-occurrences are weak evidence of
  billing equivalence).

Recommended split of labor in radiology workflows:

| Question | Prefer |
|---|---|
| What did we see? (finding, anatomy, modifier) | RadLex, SNOMED, FMA |
| What exam was ordered/performed? | LOINC/RSNA Playbook |
| What diagnosis code for the impression? | ICD-10-CM (`clinical` / explicit add-on) |
| What US professional/hospital procedure code? | CPT / ICD-10-PCS (`billing-us`, license-gated) |

### Text annotation and batch workflows

- Wrap BioPortal Annotator first, returning offsets, matched text, candidate concept,
  match method, and overlap policy.
- Add `annotate_many` and `lookup_many` with concurrency limits, input-order preservation,
  per-item errors, and resumable JSONL output.
- Add optional context-aware reranking as a separate stage with evaluation data; do not
  mix an LLM's judgment into the deterministic lookup response.

### Validation, replacement, and lifecycle

- `validate(code, ontology, version, value_set=None)` with active/inactive status.
- Inactivation reason and replacement/association targets where supported.
- Ontology catalog: canonical URI, aliases, backend keys, versions, languages, license,
  capabilities, and retrieval timestamp.
- Release diff and pinned-version reproducibility.

### Mapping quality

- Return mapping predicate, direction, target scope, provenance, justification, confidence,
  and source version.
- Distinguish provider mappings, UMLS co-CUI membership, lexical suggestions, and curated
  project mappings.
- Offer `explain_mapping` and never infer the reverse of a directional mapping without an
  explicit inverse rule.
- Export/import SSSOM for review and interchange.

### Reliability and evaluation

- A canonical identifier resolver shared by every operation.
- Typed error taxonomy: authentication, licensing, not found, ambiguous identifier,
  unsupported operation, rate limit, unavailable backend, and partial result.
- Retry/backoff and bounded caching keyed by backend, ontology, edition/version, request,
  and response shape; never cache transient failures as misses.
- Recorded contract fixtures plus opt-in live smoke tests against provider sandboxes/APIs.
- A small golden set per profile measuring exact-code resolution, top-k term retrieval,
  ranking stability, filter fidelity, mapping scope, graph path correctness, and annotation
  spans.

## Recommended sequence

| Phase | Outcome | Exit criteria |
|---|---|---|
| **0. Contract hardening** | Existing promises are trustworthy. | Review cases are covered; canonical resolver, typed errors, source-filter fidelity, ranking stability, and live smoke suite exist. |
| **1. Agent-ready terminology gateway** | Easy installation and self-description. | Ontology catalog/capabilities, versions/provenance fields, `doctor`, batch lookup, annotation, and strict MCP tools/resources ship with Python/CLI parity. |
| **2. Core graph context** | Agents can ask and explain hierarchy questions. | Ancestors, descendants, paths-to-root, relations, subsumes, shortest path, and bounded subgraph use the common node/edge envelope. |
| **3. Interoperability and mapping semantics** | Results compose with clinical systems and mapping workflows. | FHIR-shaped validate/expand/translate; SSSOM mappings; named profiles with **`radiology` default + Playbook ranking**; optional ICD; license-gated CPT; lifecycle/replacement; graph exports. |
| **4. Reproducible local analysis** | Larger and repeatable graph workloads are practical. | Optional OLS/OAK/Snowstorm/FHIR adapters, version pinning, persistent cache/local index, similarity, release diff, and graph analytics. |

## What not to build first

- A custom graph database or SPARQL service.
- Unlimited recursive traversal over paid/rate-limited APIs.
- Embedding similarity before deterministic hierarchy and mapping semantics are correct.
- A generic plugin system before two genuinely different additional backends require it.
- More ontologies in the **radiology default** without Playbook-aware ranking
  (especially dumping all of LOINC, ICD, or CPT into every imaging search).
- Treating UMLS CUI co-occurrence as CPT or ICD billing equivalence.
- A single giant “medical ontology agent” tool with an untyped action parameter.

## Near-term product milestone

A strong next release would let a fresh agent installation:

1. discover available ontologies and their versions/capabilities;
2. annotate or search a phrase using the default **`radiology` profile**
   (RadLex + LOINC Playbook + SNOMED + FMA), or another named profile;
3. validate and retrieve the chosen concept with provenance;
4. obtain a bounded explanatory subgraph and test subsumption;
5. crosswalk using typed, directional mapping evidence; and
6. return stable structured JSON with visible ambiguity, truncation, and partial failures.

That workflow is more valuable than adding many isolated endpoints: it turns the package
from a lookup utility into a trustworthy semantic context service.
