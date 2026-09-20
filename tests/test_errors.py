"""Typed provider failure and concurrency contracts."""

import asyncio

import httpx
import pytest

from med_ontology_lookup.errors import (
    ProviderAggregateError,
    ProviderError,
    decode_json,
    error_for_request,
    error_for_status,
    gather_provider_calls,
)
from med_ontology_lookup.http_util import sanitize_endpoint
from med_ontology_lookup.models import (
    Backend,
    FailureCategory,
    ProviderFailure,
    ProviderOperation,
    StatusOrigin,
)


def failure(category: FailureCategory = FailureCategory.UNAVAILABLE) -> ProviderFailure:
    return ProviderFailure(
        provider=Backend.BIOPORTAL,
        operation=ProviderOperation.SEARCH,
        category=category,
        endpoint="https://data.bioontology.org/search",
    )


def test_provider_error_exposes_only_safe_typed_details():
    exc = ProviderError(failure(FailureCategory.AUTHENTICATION))
    assert exc.failures == (exc.failure,)
    assert "authentication" in str(exc)
    assert exc.failure.model_dump(mode="json")["provider"] == "bioportal"


def test_provider_failure_sanitizes_directly_supplied_endpoint():
    record = ProviderFailure(
        provider=Backend.UMLS,
        operation=ProviderOperation.SEARCH,
        category=FailureCategory.AUTHENTICATION,
        endpoint="https://user:password@example.test/search?apiKey=secret&q=patient#details",
    )
    assert record.endpoint == "https://example.test/search"


def test_provider_aggregate_requires_failures():
    with pytest.raises(ValueError, match="at least one"):
        ProviderAggregateError([])


def test_sanitize_endpoint_removes_all_credentials_and_query_data():
    value = sanitize_endpoint(
        "https://user:password@example.test:8443/path?apiKey=secret&q=patient#fragment"
    )
    assert value == "https://example.test:8443/path"


def test_status_translation_is_typed_and_origin_stays_unknown():
    request = httpx.Request("GET", "https://example.test/search?q=patient&apiKey=secret")
    response = httpx.Response(429, request=request)
    exc = error_for_status(
        response,
        provider=Backend.UMLS,
        operation=ProviderOperation.SEARCH,
    )
    assert exc.failure.category == FailureCategory.RATE_LIMITED
    assert exc.failure.status_origin == StatusOrigin.UNKNOWN
    assert exc.failure.endpoint == "https://example.test/search"
    assert "secret" not in str(exc)
    assert "patient" not in str(exc)


def test_invalid_json_does_not_retain_response_body():
    request = httpx.Request("GET", "https://example.test/search?apiKey=secret")
    response = httpx.Response(200, request=request, text='{"echoed": "other-secret"')
    with pytest.raises(ProviderError) as caught:
        decode_json(
            response,
            provider=Backend.UMLS,
            operation=ProviderOperation.SEARCH,
        )
    assert caught.value.failure.category == FailureCategory.INVALID_JSON
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "exception_type,category",
    [
        (httpx.ConnectTimeout, FailureCategory.TIMEOUT),
        (httpx.ConnectError, FailureCategory.CONNECTION),
        (httpx.ProxyError, FailureCategory.CONNECTION),
        (httpx.RemoteProtocolError, FailureCategory.TRANSPORT),
        (httpx.DecodingError, FailureCategory.INVALID_RESPONSE),
    ],
)
def test_remote_request_failures_have_distinct_categories(
    exception_type: type[httpx.RequestError],
    category: FailureCategory,
):
    request = httpx.Request("GET", "https://example.test/search?apiKey=secret")
    translated = error_for_request(
        exception_type("provider failed", request=request),
        provider=Backend.UMLS,
        operation=ProviderOperation.SEARCH,
        endpoint=str(request.url),
    )
    assert translated is not None
    assert translated.failure.category == category
    assert translated.failure.endpoint == "https://example.test/search"


def test_local_request_misuse_is_not_translated():
    request = httpx.Request("GET", "https://example.test/search")
    translated = error_for_request(
        httpx.LocalProtocolError("bad local request", request=request),
        provider=Backend.UMLS,
        operation=ProviderOperation.SEARCH,
        endpoint=str(request.url),
    )
    assert translated is None


@pytest.mark.asyncio
async def test_gather_collects_only_typed_provider_failures():
    async def ok() -> int:
        return 1

    async def provider_failure() -> int:
        raise ProviderError(failure())

    results = await gather_provider_calls([ok(), provider_failure()])
    assert results[0] == 1
    assert isinstance(results[1], ProviderError)


@pytest.mark.asyncio
async def test_gather_propagates_unexpected_exception_and_drains_sibling():
    cleaned_up = asyncio.Event()

    async def slow() -> int:
        try:
            await asyncio.Event().wait()
        finally:
            cleaned_up.set()
        return 0

    async def broken() -> int:
        await asyncio.sleep(0)
        raise AssertionError("adapter bug")

    with pytest.raises(AssertionError, match="adapter bug"):
        await gather_provider_calls([slow(), broken()])
    assert cleaned_up.is_set()


@pytest.mark.asyncio
async def test_gather_propagates_child_cancellation_and_drains_sibling():
    cleaned_up = asyncio.Event()

    async def slow() -> int:
        try:
            await asyncio.Event().wait()
        finally:
            cleaned_up.set()
        return 0

    async def cancelled() -> int:
        await asyncio.sleep(0)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await gather_provider_calls([slow(), cancelled()])
    assert cleaned_up.is_set()


@pytest.mark.asyncio
async def test_gather_propagates_caller_cancellation_and_drains_children():
    started = asyncio.Event()
    cleaned_up = asyncio.Event()

    async def slow() -> int:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned_up.set()
        return 0

    task = asyncio.create_task(gather_provider_calls([slow()]))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned_up.is_set()
