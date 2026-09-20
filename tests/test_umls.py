"""Mocked UMLS client tests."""

import httpx
import pytest
import respx

from med_ontology_lookup.clients.umls import UMLSClient
from med_ontology_lookup.errors import ProviderError
from med_ontology_lookup.models import Backend, FailureCategory, StatusOrigin

BASE = "https://uts-ws.nlm.nih.gov/rest"


@pytest.fixture
def client():
    return UMLSClient(api_key="test-key", base_url=BASE, version="current")


@respx.mock
@pytest.mark.asyncio
async def test_search_cui(client: UMLSClient):
    respx.get(f"{BASE}/search/current").mock(
        return_value=httpx.Response(
            200,
            json={
                "pageSize": 25,
                "pageNumber": 1,
                "result": {
                    "classType": "searchResults",
                    "recCount": 1,
                    "results": [
                        {
                            "ui": "C0032326",
                            "rootSource": "MTH",
                            "uri": f"{BASE}/content/current/CUI/C0032326",
                            "name": "Pneumothorax",
                            "semanticTypes": ["Disease or Syndrome"],
                        }
                    ],
                },
            },
        )
    )
    async with client:
        results = await client.search("pneumothorax")
    assert len(results.results) == 1
    hit = results.results[0]
    assert hit.code == "C0032326"
    assert hit.cui == "C0032326"
    assert hit.backend == Backend.UMLS
    assert hit.exact_match is True  # case-insensitive preferred-label match
    assert hit.pref_label == "Pneumothorax"


@respx.mock
@pytest.mark.asyncio
async def test_get_cui(client: UMLSClient):
    respx.get(f"{BASE}/content/current/CUI/C0032326").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "ui": "C0032326",
                    "name": "Pneumothorax",
                    "semanticTypes": [{"name": "Disease or Syndrome", "uri": "..."}],
                }
            },
        )
    )
    async with client:
        concept = await client.get_cui("C0032326")
    assert concept.pref_label == "Pneumothorax"
    assert "Disease or Syndrome" in concept.semantic_types
    assert concept.ontology == "UMLS"


@respx.mock
@pytest.mark.asyncio
async def test_crosswalk_from_cui(client: UMLSClient):
    respx.get(f"{BASE}/content/current/CUI/C0032326").mock(
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
    respx.get(f"{BASE}/content/current/CUI/C0032326/atoms").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": [
                    {
                        "ui": "A123",
                        "name": "Pneumothorax",
                        "rootSource": "SNOMEDCT_US",
                        "termType": "PT",
                        "code": f"{BASE}/content/current/source/SNOMEDCT_US/36118008",
                        "obsolete": "false",
                    },
                    {
                        "ui": "A124",
                        "name": "Pneumothorax",
                        "rootSource": "FMA",
                        "termType": "PT",
                        "code": f"{BASE}/content/current/source/FMA/1224",
                        "obsolete": "false",
                    },
                ]
            },
        )
    )
    async with client:
        result = await client.crosswalk("C0032326", to_sources=["SNOMEDCT_US", "FMA"])
    assert result.cui == "C0032326"
    assert result.preferred_name == "Pneumothorax"
    codes = {(c.source, c.code) for c in result.source_codes}
    assert ("SNOMEDCT_US", "36118008") in codes
    assert ("FMA", "1224") in codes


@respx.mock
@pytest.mark.asyncio
async def test_parents(client: UMLSClient):
    respx.get(f"{BASE}/content/current/source/SNOMEDCT_US/36118008/parents").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": [
                    {
                        "ui": "19829001",
                        "name": "Disorder of lung",
                        "rootSource": "SNOMEDCT_US",
                    }
                ]
            },
        )
    )
    async with client:
        nodes = await client.parents("SNOMEDCT", "36118008")
    assert len(nodes) == 1
    assert nodes[0].code == "19829001"


@respx.mock
@pytest.mark.asyncio
async def test_crosswalk_empty_target_does_not_leak_other_sources(client: UMLSClient):
    """When to_sources has no atoms, do not fall back to every preferred term."""
    respx.get(f"{BASE}/content/current/CUI/C0032326").mock(
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
    # Filtered atoms for FMA only → empty
    respx.get(f"{BASE}/content/current/CUI/C0032326/atoms").mock(
        return_value=httpx.Response(200, json={"result": []})
    )
    async with client:
        result = await client.crosswalk("C0032326", to_sources=["FMA"])
    assert result.cui == "C0032326"
    assert result.source_codes == []


@respx.mock
@pytest.mark.asyncio
async def test_search_rejects_invalid_json(client: UMLSClient):
    respx.get(f"{BASE}/search/current").mock(return_value=httpx.Response(200, text="not-json"))
    async with client:
        with pytest.raises(ProviderError) as caught:
            await client.search("x")
    assert caught.value.failure.category == FailureCategory.INVALID_JSON


@pytest.mark.asyncio
async def test_content_decoding_error_is_typed():
    def raise_decoding_error(request: httpx.Request) -> httpx.Response:
        raise httpx.DecodingError("invalid content encoding", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(raise_decoding_error)) as transport:
        client = UMLSClient(api_key="test-key", base_url=BASE, client=transport)
        with pytest.raises(ProviderError) as caught:
            await client.search("x")
    assert caught.value.failure.category == FailureCategory.INVALID_RESPONSE


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"result": {}},
        {"result": {"results": {}}},
        {"result": {"recCount": "1", "results": []}},
        {"result": {"results": ["not-an-object"]}},
        {"result": {"results": [{"ui": "C0000001", "name": "x"}]}},
        {
            "result": {
                "results": [
                    {
                        "ui": "C0000001",
                        "name": "x",
                        "rootSource": "MTH",
                        "semanticTypes": {},
                    }
                ]
            }
        },
        {
            "result": {
                "results": [
                    {
                        "ui": "C0000001",
                        "name": "x",
                        "rootSource": "MTH",
                        "uri": 123,
                    }
                ]
            }
        },
    ],
)
async def test_search_rejects_invalid_success_shapes(client: UMLSClient, payload: object):
    respx.get(f"{BASE}/search/current").mock(return_value=httpx.Response(200, json=payload))
    async with client:
        with pytest.raises(ProviderError) as caught:
            await client.search("x")
    assert caught.value.failure.category == FailureCategory.INVALID_RESPONSE


@respx.mock
@pytest.mark.asyncio
async def test_search_preserves_non_200_success_status_on_invalid_shape(client: UMLSClient):
    respx.get(f"{BASE}/search/current").mock(return_value=httpx.Response(206, json={}))
    async with client:
        with pytest.raises(ProviderError) as caught:
            await client.search("x")
    assert caught.value.failure.category == FailureCategory.INVALID_RESPONSE
    assert caught.value.failure.http_status == 206


@respx.mock
@pytest.mark.asyncio
async def test_get_cui_rejects_empty_result(client: UMLSClient):
    respx.get(f"{BASE}/content/current/CUI/C0032326").mock(
        return_value=httpx.Response(200, json={"result": {}})
    )
    async with client:
        with pytest.raises(ProviderError) as caught:
            await client.get_cui("C0032326")
    assert caught.value.failure.category == FailureCategory.INVALID_RESPONSE


@respx.mock
@pytest.mark.asyncio
async def test_get_cui_rejects_malformed_semantic_types(client: UMLSClient):
    respx.get(f"{BASE}/content/current/CUI/C0032326").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "ui": "C0032326",
                    "name": "Pneumothorax",
                    "semanticTypes": [{"uri": "missing name"}],
                }
            },
        )
    )
    async with client:
        with pytest.raises(ProviderError) as caught:
            await client.get_cui("C0032326")
    assert caught.value.failure.category == FailureCategory.INVALID_RESPONSE


@respx.mock
@pytest.mark.asyncio
async def test_search_normalizes_mixed_semantic_type_shapes(client: UMLSClient):
    respx.get(f"{BASE}/search/current").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "recCount": 1,
                    "results": [
                        {
                            "ui": "C0032326",
                            "name": "Pneumothorax",
                            "rootSource": "MTH",
                            "semanticTypes": [
                                "Disease or Syndrome",
                                {"name": "Finding"},
                            ],
                        }
                    ],
                }
            },
        )
    )
    async with client:
        results = await client.search("pneumothorax")
    assert results.results[0].semantic_types == ["Disease or Syndrome", "Finding"]


@respx.mock
@pytest.mark.asyncio
async def test_definitions_accept_canonical_not_found_as_empty(client: UMLSClient):
    respx.get(f"{BASE}/content/current/CUI/C0032326/definitions").mock(
        return_value=httpx.Response(404, json={"error": "missing"})
    )
    async with client:
        assert await client.get_definitions("C0032326") == []


@respx.mock
@pytest.mark.asyncio
async def test_custom_endpoint_not_found_is_not_treated_as_empty():
    proxy = "https://proxy.example.test/v1/connectors/umls"
    client = UMLSClient(api_key="key", base_url=proxy)
    respx.get(f"{proxy}/content/current/CUI/C0032326/definitions").mock(
        return_value=httpx.Response(404, json={"error": "route missing"})
    )
    async with client:
        with pytest.raises(ProviderError) as caught:
            await client.get_definitions("C0032326")
    assert caught.value.failure.category == FailureCategory.HTTP_ERROR
    assert caught.value.failure.status_origin == StatusOrigin.UNKNOWN


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "member",
    [
        {"rootSource": "RADLEX", "name": "missing code"},
        {
            "rootSource": "RADLEX",
            "name": "invalid term type",
            "code": f"{BASE}/content/current/source/RADLEX/RID1",
            "termType": 123,
        },
        {
            "rootSource": "RADLEX",
            "name": "invalid obsolete flag",
            "code": f"{BASE}/content/current/source/RADLEX/RID1",
            "obsolete": 1,
        },
    ],
)
async def test_atoms_reject_malformed_members(client: UMLSClient, member: object):
    respx.get(f"{BASE}/content/current/CUI/C0032326/atoms").mock(
        return_value=httpx.Response(
            200,
            json={"result": [member]},
        )
    )
    async with client:
        with pytest.raises(ProviderError) as caught:
            await client.get_atoms("C0032326")
    assert caught.value.failure.category == FailureCategory.INVALID_RESPONSE


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [("obsolete", 1), ("concepts", ["not", "a", "url"])],
)
async def test_get_source_rejects_malformed_optional_fields(
    client: UMLSClient,
    field: str,
    value: object,
):
    result = {"ui": "RID1", "name": "Finding", field: value}
    respx.get(f"{BASE}/content/current/source/RADLEX/RID1").mock(
        return_value=httpx.Response(200, json={"result": result})
    )
    async with client:
        with pytest.raises(ProviderError) as caught:
            await client.get_source("RADLEX", "RID1")
    assert caught.value.failure.category == FailureCategory.INVALID_RESPONSE


@respx.mock
@pytest.mark.asyncio
async def test_hierarchy_rejects_malformed_success_shape(client: UMLSClient):
    respx.get(f"{BASE}/content/current/source/RADLEX/RID1/children").mock(
        return_value=httpx.Response(
            200,
            json={"result": [{"ui": 123, "name": "Malformed child"}]},
        )
    )
    async with client:
        with pytest.raises(ProviderError) as caught:
            await client.children("RADLEX", "RID1")
    assert caught.value.failure.category == FailureCategory.INVALID_RESPONSE
    assert caught.value.failure.operation.value == "children"
