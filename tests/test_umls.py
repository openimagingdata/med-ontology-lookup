"""Mocked UMLS client tests."""

import httpx
import pytest
import respx

from med_ontology_lookup.clients.umls import UMLSClient
from med_ontology_lookup.models import Backend

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
