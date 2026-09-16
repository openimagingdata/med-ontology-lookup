# Project review and proposal

**Review date:** 2026-09-03
**Backlog review:** 2026-09-05
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

1. establish offline CI while hardening provider failures and fallback behavior;
2. make backend selection, identifiers, collections, provenance, and UMLS expansion honest;
3. add direct-versus-delegated authentication, bounded diagnostics, and opt-in live checks;
4. prepare a release, with publication as an explicit checkpoint;
5. ship one coherent agent-ready slice; and
6. add bounded graph operations only after the underlying contracts are trustworthy.

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
- the locked `ty` check reports no errors;
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
when the adapter classifies an operation-specific response as an expected absence or unsupported
operation. HTTP status alone is insufficient: for example, a provider concept `404` may mean
absence while an Aperture connector-path `404` is a routing failure. Authentication,
authorization, licensing, rate limiting, timeouts, connection failures, upstream unavailability,
invalid JSON, and structurally invalid successful responses must remain visible with provider,
operation, sanitized endpoint, and status origin when it is known.

Only typed, expected provider failures should become partial-result warnings. Unexpected
programming exceptions and task cancellation must propagate rather than being converted into
normal provider outcomes by broad exception handling or `gather(return_exceptions=True)`.

This becomes more important with Aperture: `401` or `403` can mean missing tailnet identity or
an Aperture grant, `429` can be an Aperture quota, and `502` can mean the proxy cannot reach the
upstream. These must not trigger a different lookup operation.

#### 2. Hierarchy responses can silently truncate

The BioPortal parents and children methods consume one response page. The UMLS source parents
and children methods do not request or iterate pages; the documented default page size is 25.
BioPortal likewise documents common `page`, `pagesize`, `nextPage`, and `prevPage` controls.

Every collection operation needs one of two honest contracts:

- iterate within caller-supplied bounds; or
- return `truncated`, the applied limit, and an honest continuation cursor or next-page reference
  when the provider and merged result model can actually support one.

The same rule should cover search, UMLS atom expansion, annotations, mappings, and later graph
traversal. Envelopes must distinguish complete empty results, partial empty results, total failure,
and capped results. Returned count, provider-reported total, and merged total are separate fields;
the latter may be unknown. Pagination must stop safely on repeated pages, repeated cursors, or
duplicate-only pages. A plain list cannot communicate whether it is complete.

Sources: [UMLS source parents and children][umls-hierarchy] and
[BioPortal API documentation][bioportal-api].

#### 3. Crosswalk results overstate mapping certainty

For free text, the UMLS adapter selects the first search result and continues without returning
the rejected candidates or an ambiguity indicator. Source-code lookup can also resolve through
more than one CUI. The adapter then exposes source atoms sharing the chosen CUI as a flat
crosswalk, and free-text resolution currently reuses the expansion target filter as a search
restriction even though these are different decisions.

The immediate replacement contract should preserve candidate choices, make CUI selection
explicit, separate resolution restrictions from expansion targets, and label the returned atoms
as co-CUI evidence. A later mapping model should distinguish:

- the candidate-resolution decision;
- UMLS co-CUI membership;
- provider-asserted mappings;
- curated project mappings;
- lexical suggestions; and
- exact, broader, narrower, related, or unknown mapping predicates.

Direction, source and target versions, provenance, justification, and confidence must eventually
travel with each mapping assertion. Generic mappings, confidence scoring, and SSSOM-compatible
output should remain a later milestone. Until then, documentation and CLI copy should call the
current result a UMLS co-CUI source-code expansion, not an unqualified equivalence mapping.

#### 4. Identifier and source normalization is not shared

Search and hierarchy normalize UMLS source abbreviations such as `LNC` and `SNOMEDCT_US` to
BioPortal acronyms. `get` does not consistently cross that same seam. Resolution rules should be
centralized and exercised through the public facade so every operation round-trips the same
identifier forms.

#### 5. Result envelopes are not yet reproducible

The current models do not consistently identify terminology edition/version, normalized input,
retrieval time, source URL, applied limits, continuation state, or typed partial failures. A
request for UMLS version `current` is a mutable alias, not an immutable release identifier;
responses should distinguish requested release, resolved provider release when knowable, and the
possibly distinct or unavailable source-vocabulary release. `SearchResults.total_count` can mean
the number of fetched unique candidates rather than the provider's total. These semantics need
explicit names before agents or downstream software depend on them.

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
- delegated authentication, which actively guarantees that upstream credentials are absent.

Backend selection must use provider readiness, not the mere presence of an API key. In delegated
mode, the provider is eligible without a local secret. `molu doctor` should report endpoint,
authentication mode, reachability, and capabilities without ever printing credentials.

When delegated mode is active, local provider keys must never be attached to requests. This is
stronger than making credential injection a no-op: final outgoing requests must also exclude
provider credentials inherited from a caller-supplied `httpx` client's default headers,
authentication callback, cookies, default query parameters, or credentials embedded in an
endpoint URL. Unsafe inherited state should be rejected or stripped deterministically and covered
by transport-level tests. If keys are also present in the environment, they should be ignored
with a diagnostic so changing deployment mode cannot accidentally forward a secret in an
`apiKey` query parameter.

Every delegated request, including paginated requests, must remain under the configured connector
prefix. Provider-supplied absolute next-page URLs must not bypass
`/v1/connectors/<connector-id>`; pagination should reconstruct or validate the next request
against the configured delegated endpoint.

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
- query parameters are forwarded, so delegated mode must ensure local and inherited API keys are
  absent;
- all request and pagination paths must remain under the configured connector prefix;
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
from technical reachability. A diagnostic can report observed status and configuration, but a
bare `403` cannot reliably identify whether the cause is Tailscale identity, an Aperture grant,
upstream authorization, or licensing; explanations must remain bounded by the available evidence.

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

Exit criteria: every immediate item has an issue, dependency order, and verification method.

### Phase 1: offline baseline and provider-failure contract

Outcome: every change receives reproducible offline checks while provider failures stop becoming
misleading fallback results.

- Add offline CI for supported Python versions, tests, the chosen and pinned Ruff policy, `ty`,
  build validation, and package smoke installation.
- Expose the same commands through the repository Taskfile and contributor documentation, and keep
  them runnable from a clean checkout.
- Add a typed, operation-aware provider error taxonomy and fallback policy.
- Preserve provider, operation, sanitized endpoint, HTTP status, and known status origin.
- Propagate unexpected programming exceptions and cancellation.

The offline CI and provider-failure work can proceed in parallel. Neither depends on live
credentials.

Exit criteria: a clean checkout passes the documented offline checks, and regression tests cover
authentication, authorization, rate limits, not-found, malformed responses, timeouts, cancellation,
partial failure, and proxy-versus-provider status ambiguity.

### Phase 2: trustworthy lookup contracts

Outcome: provider selection, identity, collections, provenance, and UMLS expansion are explicit
enough for callers to interpret correctly.

- Define backend selection per operation: `auto` selects eligible providers; explicit single
  selection never silently uses another provider; explicit `both` requires both providers; and
  unsupported selections fail before network access. Singular `get` should reject `both` unless a
  future multi-result contract explicitly supports it.
- Make readiness depend on endpoint and authentication configuration rather than key presence.
- Centralize identifier/source normalization and resolution.
- Replace unbounded/plain list responses with bounded collection envelopes.
- Correct returned/provider/merged count semantics and add typed per-source outcomes, warnings,
  truncation, and continuation metadata without promising a resumable merged cursor prematurely.
- Add requested and resolved provider release, source-vocabulary release when available, source
  URL, normalized input, and retrieval metadata.
- Preserve ambiguity during both term-to-CUI and source-code-to-CUI resolution.
- Separate resolution restrictions from expansion targets and rename the current crosswalk output
  as evidence-labeled UMLS co-CUI expansion.

Exit criteria: regression tests cover backend selection, source aliases, identity round trips,
ambiguous terms and codes, multi-page hierarchy and atom expansion, repeated-page termination,
empty/partial/failed collections, truncation, count meanings, and version uncertainty.

### Phase 3: delegated authentication, live contracts, and diagnostics

Outcome: the same Python and CLI operations work directly or through Aperture without local
provider keys.

- Add typed direct/delegated endpoint settings and the internal authentication seam.
- Guarantee that final delegated requests contain neither BioPortal authorization nor UMLS
  `apiKey`, including credentials inherited from supplied HTTP clients or endpoint URLs.
- Keep every delegated request and pagination step under the configured Aperture connector prefix.
- Preserve proxy-originated statuses in the typed error model.
- Add separately gated, opt-in live provider and Aperture contract checks.
- Add bounded `molu doctor` checks for configuration, reachability, observed statuses, provider
  release visibility, and licensing notices without claiming unobservable root causes.
- Document direct and Aperture configurations, including least-privilege grants and UMLS licensing.

Exit criteria: the same mocked contract suite passes against direct and delegated transports, and
opt-in live checks can exercise both provider paths through a configured Aperture gateway without
printing or forwarding client-side provider credentials.

### Phase 4: release preparation and publication checkpoint

Outcome: users and agents can install a verified artifact rather than depending on a source
checkout.

- Move development tools to a uv dependency group and pin the chosen quality-tool policy.
- Add CLI integration coverage, including JSON output and exit codes.
- Decide how the agent skill and reference docs are distributed with or alongside the package.
- Prepare release notes and verify the artifact after the hardened contract is stable.
- Make tagging, GitHub release creation, and package publication a deliberate checkpoint requiring
  explicit release authority and the necessary credentials.

Exit criteria: a clean checkout can run the documented development commands, CI enforces the same
checks, the candidate artifact supports the documented installation paths, and publication either
has explicit approval or remains a clearly identified next action.

### Phase 5: agent-ready terminology workflow

Outcome: a fresh agent can discover and use the gateway safely.

- Add ontology catalog, versions, capabilities, and licensing resources.
- Implement inspectable profiles, beginning with `radiology`.
- Add bounded batch lookup and BioPortal annotation with per-item errors.
- Keep Python, CLI JSON, and MCP schemas in parity.
- Introduce narrow MCP tools only after the normalized models and errors are stable.

Exit criteria: an agent can discover availability, search or annotate, validate a selected
concept, and explain any ambiguity or partial result without parsing console prose.

### Phase 6: bounded graph context and typed mappings

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
