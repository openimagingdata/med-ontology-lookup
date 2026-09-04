# Project review and proposal

**Review date:** 2026-09-03
**Status:** proposed direction

## Executive recommendation

`med-ontology-lookup` should continue toward the product described in the
[product roadmap](product-roadmap.md): a small, dependable terminology gateway that lets
people and agents resolve medical language, inspect bounded ontology context, and translate
identifiers without learning each terminology provider's interface.

The current package is a credible alpha nucleus, but it is not ready to expand broadly. The
next milestone should harden the contracts already exposed by `search`, `get`, `crosswalk`,
`parents`, `children`, and `lookup`. In particular, the package must stop hiding provider
failures, stop silently truncating graph-shaped responses, and stop presenting ambiguous or
weak mappings as if they were unqualified crosswalks.

Authentication should also become a deployment choice behind the same lookup interface.
The default remains direct access with `BIOPORTAL_API_KEY` and/or `UMLS_API_KEY`. A second,
explicit **delegated authentication** mode should let callers point each provider adapter at
an authenticated proxy such as [Tailscale Aperture][aperture-http] and omit upstream keys from
the client environment. The package must never infer delegated authentication merely because
the hostname changed.

The recommended sequence is therefore:

1. harden existing behavior and result semantics;
2. add direct-versus-delegated authentication at the HTTP seam;
3. establish CI, live contract tests, and a published release;
4. ship one coherent agent-ready slice; and
5. add bounded graph operations only after the underlying contracts are trustworthy.

## What this product is

The package is a normalized gateway over terminology providers, not a terminology source in
its own right. Its useful product boundary is:

- accept terms, CUIs, codes, CURIEs, and IRIs;
- resolve them against a deliberately selected set of medical vocabularies;
- return normalized, versioned concepts and relationships with provider provenance;
- preserve ambiguity, partial failure, mapping strength, and licensing constraints;
- expose the same semantics through Python, structured CLI output, and eventually MCP; and
- remain deployable either directly from a workstation or through an organizational gateway.

The radiology profile remains the right default: RadLex and SNOMED CT for findings, FMA and
RadLex for anatomy, LOINC/RSNA Playbook for imaging orderables, and UMLS as a connection hub.
This should become an explicit, inspectable profile rather than an implicit tuple of default
ontology names.

The product should not become an ontology repository, a general graph database, an OWL
reasoner, or a clinical decision engine. It should not imply that a lexical result is clinically
correct or that two codes sharing a UMLS CUI are necessarily equivalent.

## Current implementation

The repository currently provides:

- an async `OntologyLookup` facade;
- BioPortal and UMLS provider adapters using `httpx`;
- Pydantic models for search results, concepts, hierarchy nodes, and source codes;
- a Typer CLI named `molu` with table and JSON output;
- balanced, per-ontology BioPortal search;
- semantic-type shorthand and strict/non-strict filtering;
- short-code and IRI resolution for common BioPortal ontologies;
- partial search warnings and credential redaction; and
- a portable agent skill under `skills/med-ontology-lookup/`.

The architecture is appropriately small:

```text
Python callers / CLI / agent skill
                |
                v
        OntologyLookup facade
          /              \
BioPortal adapter     UMLS adapter
          \              /
        shared HTTP transport
```

This is a good foundation. The facade is the public seam; provider-specific identifiers,
authentication, pagination, and failure handling belong behind it.

## Review findings

### Verified strengths

The offline engineering baseline is healthy:

- all 50 tests pass on Python 3.11, 3.12, 3.13, and 3.14;
- Pyright reports no errors;
- the wheel and source distribution build and pass metadata validation;
- the CLI runs when installed from the built wheel; and
- the resolved dependency set has no known reported vulnerabilities at review time.

The current tests are especially useful around identifier detection, BioPortal class resolution,
search balancing, semantic-type filtering, error redaction, and source-filter fidelity.

### Immediate correctness and contract risks

#### 1. Provider failures can be mistaken for normal fallback

`OntologyLookup.get`, hierarchy operations, and `lookup` catch broad HTTP failures. A BioPortal
authentication failure, rate limit, or server failure can therefore turn into a UMLS request or
an exact search. During this review, a mocked BioPortal `401` was reproducibly converted into:

- an empty `SearchResults` from `lookup`; and
- a successful UMLS concept from `get` when both backends were configured.

That behavior hides the event the caller most needs to understand. Fallback should occur only
for typed, intentional conditions such as `not_found` or `unsupported_operation`. Authentication,
authorization, licensing, rate limiting, upstream unavailability, and malformed responses must
remain visible.

This becomes more important with Aperture: `401` or `403` can mean missing tailnet identity or
an Aperture grant, `429` can be an Aperture quota, and `502` can mean the proxy cannot reach the
upstream. These must not trigger a different lookup operation.

#### 2. Hierarchy responses can silently truncate

The BioPortal parents and children methods consume one response page. The UMLS source parents
and children methods do not request or iterate pages; the documented default page size is 25.
BioPortal likewise documents common `page`, `pagesize`, `nextPage`, and `prevPage` controls.

Every collection operation needs one of two honest contracts:

- iterate within caller-supplied bounds; or
- return `truncated`, the applied limit, and a continuation cursor or next-page reference.

The same rule should cover search, annotations, mappings, and later graph traversal. A plain list
cannot communicate whether it is complete.

Sources: [UMLS source parents and children][umls-hierarchy] and
[BioPortal API documentation][bioportal-api].

#### 3. Crosswalk results overstate mapping certainty

For free text, the UMLS adapter selects the first search result and continues without returning
the rejected candidates or an ambiguity indicator. It then exposes source atoms sharing that CUI
as a flat crosswalk.

The replacement contract should distinguish:

- the candidate-resolution decision;
- UMLS co-CUI membership;
- provider-asserted mappings;
- curated project mappings;
- lexical suggestions; and
- exact, broader, narrower, related, or unknown mapping predicates.

Direction, source and target versions, provenance, justification, and confidence must travel with
each mapping assertion. Until then, documentation and CLI copy should call the current result a
UMLS co-CUI source-code expansion, not an unqualified equivalence mapping.

#### 4. Identifier and source normalization is not shared

Search and hierarchy normalize UMLS source abbreviations such as `LNC` and `SNOMEDCT_US` to
BioPortal acronyms. `get` does not consistently cross that same seam. Resolution rules should be
centralized and exercised through the public facade so every operation round-trips the same
identifier forms.

#### 5. Result envelopes are not yet reproducible

The current models do not consistently identify terminology edition/version, normalized input,
retrieval time, source URL, applied limits, continuation state, or typed partial failures.
`SearchResults.total_count` can mean the number of fetched unique candidates rather than the
provider's total. These semantics need explicit names before agents or downstream software depend
on them.

### Delivery and maintenance gaps

- There is no CI workflow, opt-in live provider smoke suite, branch protection, tag, GitHub
  release, or PyPI publication.
- No live API test was possible during this review because the environment had no provider keys.
- Exploratory statement coverage was 70% overall, with the CLI at 25%, the UMLS adapter at 67%,
  and the facade at 69%. Coverage is evidence about missing scenarios, not a target by itself.
- A current Ruff run reported 27 findings, but Ruff is not a declared development dependency and
  the repository has no complete lint policy. The project should choose and pin its policy before
  treating the count as a gate.
- Development-only packages currently use a `dev` optional extra. Current uv guidance recommends
  dependency groups for local development and testing; the `dev` group is synced by default.
  [uv dependency guidance][uv-dependencies]
- The CLI uses Typer's older function-default declarations. Current Typer documentation prefers
  `Annotated`, which also resolves the bulk of the Ruff `B008` friction.
  [Typer parameter guidance][typer-annotated]
- The portable agent skill and broader documentation are not included in built distributions.

The GitHub issue tracker is empty, so none of these risks or roadmap items currently has an owner,
acceptance criteria, or visible state.

## Authentication and endpoint proposal

### Required behavior

Each provider adapter should support two explicit modes:

| Mode | Client environment | Request behavior | Readiness rule |
| --- | --- | --- | --- |
| `direct` | Provider key is required | Adapter injects the provider's credential | Key is present |
| `delegated` | Provider key is optional and unused | Adapter sends no upstream credential; configured endpoint is responsible for authentication | Delegated endpoint is configured |

`direct` remains the default, preserving existing behavior. `delegated` is generic rather than
Aperture-specific: Aperture is the first concrete adapter at this seam, but a compatible internal
gateway should not require changes to lookup operations.

Do not infer the mode from the URL. A changed hostname is not proof that a proxy is trusted, and
silent inference would make credential leakage and confusing `401` responses more likely.

Recommended environment configuration:

```dotenv
# Existing direct mode (default)
BIOPORTAL_API_KEY=...
UMLS_API_KEY=...

# Delegated mode through two Aperture HTTP connectors
BIOPORTAL_AUTH_MODE=delegated
BIOPORTAL_BASE_URL=http://aperture-host/v1/connectors/bioportal
UMLS_AUTH_MODE=delegated
UMLS_BASE_URL=http://aperture-host/v1/connectors/umls

# BIOPORTAL_API_KEY and UMLS_API_KEY are not required in delegated mode.
```

The Python constructor should expose the same semantics through typed endpoint settings rather
than requiring callers to understand environment-variable precedence.

### Internal seam

The provider clients should ask a small authentication module to prepare requests. Its interface
needs to answer only:

- whether the provider is configured and eligible for selection;
- which non-secret authentication mode is active; and
- how to mutate headers or query parameters for a request.

The implementations are:

- direct BioPortal authentication (`Authorization` header or documented query key);
- direct UMLS authentication (`apiKey` query parameter); and
- delegated authentication (a deliberate no-op).

Backend selection must use provider readiness, not the mere presence of an API key. In delegated
mode, the provider is eligible without a local secret. `molu doctor` should report endpoint,
authentication mode, reachability, and capabilities without ever printing credentials.

When delegated mode is active, local provider keys must never be attached to requests. If keys are
also present in the environment, they should be ignored with a diagnostic so changing deployment
mode cannot accidentally forward a secret in an `apiKey` query parameter.

### Tailscale Aperture deployment

Aperture HTTP connectors implement the required model: a caller reaches
`/v1/connectors/<connector-id>/<path>`, Aperture authenticates the caller through Tailscale,
checks deny-by-default grants, appends the remaining path to the connector's upstream URL, strips
client `Authorization` and `Cookie` headers, and injects configured upstream credentials.
[Tailscale's HTTP connector guide][aperture-http] was last validated on 2026-08-13; the
[connector reference][aperture-reference] was last validated on 2026-08-23.

Both current providers accept API keys in query parameters, so an illustrative Aperture
configuration is:

```json
{
  "connectors": {
    "servers": {
      "bioportal": {
        "protocol": "http",
        "url": "https://data.bioontology.org",
        "description": "BioPortal terminology lookup",
        "auth": {
          "type": "api_key",
          "secret": "<bioportal-api-key>",
          "name": "apikey",
          "in": "query"
        }
      },
      "umls": {
        "protocol": "http",
        "url": "https://uts-ws.nlm.nih.gov/rest",
        "description": "UMLS Terminology Services lookup",
        "auth": {
          "type": "api_key",
          "secret": "<umls-api-key>",
          "name": "apiKey",
          "in": "query"
        }
      }
    }
  },
  "grants": [
    {
      "src": ["group:terminology-users"],
      "app": {
        "tailscale.com/cap/aperture": [
          {"connectors": ["bioportal/proxy", "umls/proxy"]}
        ]
      }
    }
  ]
}
```

The example is intentionally read-only in purpose, but Aperture grants control connector access,
not individual HTTP methods. Credential scopes and upstream accounts therefore remain the final
authorization boundary.

Operational constraints to document and test:

- callers need a valid Tailscale identity or an approved bridge arrangement;
- Aperture is deny-by-default and missing grants return `403`;
- connector IDs are alphanumeric and cannot contain hyphens;
- query parameters are forwarded, so delegated mode must ensure local API keys are absent;
- upstream redirects are blocked;
- connector responses above 50 MB are silently truncated by Aperture; and
- plain `http://` to the Aperture tailnet host is expected in the official examples because the
  tailnet connection is encrypted; the upstream legs remain HTTPS.

### UMLS licensing gate

A shared proxy credential is technically straightforward but must not be assumed to satisfy UMLS
licensing requirements for every caller. NLM documents a licensee-validation flow for third-party
applications that accepts both the application's validator key and the user's API key. The public
documentation reviewed here does not state that one application key may simply stand in for every
user behind a shared proxy.

Before enabling a shared UMLS Aperture connector beyond an individually licensed or otherwise
approved deployment, confirm the intended user-validation and source-vocabulary licensing model
with NLM. `molu doctor` and the ontology catalog should report licensing requirements separately
from technical reachability.

Sources: [UMLS API authentication][umls-auth] and
[validating UMLS licensees for third-party applications][umls-licensees].

## Proposed delivery sequence

### Phase 0: record and govern the work

Outcome: the repository has one executable plan and a visible backlog.

- Turn the findings in this document into small GitHub issues with acceptance criteria.
- Keep the implementation plan under `docs/plans/` current as work lands.
- Decide which behavior changes require a minor release rather than a patch release.
- Keep `CHANGELOG.md` limited to released, externally visible differences; use `DEV_LOG.md` for
  engineering decisions and investigation notes.

Exit criteria: every Phase 1 item has an issue, dependency order, and verification method.

### Phase 1: contract hardening

Outcome: existing promises are trustworthy under success, absence, partial failure, and provider
failure.

- Add a typed error taxonomy and status-aware fallback policy.
- Centralize identifier/source normalization and resolution.
- Distinguish `auto` from an explicit request for `both` providers.
- Replace unbounded/plain list responses with bounded collection envelopes.
- Correct total-count semantics and add typed warnings, truncation, and continuation metadata.
- Add provider, terminology version, source URL, normalized input, and retrieval metadata.
- Preserve ambiguity during term-to-CUI resolution.
- Rename or enrich current crosswalk output so its evidence is explicit.

Exit criteria: regression tests cover authentication, authorization, rate limits, not-found,
partial failure, ambiguous terms, source aliases, multi-page hierarchy, and truncation.

### Phase 2: delegated authentication and diagnostics

Outcome: the same Python and CLI operations work directly or through Aperture without local
provider keys.

- Add typed direct/delegated endpoint settings and the internal authentication seam.
- Make backend readiness depend on endpoint configuration and authentication mode.
- Guarantee that delegated requests contain neither BioPortal authorization nor UMLS `apiKey`.
- Preserve proxy-originated statuses in the typed error model.
- Add `molu doctor` checks for configuration, reachability, identity/grants, upstream health,
  provider release visibility, and licensing notices.
- Document direct and Aperture configurations, including least-privilege grants and UMLS licensing.

Exit criteria: the same mocked contract suite passes against direct and delegated transports, and
opt-in live tests exercise both provider paths through a configured Aperture gateway.

### Phase 3: release foundation

Outcome: users and agents can install a verified artifact rather than depending on a source
checkout.

- Add CI for supported Python versions, tests, Ruff, Pyright, build validation, and package smoke
  installation.
- Add separately gated live provider and Aperture contract tests.
- Move development tools to a uv dependency group and pin the chosen quality-tool policy.
- Add CLI integration coverage, including JSON output and exit codes.
- Decide how the agent skill and reference docs are distributed with or alongside the package.
- Tag, publish, and document the first release after the hardened contract is stable.

Exit criteria: a clean checkout can run the documented development commands, CI enforces the same
checks, and the published artifact supports the documented installation paths.

### Phase 4: agent-ready terminology workflow

Outcome: a fresh agent can discover and use the gateway safely.

- Add ontology catalog, versions, capabilities, and licensing resources.
- Implement inspectable profiles, beginning with `radiology`.
- Add bounded batch lookup and BioPortal annotation with per-item errors.
- Keep Python, CLI JSON, and MCP schemas in parity.
- Introduce narrow MCP tools only after the normalized models and errors are stable.

Exit criteria: an agent can discover availability, search or annotate, validate a selected
concept, and explain any ambiguity or partial result without parsing console prose.

### Phase 5: bounded graph context and typed mappings

Outcome: callers can ask useful relationship questions without turning the package into a graph
database.

- Add ancestors, descendants, paths-to-root, `subsumes`, relations, and shortest path.
- Require `max_depth`, node/edge limits, predicate filters, and continuation state.
- Introduce typed, directional, SSSOM-compatible mapping assertions.
- Add FHIR-shaped validation and translation where the semantics match.

Exit criteria: graph and mapping responses are versioned, provenance-preserving, bounded, and
covered by golden fixtures plus opt-in live checks.

## What not to tackle yet

- A custom graph database or unrestricted recursive traversal.
- A generic plugin framework before additional backends demonstrate a real shared seam.
- Similarity or LLM reranking before deterministic resolution and mapping evidence are correct.
- Broad ontology expansion that weakens the radiology default.
- CPT or billing mappings without explicit licensing and mapping provenance.
- A large MCP surface that merely republishes unstable internal contracts.
- Aperture-specific branches inside search, lookup, or graph logic; deployment variation belongs
  at the endpoint/authentication seam.

## Decision summary

The project should remain small in interface and deep in implementation. Callers should learn one
terminology contract; the package should absorb provider names, credentials, proxy routing,
pagination, retries, provenance, and error interpretation behind that seam.

The immediate product is not “more endpoints.” It is a lookup result that can be trusted. Once
that is true, delegated authentication through Aperture makes the tool substantially easier and
safer to deploy for agents, and the graph roadmap becomes an incremental extension rather than a
rewrite.

[aperture-http]: https://tailscale.com/docs/aperture/how-to/set-up-http-api-connector
[aperture-reference]: https://tailscale.com/docs/aperture/connectors/reference
[bioportal-api]: https://data.bioontology.org/documentation
[typer-annotated]: https://typer.tiangolo.com/tutorial/arguments/optional/
[umls-auth]: https://documentation.uts.nlm.nih.gov/rest/authentication.html
[umls-hierarchy]: https://documentation.uts.nlm.nih.gov/rest/parents-and-children/
[umls-licensees]: https://documentation.uts.nlm.nih.gov/validating-licensees.html
[uv-dependencies]: https://docs.astral.sh/uv/concepts/projects/dependencies/
