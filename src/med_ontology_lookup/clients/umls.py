"""Async UMLS Terminology Services (UTS) REST client."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

import httpx

from med_ontology_lookup.config import (
    DEFAULT_UMLS_SABS,
    ONTOLOGY_TO_UMLS_SAB,
    Settings,
    get_settings,
)
from med_ontology_lookup.models import (
    Backend,
    Concept,
    CrosswalkResult,
    HierarchyNode,
    SearchHit,
    SearchResults,
    SourceCode,
)


def _code_from_atom_url(url: str | None) -> str:
    """Extract code from .../source/SAB/CODE or similar."""
    if not url or url == "NONE":
        return ""
    # URLs may percent-encode the code
    path = unquote(str(url).rstrip("/"))
    return path.rsplit("/", 1)[-1]


def _exact_label_match(query: str, name: str) -> bool:
    return query.strip().casefold() == name.strip().casefold()


class UMLSClient:
    """Async client for UMLS search, CUI detail, atoms, and hierarchy."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        version: str | None = None,
        client: httpx.AsyncClient | None = None,
        settings: Settings | None = None,
        timeout: float | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.api_key = api_key if api_key is not None else self._settings.umls_key()
        self.base_url = (base_url or self._settings.umls_base_url).rstrip("/")
        self.version = version or self._settings.umls_version
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout if timeout is not None else self._settings.http_timeout

    async def __aenter__(self) -> UMLSClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_key(self) -> str:
        if not self.api_key:
            raise ValueError("UMLS API key required. Set UMLS_API_KEY or pass api_key=...")
        return self.api_key

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ValueError(
                "HTTP client not initialized. Use `async with UMLSClient()` or pass client=..."
            )
        return self._client

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        client = self._require_client()
        merged = dict(params or {})
        merged["apiKey"] = self._require_key()
        url = f"{self.base_url}{path}"
        response = await client.get(url, params=merged)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def normalize_sab(source: str) -> str:
        """Map friendly ontology names to UMLS root source abbreviations."""
        key = source.strip().upper()
        return ONTOLOGY_TO_UMLS_SAB.get(key, key)

    async def search(
        self,
        query: str,
        *,
        sabs: list[str] | None = None,
        search_type: str = "words",
        return_id_type: str = "concept",
        page_size: int = 25,
        semantic_types: list[str] | None = None,
        input_type: str = "atom",
        partial_search: bool = False,
    ) -> SearchResults:
        """Search UMLS; default returns CUIs."""
        params: dict[str, Any] = {
            "string": query,
            "searchType": search_type,
            "returnIdType": return_id_type,
            "pageSize": min(page_size, 200),
            "inputType": input_type,
        }
        if sabs:
            params["sabs"] = ",".join(self.normalize_sab(s) for s in sabs)
        if semantic_types:
            params["semanticTypes"] = "|".join(semantic_types)
        if partial_search:
            params["partialSearch"] = "true"

        data = await self._get(f"/search/{self.version}", params)
        result_block = data.get("result") or {}
        raw_results = result_block.get("results") or []
        hits: list[SearchHit] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            # UMLS returns a sentinel when no results
            ui = str(item.get("ui") or "")
            if ui in {"", "NONE"}:
                continue
            name = str(item.get("name") or "")
            root = str(item.get("rootSource") or "UMLS")
            stypes = item.get("semanticTypes") or []
            if stypes and isinstance(stypes[0], dict):
                stype_names = [str(s.get("name") or "") for s in stypes]
            else:
                stype_names = [str(s) for s in stypes]

            is_cui = ui.upper().startswith("C") and return_id_type == "concept"
            hits.append(
                SearchHit(
                    concept_id=ui,
                    code=ui,
                    ontology="UMLS" if is_cui else root,
                    pref_label=name,
                    synonyms=[],
                    definition=None,
                    semantic_types=stype_names,
                    cui=ui if is_cui else None,
                    ui_link=str(item.get("uri") or "") or None,
                    backend=Backend.UMLS,
                    exact_match=_exact_label_match(query, name),
                    raw=item,
                )
            )
        return SearchResults(
            query=query,
            total_count=result_block.get("recCount"),
            results=hits,
            backend=Backend.UMLS,
        )

    async def get_cui(self, cui: str) -> Concept:
        """Fetch concept metadata for a CUI."""
        data = await self._get(f"/content/{self.version}/CUI/{cui.upper()}")
        result = data.get("result") or data
        stypes = result.get("semanticTypes") or []
        stype_names = [
            str(s.get("name") if isinstance(s, dict) else s) for s in stypes
        ]
        name = str(result.get("name") or "")
        ui = str(result.get("ui") or cui.upper())
        return Concept(
            concept_id=ui,
            code=ui,
            ontology="UMLS",
            pref_label=name,
            synonyms=[],
            definition=None,
            semantic_types=stype_names,
            cuis=[ui],
            obsolete=None,
            ui_link=f"https://uts.nlm.nih.gov/uts/umls/concept/{ui}",
            backend=Backend.UMLS,
            raw=result if isinstance(result, dict) else None,
        )

    async def get_definitions(self, cui: str) -> list[str]:
        """Return definition strings for a CUI (may be empty)."""
        try:
            data = await self._get(f"/content/{self.version}/CUI/{cui.upper()}/definitions")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            raise
        results = data.get("result") or []
        if results == "NONE" or not results:
            return []
        defs: list[str] = []
        for item in results:
            if isinstance(item, dict) and item.get("value"):
                defs.append(str(item["value"]))
        return defs

    async def get_atoms(
        self,
        cui: str,
        *,
        sabs: list[str] | None = None,
        language: str = "ENG",
        preferred_only: bool = False,
    ) -> list[SourceCode]:
        """Atoms (source strings/codes) for a CUI — the crosswalk building block."""
        params: dict[str, Any] = {"language": language, "pageSize": 200}
        if sabs:
            params["sabs"] = ",".join(self.normalize_sab(s) for s in sabs)
        if preferred_only:
            params["ttys"] = "PT"

        path = f"/content/{self.version}/CUI/{cui.upper()}/atoms"
        data = await self._get(path, params)
        results = data.get("result") or []
        if results == "NONE" or not results:
            return []

        codes: list[SourceCode] = []
        seen: set[tuple[str, str]] = set()
        for item in results:
            if not isinstance(item, dict):
                continue
            source = str(item.get("rootSource") or "")
            code = _code_from_atom_url(item.get("code"))
            if not code:
                code = _code_from_atom_url(item.get("sourceConcept"))
            if not code or not source:
                continue
            key = (source, code)
            if key in seen:
                continue
            seen.add(key)
            obsolete = item.get("obsolete")
            if isinstance(obsolete, str):
                obsolete = obsolete.lower() == "true"
            codes.append(
                SourceCode(
                    code=code,
                    source=source,
                    name=str(item.get("name") or ""),
                    term_type=str(item.get("termType") or "") or None,
                    cui=cui.upper(),
                    obsolete=obsolete if isinstance(obsolete, bool) else None,
                )
            )
        return codes

    async def crosswalk(
        self,
        query: str,
        *,
        from_source: str | None = None,
        to_sources: list[str] | None = None,
        search_type: str = "exact",
    ) -> CrosswalkResult:
        """Resolve *query* to a CUI (if needed) and list source codes.

        *query* may be a CUI or a source code (when *from_source* is set) or a term.
        """
        cui: str | None = None
        preferred_name: str | None = None
        semantic_types: list[str] = []

        q = query.strip()
        if q.upper().startswith("C") and q[1:].isdigit() and len(q) >= 8:
            cui = q.upper()
            concept = await self.get_cui(cui)
            preferred_name = concept.pref_label
            semantic_types = concept.semantic_types
        elif from_source:
            # Map source code → CUI
            sab = self.normalize_sab(from_source)
            search = await self.search(
                q,
                sabs=[sab],
                search_type="exact",
                return_id_type="concept",
                input_type="sourceUi",
                page_size=5,
            )
            if search.results:
                cui = search.results[0].cui or search.results[0].code
                preferred_name = search.results[0].pref_label
                semantic_types = search.results[0].semantic_types
        else:
            search = await self.search(
                q,
                sabs=to_sources,
                search_type=search_type,
                return_id_type="concept",
                page_size=5,
            )
            if search.results:
                top = search.results[0]
                cui = top.cui or top.code
                preferred_name = top.pref_label
                semantic_types = top.semantic_types

        if not cui:
            return CrosswalkResult(query=query, cui=None, preferred_name=None, source_codes=[])

        sabs = to_sources or list(DEFAULT_UMLS_SABS)
        atoms = await self.get_atoms(cui, sabs=sabs)
        # Do not fall back to unfiltered atoms when the caller named target sources —
        # an empty list means "no codes in those SABs", not "show every vocabulary".

        if preferred_name is None:
            try:
                concept = await self.get_cui(cui)
                preferred_name = concept.pref_label
                semantic_types = concept.semantic_types
            except httpx.HTTPError:
                pass

        return CrosswalkResult(
            query=query,
            cui=cui,
            preferred_name=preferred_name,
            semantic_types=semantic_types,
            source_codes=atoms,
        )

    async def get_source(self, source: str, code: str) -> Concept:
        """Fetch a source-asserted identifier."""
        sab = self.normalize_sab(source)
        data = await self._get(f"/content/{self.version}/source/{sab}/{code}")
        result = data.get("result") or data
        name = str(result.get("name") or "")
        ui = str(result.get("ui") or code)
        obsolete = result.get("obsolete")
        if isinstance(obsolete, str):
            obsolete = obsolete.lower() == "true"
        return Concept(
            concept_id=ui,
            code=ui,
            ontology=sab,
            pref_label=name,
            synonyms=[],
            definition=None,
            semantic_types=[],
            cuis=[],
            obsolete=obsolete if isinstance(obsolete, bool) else None,
            ui_link=str(result.get("concepts") or "") or None,
            backend=Backend.UMLS,
            raw=result if isinstance(result, dict) else None,
        )

    async def parents(self, source: str, code: str) -> list[HierarchyNode]:
        sab = self.normalize_sab(source)
        data = await self._get(f"/content/{self.version}/source/{sab}/{code}/parents")
        results = data.get("result") or []
        if results == "NONE" or not results:
            return []
        nodes: list[HierarchyNode] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            ui = str(item.get("ui") or "")
            nodes.append(
                HierarchyNode(
                    concept_id=ui,
                    code=ui,
                    ontology=str(item.get("rootSource") or sab),
                    pref_label=str(item.get("name") or ui),
                    backend=Backend.UMLS,
                )
            )
        return nodes

    async def children(self, source: str, code: str) -> list[HierarchyNode]:
        sab = self.normalize_sab(source)
        data = await self._get(f"/content/{self.version}/source/{sab}/{code}/children")
        results = data.get("result") or []
        if results == "NONE" or not results:
            return []
        nodes: list[HierarchyNode] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            ui = str(item.get("ui") or "")
            nodes.append(
                HierarchyNode(
                    concept_id=ui,
                    code=ui,
                    ontology=str(item.get("rootSource") or sab),
                    pref_label=str(item.get("name") or ui),
                    backend=Backend.UMLS,
                )
            )
        return nodes
