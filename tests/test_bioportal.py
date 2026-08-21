"""Mocked BioPortal client tests."""

from urllib.parse import quote

import httpx
import pytest
import respx

from med_ontology_lookup.clients.bioportal import (
    BioPortalClient,
    _exact_first_preserve_order,
    _short_code,
)
from med_ontology_lookup.models import Backend, SearchHit

BASE = "https://data.bioontology.org"


@pytest.fixture
def client():
    return BioPortalClient(api_key="test-key", base_url=BASE)


@respx.mock
@pytest.mark.asyncio
async def test_search_parses_collection(client: BioPortalClient):
    respx.get(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": 1,
                "pageCount": 1,
                "totalCount": 1,
                "collection": [
                    {
                        "@id": "http://radlex.org/RID/RID43255",
                        "prefLabel": "ground-glass opacity",
                        "synonym": ["GGO"],
                        "definition": ["Hazy increased opacity..."],
                        "semanticType": ["T033"],
                        "cui": ["C3544344"],
                        "links": {
                            "ontology": f"{BASE}/ontologies/RADLEX",
                            "ui": "https://bioportal.bioontology.org/ontologies/RADLEX/?p=classes&conceptid=http%3A%2F%2Fradlex.org%2FRID%2FRID43255",
                        },
                    }
                ],
            },
        )
    )
    async with client:
        results = await client.search("ground glass opacity", ontologies=["RADLEX"])
    assert results.total_count == 1
    assert len(results.results) == 1
    hit = results.results[0]
    assert hit.code == "RID43255"
    assert hit.ontology == "RADLEX"
    assert hit.pref_label == "ground-glass opacity"
    assert "GGO" in hit.synonyms
    assert hit.cui == "C3544344"
    assert hit.backend == Backend.BIOPORTAL


@respx.mock
@pytest.mark.asyncio
async def test_get_class(client: BioPortalClient):
    class_id = "http://radlex.org/RID/RID43255"
    # quote encodes the class id in the path
    respx.get(url__regex=rf"{BASE}/ontologies/RADLEX/classes/.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "@id": class_id,
                "prefLabel": "ground-glass opacity",
                "synonym": ["GGO"],
                "definition": ["Hazy increased opacity of lung"],
                "semanticType": ["T033"],
                "cui": ["C3544344"],
                "obsolete": False,
                "links": {
                    "ontology": f"{BASE}/ontologies/RADLEX",
                    "ui": "https://bioportal.bioontology.org/...",
                },
            },
        )
    )
    async with client:
        concept = await client.get_class("RADLEX", class_id)
    assert concept.code == "RID43255"
    assert concept.pref_label == "ground-glass opacity"
    assert concept.obsolete is False


@respx.mock
@pytest.mark.asyncio
async def test_parents(client: BioPortalClient):
    respx.get(url__regex=rf"{BASE}/ontologies/RADLEX/classes/.*/parents").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "@id": "http://radlex.org/RID/RID5",
                    "prefLabel": "imaging observation",
                }
            ],
        )
    )
    async with client:
        nodes = await client.parents("RADLEX", "http://radlex.org/RID/RID43255")
    assert len(nodes) == 1
    assert nodes[0].pref_label == "imaging observation"


def test_missing_key_raises():
    c = BioPortalClient(api_key="")
    with pytest.raises(ValueError, match="API key"):
        c._require_key()


@respx.mock
@pytest.mark.asyncio
async def test_class_exists_raises_on_auth_and_rate_limit(client: BioPortalClient):
    iri = "http://www.radlex.org/RID/RID194"
    respx.get(f"{BASE}/ontologies/RADLEX/classes/{quote(iri, safe='')}").mock(
        return_value=httpx.Response(429, json={"errors": ["rate limited"]})
    )
    async with client:
        with pytest.raises(httpx.HTTPStatusError) as exc:
            await client._class_exists("RADLEX", iri)
    assert exc.value.response.status_code == 429


@respx.mock
@pytest.mark.asyncio
async def test_resolve_does_not_cache_misses(client: BioPortalClient):
    short = "RID99999"
    iri = "http://www.radlex.org/RID/RID99999"
    respx.get(f"{BASE}/ontologies/RADLEX/classes/{quote(short, safe='')}").mock(
        return_value=httpx.Response(400, json={"errors": ["not a valid IRI"]})
    )
    respx.get(f"{BASE}/ontologies/RADLEX/classes/{quote(iri, safe='')}").mock(
        return_value=httpx.Response(404, json={"errors": ["missing"]})
    )
    respx.get(f"{BASE}/search").mock(
        return_value=httpx.Response(200, json={"collection": [], "totalCount": 0})
    )
    async with client:
        first = await client.resolve_class_id("RADLEX", short)
        assert first == short
        assert ("RADLEX", short) not in client._resolve_cache


@respx.mock
@pytest.mark.asyncio
async def test_resolve_does_not_match_numeric_suffix(client: BioPortalClient):
    """7088 must not resolve to fma17088 via endswith."""
    short = "7088"
    respx.get(url__regex=rf"{BASE}/ontologies/FMA/classes/.*").mock(
        return_value=httpx.Response(404, json={"errors": ["missing"]})
    )
    respx.get(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "totalCount": 1,
                "collection": [
                    {
                        "@id": "http://purl.org/sig/ont/fma/fma17088",
                        "prefLabel": "unrelated",
                        "notation": ["FMA:17088"],
                        "links": {"ontology": f"{BASE}/ontologies/FMA", "ui": ""},
                    }
                ],
            },
        )
    )
    async with client:
        resolved = await client.resolve_class_id("FMA", short)
    assert resolved == short
    assert "17088" not in resolved


def test_short_code_prefers_fragment_over_path():
    assert _short_code("http://example.org/ontology.owl#Class") == "Class"
    assert _short_code("http://www.radlex.org/RID/RID194") == "RID194"
    assert _short_code("http://purl.org/sig/ont/fma/fma7088") == "fma7088"


def test_exact_first_preserves_source_order():
    def hit(label: str, exact: bool) -> SearchHit:
        return SearchHit(
            concept_id=label,
            code=label,
            ontology="SNOMEDCT",
            pref_label=label,
            backend=Backend.BIOPORTAL,
            exact_match=exact,
        )

    # Non-exact zebra before apple; exact banana before zebra
    ordered = _exact_first_preserve_order(
        [hit("zebra", False), hit("apple", False), hit("banana", True), hit("aardvark", True)]
    )
    assert [h.pref_label for h in ordered] == ["banana", "aardvark", "zebra", "apple"]


@respx.mock
@pytest.mark.asyncio
async def test_get_class_resolves_short_radlex_code(client: BioPortalClient):
    """Short RID must be expanded to full IRI before /classes/{cls}."""
    short = "RID194"
    iri = "http://www.radlex.org/RID/RID194"
    # existence probe for bare short code → 400/404
    respx.get(f"{BASE}/ontologies/RADLEX/classes/{quote(short, safe='')}").mock(
        return_value=httpx.Response(400, json={"errors": ["not a valid IRI"]})
    )
    # existence probe + final get for full IRI
    respx.get(f"{BASE}/ontologies/RADLEX/classes/{quote(iri, safe='')}").mock(
        return_value=httpx.Response(
            200,
            json={
                "@id": iri,
                "prefLabel": "right hepatic duct",
                "synonym": [],
                "definition": [],
                "semanticType": [],
                "cui": [],
                "obsolete": False,
                "links": {
                    "ontology": f"{BASE}/ontologies/RADLEX",
                    "ui": "https://bioportal.bioontology.org/...",
                },
            },
        )
    )
    async with client:
        concept = await client.get_class("RADLEX", short)
    assert concept.code == "RID194"
    assert concept.pref_label == "right hepatic duct"
    assert concept.concept_id == iri


@respx.mock
@pytest.mark.asyncio
async def test_parents_resolves_short_code(client: BioPortalClient):
    short = "RID194"
    iri = "http://www.radlex.org/RID/RID194"
    respx.get(f"{BASE}/ontologies/RADLEX/classes/{quote(short, safe='')}").mock(
        return_value=httpx.Response(400, json={"errors": ["not a valid IRI"]})
    )
    respx.get(f"{BASE}/ontologies/RADLEX/classes/{quote(iri, safe='')}").mock(
        return_value=httpx.Response(
            200,
            json={"@id": iri, "prefLabel": "right hepatic duct"},
        )
    )
    respx.get(f"{BASE}/ontologies/RADLEX/classes/{quote(iri, safe='')}/parents").mock(
        return_value=httpx.Response(
            200,
            json=[{"@id": "http://www.radlex.org/RID/RID169", "prefLabel": "hepatic duct"}],
        )
    )
    async with client:
        nodes = await client.parents("RADLEX", short)
    assert len(nodes) == 1
    assert nodes[0].pref_label == "hepatic duct"
