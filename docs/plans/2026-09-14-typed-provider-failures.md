# Typed Provider Failures and Operation-Aware Fallback

**Status:** complete
**Date:** 2026-09-14
**Issue:** [#3 — Model typed provider failures and operation-aware fallback](https://github.com/openimagingdata/med-ontology-lookup/issues/3)

## Goal

Give the BioPortal and UMLS adapters one small, typed failure interface so the
`OntologyLookup` facade can distinguish expected absence or unsupported operations from actual
provider failures. Fallback and partial-result behavior must be deliberate, operation-specific,
credential-safe, and consistent across Python and CLI callers.

## Plan

- [x] Record this executable plan in `docs/plans/` before diagnosis or implementation.
- [x] Re-read repository context, architectural decisions, issue #3, the adapter/facade call paths,
  tests, CLI serialization, and documentation affected by the public failure contract.
- [x] Research the current official `httpx`, Python asynchronous-task/cancellation, and Pydantic
  guidance needed for exception translation and stable structured output; record any constraints
  that change this plan.
- [x] Build and run a fast deterministic regression loop that reproduces the reported failure:
  non-fallback BioPortal failures must not become a UMLS success, exact-search fallback, or empty
  success. Minimize it to the public facade seam.
- [x] Record and test 3–5 ranked, falsifiable hypotheses about where provider failures lose their
  meaning, then retain the smallest correct explanation.
- [x] Design the failure module at the adapter–facade seam and document its interface before
  implementation. It must represent provider, operation, category, sanitized endpoint, optional
  HTTP status, and known/unknown status origin without exposing credentials.
- [x] Define the operation-specific fallback matrix. Only adapter-classified absence or unsupported
  operations may trigger fallback; authentication, authorization, licensing, rate limiting,
  timeout/connection, upstream unavailability, invalid JSON, and invalid successful response
  shapes remain visible.
- [x] Have a `gpt-6-astra` subagent review this plan, the proposed failure interface, fallback
  matrix, regression seam, compatibility impact, and issue boundaries; incorporate accepted
  feedback into this document before implementation.
- [x] Add red regression tests first for `get`, `lookup`, hierarchy, search aggregation, malformed
  responses, cancellation, and secret redaction. Confirm the focused feedback loop fails for the
  intended reason.
- [x] Implement centralized HTTP/response translation in the provider adapters and consume only
  typed provider failures in the facade. Do not catch unexpected programming exceptions or task
  cancellation as normal provider outcomes.
- [x] Replace broad `gather(return_exceptions=True)` result handling with concurrency behavior that
  preserves typed partial provider outcomes while propagating unexpected exceptions and
  cancellation.
- [x] Expose stable typed failure/warning fields through Python models and CLI JSON while retaining
  concise human-readable CLI errors and avoiding unrelated collection/provenance redesign owned by
  issues #6 and #7.
- [x] Run focused regressions after each seam change, then the complete test, type, lint, build,
  metadata, and installed-wheel smoke checks available in the repository.
- [x] Update public documentation for failure and fallback semantics, add a concise external-facing
  `CHANGELOG.md` entry for behavior changes, and record implementation decisions in `DEV_LOG.md`.
- [x] Perform the final documentation review: reconcile this plan with the actual implementation,
  mark it complete, verify related reference docs and issue #3 acceptance criteria, and ensure
  `DEV_LOG.md`/`CHANGELOG.md` describe the final state accurately.

## Intended issue boundary

This issue owns provider-failure classification, adapter-to-facade translation, fallback policy,
partial failure representation, cancellation propagation, and credential-safe error rendering. It
does not own retry/circuit-breaking, backend-selection semantics (#4), collection pagination and
completeness (#6), full provenance envelopes (#7), delegated transport configuration (#9), or
diagnostic root-cause inference (#11).

## Public failure contract

Add a public `errors` module and export its interface from the package root:

```text
ProviderFailure
  provider: Backend
  operation: ProviderOperation
  category: FailureCategory
  endpoint: str
  http_status: int | None
  status_origin: StatusOrigin
  ontology: str | None

ProviderFailureError(Exception)
  failures: nonempty tuple[ProviderFailure, ...]

ProviderError(ProviderFailureError)
  failure: ProviderFailure

ProviderAggregateError(ProviderFailureError)
  failures: nonempty tuple[ProviderFailure, ...]
```

`ProviderOperation` will cover the existing remote calls: search, class resolution, concept
detail, definitions, atoms, source detail, parents, and children. `FailureCategory` will contain
`not_found`, `unsupported_operation`, `authentication`, `authorization`, `licensing`,
`rate_limited`, `timeout`, `connection`, `unavailable`, `invalid_json`, `invalid_response`,
`transport`, and `http_error`. `StatusOrigin` will contain `provider`, `proxy`, and `unknown`.

The failure record contains facts, not policy: it will not carry universal `retryable` or
`fallback_allowed` flags. Adapters classify responses; each facade operation decides whether a
classified event permits fallback. No error object retains raw HTTPX request/response objects,
headers, bodies, validation inputs, or chained secret-bearing exceptions.

For compatibility, keep `SearchResults.warnings: list[str]` and add
`SearchResults.failures: list[ProviderFailure]`. Warning text is derived only from the same safe
fields. Existing successful return types stay unchanged.

Provider CLI failures use stderr, exit status 1, and this JSON shape when `--output json` is
selected:

```json
{
  "error": {
    "code": "provider_failure",
    "message": "All attempted providers failed",
    "failures": []
  }
}
```

Actual error output always has a nonempty `failures` list. Table-mode output remains concise. The
CLI will never print a provider response body or raw exception string.

## Classification evidence

Classification is conservative and operation-specific:

- Status origin remains `unknown` in #3 unless the response carries explicit, verified origin
  evidence. A canonical URL alone does not prove that no intermediary generated the response.
- For compatibility with existing direct-provider behavior, a `404` from the canonical BioPortal
  or UMLS route is classified as `not_found` only for a resource-detail or relationship operation
  whose path already names the requested resource. This is a narrow compatibility assumption, not
  proof of actual response origin, so `status_origin` remains `unknown`. A search-endpoint `404` is
  `http_error`.
- An unknown-origin `404` is `http_error`, never absence, because it may be a connector-routing
  failure, except for the explicitly documented canonical-route compatibility assumption above.
  A custom endpoint never receives that assumption. Issue #9 may supply explicit proxy evidence
  later.
- A BioPortal class-resolution probe may advance after a canonical-route `400` only when the
  deliberately tried candidate is a bare short code and a bounded parsed error envelope contains
  the existing provider-specific `not a valid IRI` signal. This preserves current short-code
  compatibility but is not claimed as an official provider guarantee or a general
  `400 == not_found` rule. A `400` for an IRI, a custom endpoint, an unrecognized envelope, or an
  invalid envelope raises.
- `401` is `authentication`; `403` is `authorization`; `429` is `rate_limited`; representative
  upstream `5xx` statuses are `unavailable`; other statuses are `http_error`. No response text is
  inspected to guess licensing or unsupported capability.
- `unsupported_operation` is emitted only from an explicit adapter capability rule or a future
  documented provider signature, not inferred from arbitrary `405` or `501` responses.
- HTTPX timeout classes map to `timeout`; network/proxy errors map to `connection`; remote content
  decoding and redirect failures map to `transport` or `invalid_response`. Local protocol misuse,
  unsupported URL schemes, invalid URLs, stream misuse, and internal programming exceptions
  propagate unchanged.
- JSON decoding is isolated around `response.json()` and maps to `invalid_json`. Endpoint-specific
  minimal shape validation maps to `invalid_response`; unknown extra fields remain allowed.

The provider documentation reviewed for this issue does not establish a trustworthy response-body
signature for general absence or unsupported operation. Tests therefore record the conservative
rules above instead of treating guessed body text as a provider guarantee.

## Fallback matrix

| Operation or event | Required action |
| --- | --- |
| BioPortal bare-short-code probe receives its recognized canonical-provider invalid-candidate response | Try the generated IRI candidate |
| BioPortal candidate probe receives positively classified provider absence | Try the next candidate |
| Candidate probe receives unknown-origin `404`, invalid JSON/shape, or another failure | Raise and do not cache the candidate |
| All candidate probes are expected misses | Run the existing exact code-resolution search without changing match rules |
| `get` receives BioPortal `not_found` or explicit `unsupported_operation` | Try UMLS only when current routing already permits it |
| `parents`/`children` receive BioPortal `not_found` or explicit `unsupported_operation` | Try UMLS only when current routing already permits it |
| Hierarchy receives a valid empty collection | Return empty; do not fall back |
| `lookup` direct code lookup ends in `not_found` or `unsupported_operation` | Run the existing exact-search fallback |
| `lookup` receives configuration, auth/rate/server/transport/response failure, cancellation, or unexpected exception | Raise; do not search |
| UMLS definitions receive canonical-provider `not_found` | Return an empty list |
| UMLS definitions receive unknown-origin `404` or another failure | Raise |
| Search has at least one successful call, including a valid empty response | Return merged successes with typed failures and compatible warnings |
| Every attempted search call fails | Raise `ProviderAggregateError` preserving every typed failure |
| Any operation receives cancellation or an unexpected programming exception | Cancel/drain sibling tasks where applicable and re-raise the original exception |

## Concurrency and partial success

Do not replace `gather(return_exceptions=True)` mechanically with `TaskGroup`: TaskGroup would
cancel siblings and wrap ordinary child failures in an exception group, changing the public
exception shape. Add a small internal gather helper that captures only `ProviderFailureError` as a
result. On any unexpected `BaseException` or cancellation, it cancels and drains unfinished
siblings and re-raises the original exception unchanged.

Both aggregation layers count successful calls, not returned hits. Consequently, a valid empty
response plus a provider failure is a partial success with `results=[]` and typed failures; only
zero successful calls is total failure. Inner BioPortal aggregate failures are flattened into the
outer provider aggregate without losing ontology context.

## Response validation

Validate only the minimum shape each endpoint needs, while allowing unknown fields:

- BioPortal search requires an object with a list `collection`; every search member requires a
  nonempty string `@id`, a nonempty string `prefLabel`, and a usable ontology link. Class detail
  and successful class probes require nonempty string `@id` and `prefLabel`. Hierarchy accepts a
  list or an object with a list `collection`; every node requires a nonempty string `@id`, while a
  missing label retains the existing explicit code-label fallback. Fields that are present with
  incompatible types are invalid.
- UMLS responses require an object with `result`. Search requires a result object with a list
  `results`; non-sentinel members require nonempty string `ui`, `name`, and `rootSource` fields.
  CUI and source detail require a result object with nonempty string `ui` and `name` fields.
  Definitions require string `value` members. Atoms require nonempty `rootSource`, `name`, and a
  usable `code` or `sourceConcept` reference. Hierarchy nodes require a nonempty string `ui` and
  accept a missing label or root source only through the existing explicit request-derived
  fallbacks. Fields that are present with incompatible types are invalid.
- Definitions, atoms, and hierarchy accept the documented `NONE` sentinel as empty; search keeps
  the existing `ui=NONE` no-result sentinel. Any other string in a collection position is invalid.
- Missing envelopes, wrong collection types, malformed members, and invalid JSON are failures,
  rather than silently becoming empty results. Valid empty lists and UMLS `NONE` remain successes.

Shape checks live beside provider mapping code. Only explicit validation failures are translated,
so an unrelated `TypeError`, `AssertionError`, or other implementation defect still propagates.

## Regression loop and hypotheses

The red-capable command is a small `uv run python` facade call with mocked transports. BioPortal
returns `401`, UMLS would return a valid concept, and the command asserts both that the `401`
raises and that UMLS was not called. On the original implementation it exits 1 with:

```text
AssertionError: BioPortal 401 was hidden by UMLS fallback
```

The ranked causes and falsifying regressions are:

1. Broad facade catches cause fallthrough; restricting fallback to typed absence must prevent the
   UMLS route from being called.
2. Raw HTTPX exceptions erase provider meaning; adapter translation must expose stable category,
   operation, origin, and safe endpoint fields.
3. `gather(return_exceptions=True)` turns arbitrary exceptions/cancellation into data; the new
   helper must propagate them and clean up siblings.
4. Aggregators infer success from hits; explicit success counts must preserve valid empty partial
   results.
5. Missing response-shape checks masquerade as empty success; malformed successful responses must
   raise `invalid_response`.

## Compatibility and issue boundary

- This is an additive model change for successful search JSON (`failures` defaults to an empty
  list) and a deliberate error-contract change from raw HTTPX exceptions to public library
  exceptions.
- Existing `warnings` remain strings. Singular and list success envelopes do not change in #3.
- The fixture that currently configures both providers while mocking only BioPortal will be made
  explicit, so an unmocked request cannot masquerade as a tolerated partial failure.
- Backend preference and readiness remain #4; normalization remains #5; pagination/count envelope
  redesign remains #6; full provenance remains #7; delegated credential/routing configuration
  remains #9; diagnostic inference remains #11.
- Documentation will include a README Python exception example, CLI JSON error example, an
  `Unreleased` changelog entry, final plan reconciliation, and a `DEV_LOG.md` decision record.

## Review notes

Independent `gpt-6-astra` review completed on 2026-09-14, followed by a blocker-only second pass.
The plan was expanded from a checklist
into a concrete interface and policy. Accepted corrections include conservative absence evidence,
safe-field-only CLI errors, explicit success counting, endpoint-shape validation, propagation of
suppressed lookup/crosswalk failures, original-exception-preserving concurrency cleanup, and an
additive typed `failures` field alongside compatible string warnings.

The second pass removed URL-only claims about response origin, labeled canonical-route `404`
handling as a narrow compatibility assumption, required a parsed provider-specific signal for the
bare-code `400` path, and specified correctly typed identity fields for successful payloads. No
review blocker remains.

Current official documentation confirmed that HTTPX separates request/transport failures from
`HTTPStatusError`, that its content `DecodingError` is not JSON decoding, and that
`gather(return_exceptions=True)` treats exceptions as results. Python documentation also requires
`CancelledError` to propagate after cleanup and notes TaskGroup's sibling cancellation and
exception-group behavior. These constraints produced the explicit gather-helper decision above.

## Completion notes

Completed on 2026-09-14. The implementation adds the public `ProviderFailure` model and
`ProviderFailureError` hierarchy; centralized status, request, JSON, and response-shape translation;
operation-aware facade fallback; typed partial search failures; safe CLI JSON errors; and explicit
concurrent-task cleanup. BioPortal and UMLS now validate the minimum identity and collection fields
their mappers require instead of coercing malformed successes into empty or plausible-looking data.

The original BioPortal-`401` facade regression failed against the former behavior because UMLS
fallback hid the authentication failure. It now raises `ProviderError`, and the regression set also
covers `403`, `429`, upstream `5xx`, typed absence fallback, exact-search fallback, custom-endpoint
`404`, valid empty results, partial and total search failure, malformed endpoint payloads, timeout and
connection categories, unexpected exceptions, cancellation cleanup, CLI JSON structure, and secret
redaction.

Final verification:

- `121 passed` under each supported Python version, 3.11, 3.12, 3.13, and 3.14, using isolated
  project environments.
- The locked `ty` check reported zero errors; Ruff lint and format checks passed;
  `git diff --check` passed.
- `uv build` produced the sdist and wheel; Twine accepted both artifacts; an isolated environment
  imported the public failure API from the built wheel successfully.
- Top-level and search-command help plus `molu version` completed successfully.

The final documentation review updated `README.md`, `CHANGELOG.md`, and `DEV_LOG.md`. The project
proposal and reviewed backlog remain accurate: this change completes the implementation scope of
issue #3 without taking on backend readiness (#4), delegated authentication (#9), retries,
pagination/completeness, or provenance redesign. Issue #3 remains open for maintainer review before
the implementation is committed or proposed for merge.
