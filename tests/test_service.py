"""Facade / lookup routing tests (mocked HTTP)."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from med_ontology_lookup.errors import ProviderAggregateError, ProviderError
from med_ontology_lookup.models import (
    Backend,
    Concept,
    FailureCategory,
    ProviderFailure,
    ProviderOperation,
    SearchHit,
    SearchResults,
)
from med_ontology_lookup.service import OntologyLookup

BP = "https://data.bioontology.org"
UMLS = "https://uts-ws.nlm.nih.gov/rest"


@pytest.fixture
def mol():
    return OntologyLookup(bioportal_api_key="bp-key", umls_api_key="umls-key")


@respx.mock
@pytest.mark.asyncio
async def test_lookup_term_searches_bioportal(mol: OntologyLookup):
    respx.get(f"{BP}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "totalCount": 1,
                "pageCount": 1,
                "page": 1,
                "collection": [
                    {
                        "@id": "http://purl.bioontology.org/ontology/SNOMEDCT/36118008",
                        "prefLabel": "Pneumothorax",
                        "synonym": [],
                        "links": {"ontology": f"{BP}/ontologies/SNOMEDCT", "ui": ""},
                    }
                ],
            },
        )
    )
    bp_only = OntologyLookup(bioportal_api_key="bp-key", umls_api_key="")
    async with bp_only:
        result = await bp_only.lookup("pneumothorax")
    assert isinstance(result, SearchResults)
    assert result.results[0].pref_label == "Pneumothorax"


@respx.mock
@pytest.mark.asyncio
async def test_lookup_cui_gets_umls(mol: OntologyLookup):
    respx.get(f"{UMLS}/content/current/CUI/C0032326").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "ui": "C0032326",
                    "name": "Pneumothorax",
                    "semanticTypes": [{"name": "Disease or Syndrome"}],
                }
            },
        )
    )
    respx.get(f"{UMLS}/content/current/CUI/C0032326/definitions").mock(
        return_value=httpx.Response(200, json={"result": "NONE"})
    )
    async with mol:
        result = await mol.lookup("C0032326")
    assert isinstance(result, Concept)
    assert result.pref_label == "Pneumothorax"
    assert result.code == "C0032326"


def test_no_keys_raises():
    empty = OntologyLookup(bioportal_api_key="", umls_api_key="")
    # force empty keys
    empty._bioportal.api_key = None
    empty._umls.api_key = None
    with pytest.raises(ValueError, match="No API keys"):
        empty._resolve_backends("auto")


@respx.mock
@pytest.mark.asyncio
async def test_search_maps_snomedct_us_to_bioportal_acronym(mol: OntologyLookup):
    route = respx.get(f"{BP}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "totalCount": 0,
                "pageCount": 1,
                "page": 1,
                "collection": [],
            },
        )
    )
    async with mol:
        await mol.search("pneumothorax", ontologies=["SNOMEDCT_US"], backend="bioportal")
    assert route.called
    ontologies = route.calls.last.request.url.params.get("ontologies")
    assert ontologies == "SNOMEDCT"


@respx.mock
@pytest.mark.asyncio
async def test_search_maps_lnc_to_loinc(mol: OntologyLookup):
    route = respx.get(f"{BP}/search").mock(
        return_value=httpx.Response(
            200,
            json={"totalCount": 0, "pageCount": 1, "page": 1, "collection": []},
        )
    )
    async with mol:
        await mol.search("bilirubin", ontologies=["LNC"], backend="bioportal")
    assert route.calls.last.request.url.params.get("ontologies") == "LOINC"


@respx.mock
@pytest.mark.asyncio
async def test_search_warns_when_one_ontology_fails(mol: OntologyLookup):
    def handler(request: httpx.Request) -> httpx.Response:
        onts = request.url.params.get("ontologies")
        if onts == "SNOMEDCT":
            return httpx.Response(500, json={"errors": ["boom"]})
        return httpx.Response(
            200,
            json={
                "totalCount": 1,
                "pageCount": 1,
                "page": 1,
                "collection": [
                    {
                        "@id": "http://www.radlex.org/RID/RID1",
                        "prefLabel": "ok",
                        "synonym": [],
                        "links": {"ontology": f"{BP}/ontologies/RADLEX", "ui": ""},
                    }
                ],
            },
        )

    respx.get(f"{BP}/search").mock(side_effect=handler)
    async with mol:
        result = await mol.search(
            "x",
            ontologies=["RADLEX", "SNOMEDCT"],
            backend="bioportal",
        )
    assert result.results
    assert result.results[0].ontology == "RADLEX"
    assert any("SNOMEDCT" in w for w in result.warnings)


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,category",
    [
        (401, FailureCategory.AUTHENTICATION),
        (403, FailureCategory.AUTHORIZATION),
        (429, FailureCategory.RATE_LIMITED),
        (503, FailureCategory.UNAVAILABLE),
    ],
)
async def test_get_does_not_fallback_after_bioportal_provider_failure(
    mol: OntologyLookup,
    status: int,
    category: FailureCategory,
):
    respx.get(url__regex=rf"{BP}/ontologies/RADLEX/classes/.*").mock(
        return_value=httpx.Response(status, json={"errors": ["provider failure"]})
    )
    umls = respx.get(f"{UMLS}/content/current/source/RADLEX/RID1").mock(
        return_value=httpx.Response(
            200,
            json={"result": {"ui": "RID1", "name": "fallback result"}},
        )
    )

    async with mol:
        with pytest.raises(ProviderError) as exc:
            await mol.get("RID1", ontology="RADLEX")

    assert exc.value.failure.category == category
    assert exc.value.failure.http_status == status
    assert not umls.called


@respx.mock
@pytest.mark.asyncio
async def test_get_falls_back_after_canonical_bioportal_absence(mol: OntologyLookup):
    respx.get(url__regex=rf"{BP}/ontologies/RADLEX/classes/.*").mock(
        return_value=httpx.Response(404, json={"errors": ["missing"]})
    )
    respx.get(f"{BP}/search").mock(
        return_value=httpx.Response(200, json={"collection": [], "totalCount": 0})
    )
    umls = respx.get(f"{UMLS}/content/current/source/RADLEX/RID1").mock(
        return_value=httpx.Response(
            200,
            json={"result": {"ui": "RID1", "name": "UMLS result"}},
        )
    )

    async with mol:
        concept = await mol.get("RID1", ontology="RADLEX")

    assert concept.pref_label == "UMLS result"
    assert umls.called


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,category",
    [
        (401, FailureCategory.AUTHENTICATION),
        (403, FailureCategory.AUTHORIZATION),
        (429, FailureCategory.RATE_LIMITED),
        (503, FailureCategory.UNAVAILABLE),
    ],
)
async def test_lookup_does_not_search_after_bioportal_provider_failure(
    status: int,
    category: FailureCategory,
):
    mol = OntologyLookup(bioportal_api_key="bp-key", umls_api_key="")
    respx.get(url__regex=rf"{BP}/ontologies/RADLEX/classes/.*").mock(
        return_value=httpx.Response(status, json={"errors": ["provider failure"]})
    )
    search = respx.get(f"{BP}/search").mock(
        return_value=httpx.Response(
            200,
            json={"totalCount": 0, "pageCount": 1, "page": 1, "collection": []},
        )
    )

    async with mol:
        with pytest.raises(ProviderError) as exc:
            await mol.lookup("RID1")

    assert exc.value.failure.category == category
    assert not search.called


@respx.mock
@pytest.mark.asyncio
async def test_hierarchy_does_not_fallback_after_bioportal_rate_limit(
    mol: OntologyLookup,
):
    respx.get(url__regex=rf"{BP}/ontologies/RADLEX/classes/.*").mock(
        return_value=httpx.Response(429, json={"errors": ["rate limited"]})
    )
    umls = respx.get(f"{UMLS}/content/current/source/RADLEX/RID1/parents").mock(
        return_value=httpx.Response(200, json={"result": []})
    )

    async with mol:
        with pytest.raises(ProviderError) as exc:
            await mol.parents("RID1", ontology="RADLEX")

    assert exc.value.failure.category == FailureCategory.RATE_LIMITED
    assert not umls.called


@pytest.mark.asyncio
async def test_lookup_uses_exact_search_after_typed_absence(mol: OntologyLookup):
    mol.get = AsyncMock(
        side_effect=ProviderError(
            ProviderFailure(
                provider=Backend.BIOPORTAL,
                operation=ProviderOperation.GET_CONCEPT,
                category=FailureCategory.NOT_FOUND,
                endpoint=f"{BP}/ontologies/RADLEX/classes/RID1",
                http_status=404,
                ontology="RADLEX",
            )
        )
    )
    expected = SearchResults(query="RID1", results=[], backend=Backend.BIOPORTAL)
    mol.search = AsyncMock(return_value=expected)

    result = await mol.lookup("RID1")

    assert result is expected
    mol.search.assert_awaited_once_with(
        "RID1",
        ontologies=["RADLEX"],
        limit=15,
        exact=True,
    )


@pytest.mark.asyncio
async def test_hierarchy_valid_empty_result_does_not_fallback(mol: OntologyLookup):
    mol.bioportal.parents = AsyncMock(return_value=[])
    mol.umls.parents = AsyncMock(return_value=[])

    result = await mol.parents("RID1", ontology="RADLEX")

    assert result == []
    mol.umls.parents.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_propagates_unexpected_provider_exception(mol: OntologyLookup):
    mol.bioportal.search_balanced = AsyncMock(side_effect=AssertionError("adapter bug"))
    mol.umls.search = AsyncMock(
        return_value=SearchResults(
            query="x",
            total_count=1,
            results=[
                SearchHit(
                    concept_id="C0000001",
                    code="C0000001",
                    ontology="UMLS",
                    pref_label="x",
                    backend=Backend.UMLS,
                )
            ],
        )
    )

    with pytest.raises(AssertionError, match="adapter bug"):
        await mol.search("x", ontologies=["RADLEX"], backend="both")


@pytest.mark.asyncio
async def test_search_propagates_provider_task_cancellation(mol: OntologyLookup):
    mol.bioportal.search_balanced = AsyncMock(side_effect=asyncio.CancelledError())
    mol.umls.search = AsyncMock(
        return_value=SearchResults(
            query="x",
            total_count=1,
            results=[
                SearchHit(
                    concept_id="C0000001",
                    code="C0000001",
                    ontology="UMLS",
                    pref_label="x",
                    backend=Backend.UMLS,
                )
            ],
        )
    )

    with pytest.raises(asyncio.CancelledError):
        await mol.search("x", ontologies=["RADLEX"], backend="both")


@respx.mock
@pytest.mark.asyncio
async def test_search_keeps_valid_empty_success_when_other_provider_fails(
    mol: OntologyLookup,
):
    respx.get(f"{BP}/search").mock(
        return_value=httpx.Response(
            200,
            json={"totalCount": 0, "pageCount": 1, "page": 1, "collection": []},
        )
    )
    respx.get(f"{UMLS}/search/current").mock(
        return_value=httpx.Response(503, json={"error": "unavailable"})
    )

    async with mol:
        result = await mol.search("x", ontologies=["RADLEX"], backend="both")

    assert result.results == []
    assert any("umls" in warning for warning in result.warnings)
    assert [failure.category for failure in result.failures] == [FailureCategory.UNAVAILABLE]


@respx.mock
@pytest.mark.asyncio
async def test_search_keeps_authentication_failure_visible_with_empty_umls_success(
    mol: OntologyLookup,
):
    respx.get(f"{BP}/search").mock(
        return_value=httpx.Response(401, json={"errors": ["unauthorized"]})
    )
    respx.get(f"{UMLS}/search/current").mock(
        return_value=httpx.Response(
            200,
            json={"result": {"recCount": 0, "results": [{"ui": "NONE"}]}},
        )
    )

    async with mol:
        result = await mol.search("x", ontologies=["RADLEX"], backend="both")

    assert result.results == []
    assert [failure.category for failure in result.failures] == [FailureCategory.AUTHENTICATION]
    assert any("authentication" in warning for warning in result.warnings)


@respx.mock
@pytest.mark.asyncio
async def test_search_raises_typed_aggregate_when_every_provider_fails(
    mol: OntologyLookup,
):
    respx.get(f"{BP}/search").mock(
        return_value=httpx.Response(401, json={"errors": ["unauthorized"]})
    )
    respx.get(f"{UMLS}/search/current").mock(
        return_value=httpx.Response(503, json={"error": "unavailable"})
    )

    async with mol:
        with pytest.raises(ProviderAggregateError) as caught:
            await mol.search("x", ontologies=["RADLEX"], backend="both")

    assert [failure.provider for failure in caught.value.failures] == [
        Backend.BIOPORTAL,
        Backend.UMLS,
    ]
    assert [failure.category for failure in caught.value.failures] == [
        FailureCategory.AUTHENTICATION,
        FailureCategory.UNAVAILABLE,
    ]


def test_interleave_preserves_source_order_within_ontology():
    from med_ontology_lookup.models import Backend, SearchHit

    def hit(label: str, exact: bool = False) -> SearchHit:
        return SearchHit(
            concept_id=label,
            code=label,
            ontology="SNOMEDCT",
            pref_label=label,
            backend=Backend.BIOPORTAL,
            exact_match=exact,
        )

    # API order: zebra, apple (non-exact); banana is exact and should rise first
    hits = [hit("zebra"), hit("apple"), hit("banana", exact=True)]
    ordered = OntologyLookup._interleave_by_ontology(hits, limit=10)
    assert [h.pref_label for h in ordered] == ["banana", "zebra", "apple"]
