"""Facade / lookup routing tests (mocked HTTP)."""

import httpx
import pytest
import respx

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
    assert result.results[0].pref_label == "Pneumothorax"  # type: ignore[union-attr]


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
    assert result.pref_label == "Pneumothorax"  # type: ignore[union-attr]
    assert result.code == "C0032326"  # type: ignore[union-attr]


def test_no_keys_raises():
    empty = OntologyLookup(bioportal_api_key="", umls_api_key="")
    # force empty keys
    empty._bioportal.api_key = None
    empty._umls.api_key = None
    with pytest.raises(ValueError, match="No API keys"):
        empty._resolve_backends("auto")


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
