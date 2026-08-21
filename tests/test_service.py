"""Facade / lookup routing tests (mocked HTTP)."""

import httpx
import pytest
import respx

from med_ontology_lookup.models import Concept, SearchResults
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
    async with mol:
        result = await mol.lookup("pneumothorax")
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
