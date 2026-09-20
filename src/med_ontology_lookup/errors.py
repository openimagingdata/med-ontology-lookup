"""Typed, credential-safe provider failures."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Iterable, Sequence
from typing import TypeVar

import httpx

from med_ontology_lookup.http_util import sanitize_endpoint
from med_ontology_lookup.models import (
    Backend,
    FailureCategory,
    ProviderFailure,
    ProviderOperation,
    StatusOrigin,
)

T = TypeVar("T")


class ProviderFailureError(Exception):
    """Base class for one or more expected external provider failures."""

    failures: tuple[ProviderFailure, ...]

    def __init__(self, failures: Iterable[ProviderFailure], message: str) -> None:
        collected = tuple(failures)
        if not collected:
            raise ValueError("ProviderFailureError requires at least one failure")
        self.failures = collected
        super().__init__(message)


class ProviderError(ProviderFailureError):
    """One failed provider operation."""

    failure: ProviderFailure

    def __init__(self, failure: ProviderFailure) -> None:
        self.failure = failure
        super().__init__((failure,), failure.summary())


class ProviderAggregateError(ProviderFailureError):
    """Every call in a provider aggregation failed."""

    def __init__(self, failures: Iterable[ProviderFailure]) -> None:
        collected = tuple(failures)
        noun = "failure" if len(collected) == 1 else "failures"
        super().__init__(
            collected,
            f"All attempted provider calls failed ({len(collected)} {noun})",
        )


def _failure(
    *,
    provider: Backend,
    operation: ProviderOperation,
    category: FailureCategory,
    endpoint: str,
    http_status: int | None = None,
    ontology: str | None = None,
) -> ProviderFailure:
    return ProviderFailure(
        provider=provider,
        operation=operation,
        category=category,
        endpoint=sanitize_endpoint(endpoint),
        http_status=http_status,
        status_origin=StatusOrigin.UNKNOWN,
        ontology=ontology,
    )


def error_for_status(
    response: httpx.Response,
    *,
    provider: Backend,
    operation: ProviderOperation,
    ontology: str | None = None,
    allow_canonical_not_found: bool = False,
) -> ProviderError:
    """Translate an unsuccessful response without retaining request or body."""
    status = response.status_code
    if status == 404 and allow_canonical_not_found:
        category = FailureCategory.NOT_FOUND
    elif status == 401:
        category = FailureCategory.AUTHENTICATION
    elif status == 403:
        category = FailureCategory.AUTHORIZATION
    elif status == 429:
        category = FailureCategory.RATE_LIMITED
    elif status in {408, 504}:
        category = FailureCategory.TIMEOUT
    elif 500 <= status <= 599:
        category = FailureCategory.UNAVAILABLE
    else:
        category = FailureCategory.HTTP_ERROR
    return ProviderError(
        _failure(
            provider=provider,
            operation=operation,
            category=category,
            endpoint=str(response.request.url),
            http_status=status,
            ontology=ontology,
        )
    )


def error_for_request(
    exc: httpx.RequestError,
    *,
    provider: Backend,
    operation: ProviderOperation,
    endpoint: str,
    ontology: str | None = None,
) -> ProviderError | None:
    """Translate expected remote transport failures; return None for local misuse."""
    if isinstance(exc, httpx.TimeoutException):
        category = FailureCategory.TIMEOUT
    elif isinstance(exc, (httpx.ProxyError, httpx.NetworkError)):
        category = FailureCategory.CONNECTION
    elif isinstance(exc, httpx.DecodingError):
        category = FailureCategory.INVALID_RESPONSE
    elif isinstance(exc, (httpx.RemoteProtocolError, httpx.TooManyRedirects)):
        category = FailureCategory.TRANSPORT
    else:
        return None
    return ProviderError(
        _failure(
            provider=provider,
            operation=operation,
            category=category,
            endpoint=endpoint,
            ontology=ontology,
        )
    )


def decode_json(
    response: httpx.Response,
    *,
    provider: Backend,
    operation: ProviderOperation,
    ontology: str | None = None,
) -> object:
    """Decode JSON and translate only failures from the decoding expression."""
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ProviderError(
            _failure(
                provider=provider,
                operation=operation,
                category=FailureCategory.INVALID_JSON,
                endpoint=str(response.request.url),
                http_status=response.status_code,
                ontology=ontology,
            )
        ) from None


def invalid_response(
    *,
    provider: Backend,
    operation: ProviderOperation,
    endpoint: str,
    ontology: str | None = None,
    http_status: int | None = None,
) -> ProviderError:
    """Build a safe invalid-response error without retaining validation input."""
    return ProviderError(
        _failure(
            provider=provider,
            operation=operation,
            category=FailureCategory.INVALID_RESPONSE,
            endpoint=endpoint,
            http_status=http_status,
            ontology=ontology,
        )
    )


async def _capture_provider_failure(
    awaitable: Awaitable[T],
) -> T | ProviderFailureError:
    try:
        return await awaitable
    except ProviderFailureError as exc:
        return exc


async def gather_provider_calls(
    awaitables: Sequence[Awaitable[T]],
) -> list[T | ProviderFailureError]:
    """Collect typed failures, but clean up and preserve unexpected exceptions."""
    tasks = [asyncio.create_task(_capture_provider_failure(item)) for item in awaitables]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def flatten_failures(errors: Iterable[ProviderFailureError]) -> list[ProviderFailure]:
    """Preserve every failure from nested provider aggregations."""
    return [failure for error in errors for failure in error.failures]


__all__ = [
    "FailureCategory",
    "ProviderAggregateError",
    "ProviderError",
    "ProviderFailure",
    "ProviderFailureError",
    "ProviderOperation",
    "StatusOrigin",
]
