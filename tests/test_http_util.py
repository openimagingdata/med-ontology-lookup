"""Secret redaction in HTTP error messages."""

import json

from med_ontology_lookup.cli import OutputFormat, _handle_errors
from med_ontology_lookup.errors import ProviderError
from med_ontology_lookup.http_util import format_http_error, redact_secrets, sanitize_url
from med_ontology_lookup.models import (
    Backend,
    FailureCategory,
    ProviderFailure,
    ProviderOperation,
)


def test_sanitize_url_strips_apikey():
    url = "https://uts-ws.nlm.nih.gov/rest/search/current?string=x&apiKey=super-secret"
    out = sanitize_url(url)
    assert "super-secret" not in out
    assert "apiKey" not in out.lower() or "REDACTED" in redact_secrets(url)


def test_redact_secrets_in_free_text():
    text = "Client error for url 'https://uts-ws.nlm.nih.gov/rest/x?apiKey=abc123&q=1'"
    assert "abc123" not in redact_secrets(text)
    assert "REDACTED" in redact_secrets(text)


def test_format_http_error_uses_sanitized_url():
    import httpx

    request = httpx.Request(
        "GET",
        "https://uts-ws.nlm.nih.gov/rest/search/current",
        params={"string": "x", "apiKey": "super-secret"},
    )
    response = httpx.Response(401, request=request)
    exc = httpx.HTTPStatusError("nope", request=request, response=response)
    msg = format_http_error(exc)
    assert "super-secret" not in msg
    assert "401" in msg


def test_handle_errors_does_not_print_apikey(capsys):
    import httpx
    import pytest
    import typer

    request = httpx.Request(
        "GET",
        "https://uts-ws.nlm.nih.gov/rest/search/current?apiKey=super-secret",
    )
    response = httpx.Response(
        401,
        request=request,
        text='{"echoedAuthorization": "Bearer arbitrary-secret"}',
    )
    exc = httpx.HTTPStatusError("boom", request=request, response=response)
    with pytest.raises(typer.Exit):
        _handle_errors(exc)
    captured = capsys.readouterr()
    assert "super-secret" not in captured.out
    assert "super-secret" not in captured.err
    assert "arbitrary-secret" not in captured.err


def test_handle_provider_error_prints_typed_json_to_stderr(capsys):
    import pytest
    import typer

    exc = ProviderError(
        ProviderFailure(
            provider=Backend.UMLS,
            operation=ProviderOperation.SEARCH,
            category=FailureCategory.AUTHENTICATION,
            endpoint="https://example.test/search",
            http_status=401,
        )
    )
    with pytest.raises(typer.Exit) as caught:
        _handle_errors(exc, output=OutputFormat.json)
    assert caught.value.exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["error"]["code"] == "provider_failure"
    assert payload["error"]["failures"][0]["category"] == "authentication"
