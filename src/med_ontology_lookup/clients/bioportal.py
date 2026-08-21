"""Async BioPortal (data.bioontology.org) client."""

from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import quote

import httpx

from med_ontology_lookup.config import DEFAULT_BIOPORTAL_ONTOLOGIES, Settings, get_settings
from med_ontology_lookup.http_util import format_http_error
from med_ontology_lookup.models import (
    Backend,
    Concept,
    HierarchyNode,
    SearchHit,
    SearchResults,
)


def _short_code(concept_id: str) -> str:
    """Short local name of a URI/IRI, or the id itself.

    Fragment identifiers take precedence over path segments so
    ``http://example.org/ontology.owl#Class`` → ``Class``.
    """
    if not concept_id:
        return ""
    cleaned = concept_id.rstrip("/")
    if "#" in cleaned:
        return cleaned.rsplit("#", 1)[-1]
    if "/" in cleaned:
        return cleaned.rsplit("/", 1)[-1]
    return cleaned


def _looks_like_iri(class_id: str) -> bool:
    s = class_id.strip()
    return "://" in s or s.startswith("urn:")


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _first_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def _links_dict(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("links")
    return raw if isinstance(raw, dict) else {}


def _ontology_from_links(links: dict[str, Any] | None) -> str:
    if not links:
        return ""
    url = links.get("ontology")
    if not url:
        return ""
    return str(url).rstrip("/").rsplit("/", 1)[-1]


def _exact_label_match(query: str, pref_label: str, synonyms: list[str]) -> bool:
    q = query.strip().casefold()
    if pref_label.strip().casefold() == q:
        return True
    return any(s.strip().casefold() == q for s in synonyms)


class BioPortalClient:
    """Async client for BioPortal search and class endpoints."""

    DEFAULT_ONTOLOGIES: ClassVar[tuple[str, ...]] = DEFAULT_BIOPORTAL_ONTOLOGIES
    # Search /include only allows: prefLabel, synonym, definition, notation, cui, semanticType, properties
    DEFAULT_INCLUDE: ClassVar[str] = "prefLabel,synonym,definition,semanticType,cui"
    # Class detail endpoint accepts a broader attribute set including obsolete.
    CLASS_INCLUDE: ClassVar[str] = "prefLabel,synonym,definition,semanticType,cui,obsolete"
    # Known BioPortal class IRI templates for short-code → full IRI resolution.
    # {code} is the short id as supplied (e.g. RID194, 76581006, 7088, 8867-4).
    IRI_TEMPLATES: ClassVar[dict[str, tuple[str, ...]]] = {
        "RADLEX": ("http://www.radlex.org/RID/{code}",),
        "SNOMEDCT": ("http://purl.bioontology.org/ontology/SNOMEDCT/{code}",),
        "FMA": (
            "http://purl.org/sig/ont/fma/fma{code}",
            "http://purl.org/sig/ont/fma/{code}",
        ),
        "LOINC": ("http://purl.bioontology.org/ontology/LNC/{code}",),
    }

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        settings: Settings | None = None,
        timeout: float | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.api_key = api_key if api_key is not None else self._settings.bioportal_key()
        self.base_url = (base_url or self._settings.bioportal_base_url).rstrip("/")
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout if timeout is not None else self._settings.http_timeout
        self._resolve_cache: dict[tuple[str, str], str] = {}

    async def __aenter__(self) -> BioPortalClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_key(self) -> str:
        if not self.api_key:
            raise ValueError(
                "BioPortal API key required. Set BIOPORTAL_API_KEY or pass api_key=..."
            )
        return self.api_key

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ValueError(
                "HTTP client not initialized. Use `async with BioPortalClient()` "
                "or pass client=..."
            )
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"apikey token={self._require_key()}"}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        client = self._require_client()
        url = f"{self.base_url}{path}"
        response = await client.get(url, params=params or {}, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def _hit_from_item(self, item: dict[str, Any], query: str = "") -> SearchHit:
        links = _links_dict(item)
        ontology = _ontology_from_links(links)
        concept_id = str(item.get("@id", ""))
        synonyms = _as_str_list(item.get("synonym"))
        pref_label = str(item.get("prefLabel") or "")
        cuis = _as_str_list(item.get("cui"))
        return SearchHit(
            concept_id=concept_id,
            code=_short_code(concept_id),
            ontology=ontology,
            pref_label=pref_label,
            synonyms=synonyms,
            definition=_first_str(item.get("definition")),
            semantic_types=_as_str_list(item.get("semanticType")),
            cui=cuis[0] if cuis else None,
            ui_link=str(links.get("ui") or "") or None,
            backend=Backend.BIOPORTAL,
            exact_match=_exact_label_match(query, pref_label, synonyms) if query else False,
            raw=item,
        )

    def _concept_from_item(self, item: dict[str, Any], ontology: str | None = None) -> Concept:
        links = _links_dict(item)
        ont = ontology or _ontology_from_links(links)
        concept_id = str(item.get("@id", ""))
        return Concept(
            concept_id=concept_id,
            code=_short_code(concept_id),
            ontology=ont,
            pref_label=str(item.get("prefLabel") or ""),
            synonyms=_as_str_list(item.get("synonym")),
            definition=_first_str(item.get("definition")),
            semantic_types=_as_str_list(item.get("semanticType")),
            cuis=_as_str_list(item.get("cui")),
            obsolete=item.get("obsolete") if isinstance(item.get("obsolete"), bool) else None,
            ui_link=str(links.get("ui") or "") or None,
            backend=Backend.BIOPORTAL,
            raw=item,
        )

    def _node_from_item(self, item: dict[str, Any], ontology: str) -> HierarchyNode:
        concept_id = str(item.get("@id", ""))
        return HierarchyNode(
            concept_id=concept_id,
            code=_short_code(concept_id),
            ontology=ontology,
            pref_label=str(item.get("prefLabel") or _short_code(concept_id)),
            backend=Backend.BIOPORTAL,
        )

    async def search(
        self,
        query: str,
        *,
        ontologies: list[str] | None = None,
        page: int = 1,
        page_size: int = 50,
        require_exact_match: bool = False,
        semantic_types: list[str] | None = None,
        also_search_properties: bool = False,
        include: str | None = None,
    ) -> SearchResults:
        """Search BioPortal classes."""
        params: dict[str, Any] = {
            "q": query,
            "page": page,
            "pagesize": min(page_size, 100),
            "include": include or self.DEFAULT_INCLUDE,
            "display_context": "false",
            "display_links": "true",
        }
        onts = ontologies if ontologies is not None else list(self.DEFAULT_ONTOLOGIES)
        if onts:
            params["ontologies"] = ",".join(onts)
        if require_exact_match:
            params["require_exact_match"] = "true"
        if semantic_types:
            params["semantic_types"] = ",".join(semantic_types)
        if also_search_properties:
            params["also_search_properties"] = "true"

        data = await self._get("/search", params)
        collection = data.get("collection") or []
        hits = [self._hit_from_item(item, query=query) for item in collection if isinstance(item, dict)]
        return SearchResults(
            query=query,
            total_count=data.get("totalCount"),
            results=hits,
            backend=Backend.BIOPORTAL,
        )

    async def search_all(
        self,
        query: str,
        *,
        max_results: int = 50,
        ontologies: list[str] | None = None,
        require_exact_match: bool = False,
        semantic_types: list[str] | None = None,
    ) -> list[SearchHit]:
        """Paginate search up to *max_results*."""
        all_hits: list[SearchHit] = []
        page = 1
        page_size = min(50, max_results)
        while len(all_hits) < max_results:
            batch = await self.search(
                query,
                ontologies=ontologies,
                page=page,
                page_size=page_size,
                require_exact_match=require_exact_match,
                semantic_types=semantic_types,
            )
            all_hits.extend(batch.results)
            if not batch.results:
                break
            total = batch.total_count
            if total is not None and len(all_hits) >= total:
                break
            if len(batch.results) < page_size:
                break
            page += 1
        return all_hits[:max_results]

    async def search_balanced(
        self,
        query: str,
        *,
        ontologies: list[str] | None = None,
        max_results: int = 50,
        require_exact_match: bool = False,
        semantic_types: list[str] | None = None,
        per_ontology: int | None = None,
    ) -> SearchResults:
        """Search each ontology separately (in parallel) and merge.

        BioPortal's multi-ontology search ranks by global score, so a large
        vocabulary (e.g. SNOMEDCT) can completely crowd out RADLEX/FMA/LOINC
        even when those have exact matches. Querying per-ontology fixes that.
        """
        import asyncio

        onts = list(ontologies) if ontologies is not None else list(self.DEFAULT_ONTOLOGIES)
        if not onts:
            hits = await self.search_all(
                query,
                max_results=max_results,
                ontologies=None,
                require_exact_match=require_exact_match,
                semantic_types=semantic_types,
            )
            return SearchResults(
                query=query, total_count=len(hits), results=hits, backend=Backend.BIOPORTAL
            )
        if len(onts) == 1:
            hits = await self.search_all(
                query,
                max_results=max_results,
                ontologies=onts,
                require_exact_match=require_exact_match,
                semantic_types=semantic_types,
            )
            return SearchResults(
                query=query, total_count=len(hits), results=hits, backend=Backend.BIOPORTAL
            )

        # Fetch enough from each ontology to fill a balanced page.
        n_each = per_ontology or max(5, (max_results + len(onts) - 1) // len(onts) + 2)
        results = await asyncio.gather(
            *[
                self.search_all(
                    query,
                    max_results=n_each,
                    ontologies=[ont],
                    require_exact_match=require_exact_match,
                    semantic_types=semantic_types,
                )
                for ont in onts
            ],
            return_exceptions=True,
        )

        by_ont: dict[str, list[SearchHit]] = {ont: [] for ont in onts}
        errors: list[BaseException] = []
        warnings: list[str] = []
        for ont, result in zip(onts, results, strict=True):
            if isinstance(result, BaseException):
                errors.append(result)
                warnings.append(f"{ont}: {format_http_error(result)}")
                continue
            by_ont[ont] = result  # type: ignore[assignment]

        if errors and not any(by_ont.values()):
            raise errors[0]

        # Round-robin across ontologies; exact matches first, preserving API order.
        for ont in onts:
            by_ont[ont] = _exact_first_preserve_order(by_ont[ont])

        indices = {ont: 0 for ont in onts}
        merged: list[SearchHit] = []
        seen_ids: set[str] = set()
        while len(merged) < max_results:
            progressed = False
            for ont in onts:
                i = indices[ont]
                group = by_ont[ont]
                if i >= len(group):
                    continue
                hit = group[i]
                indices[ont] = i + 1
                progressed = True
                if hit.concept_id in seen_ids:
                    continue
                seen_ids.add(hit.concept_id)
                merged.append(hit)
                if len(merged) >= max_results:
                    break
            if not progressed:
                break
        return SearchResults(
            query=query,
            total_count=len(merged),
            results=merged,
            backend=Backend.BIOPORTAL,
            warnings=warnings,
        )

    def _candidate_iris(self, ontology: str, class_id: str) -> list[str]:
        """Build candidate full IRIs for a short code."""
        code = class_id.strip()
        ont = ontology.upper()
        candidates: list[str] = []
        # LOINC (and some others) accept the short code as the class id.
        candidates.append(code)
        for template in self.IRI_TEMPLATES.get(ont, ()):
            # FMA templates use bare digits; strip a leading fma prefix if present
            fill = code
            if ont == "FMA" and fill.lower().startswith("fma"):
                fill = fill[3:].lstrip("_:")
            candidates.append(template.format(code=fill))
        # Deduplicate preserving order
        seen: set[str] = set()
        out: list[str] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    async def _class_exists(self, ontology: str, class_id: str) -> bool:
        client = self._require_client()
        encoded = quote(class_id, safe="")
        url = f"{self.base_url}/ontologies/{ontology}/classes/{encoded}"
        response = await client.get(
            url,
            params={
                "include": "prefLabel",
                "display_context": "false",
                "display_links": "false",
            },
            headers=self._headers(),
        )
        if response.status_code == 200:
            return True
        if response.status_code in {400, 404}:
            return False
        response.raise_for_status()
        return False

    async def resolve_class_id(self, ontology: str, class_id: str) -> str:
        """Resolve a short code or IRI to a BioPortal class id (usually a full IRI).

        BioPortal's ``/classes/{cls}`` endpoint requires a valid IRI for most
        ontologies (RadLex, SNOMED CT, FMA). Short codes like ``RID194`` must be
        expanded first.
        """
        raw = class_id.strip()
        if not raw:
            return raw
        if _looks_like_iri(raw):
            return raw

        ont = ontology.upper()
        cache_key = (ont, raw)
        cached = self._resolve_cache.get(cache_key)
        if cached is not None:
            return cached

        for candidate in self._candidate_iris(ont, raw):
            if await self._class_exists(ont, candidate):
                self._resolve_cache[cache_key] = candidate
                return candidate

        # Search fallback: exact short-code / notation / IRI-suffix match only
        results = await self.search(
            raw,
            ontologies=[ont],
            page_size=25,
            also_search_properties=True,
            include="prefLabel,synonym,definition,semanticType,cui,notation",
        )
        needle = raw.casefold()
        for hit in results.results:
            short = hit.code.casefold()
            iri = hit.concept_id.rstrip("/")
            if short == needle or iri.casefold().endswith("/" + needle) or iri.casefold().endswith("#" + needle):
                self._resolve_cache[cache_key] = hit.concept_id
                return hit.concept_id
            raw_item = hit.raw or {}
            notation = raw_item.get("notation")
            notations = notation if isinstance(notation, list) else ([notation] if notation else [])
            for n in notations:
                nstr = str(n).casefold()
                if nstr == needle or nstr.endswith(":" + needle):
                    self._resolve_cache[cache_key] = hit.concept_id
                    return hit.concept_id

        # Do not cache misses — a later retry may succeed
        return raw

    async def get_class(self, ontology: str, class_id: str) -> Concept:
        """Fetch a class by ontology acronym and class id or full IRI."""
        resolved = await self.resolve_class_id(ontology, class_id)
        encoded = quote(resolved, safe="")
        data = await self._get(
            f"/ontologies/{ontology}/classes/{encoded}",
            {
                "include": self.CLASS_INCLUDE,
                "display_context": "false",
                "display_links": "true",
            },
        )
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected response for {ontology}/{class_id}")
        return self._concept_from_item(data, ontology=ontology)

    async def parents(self, ontology: str, class_id: str) -> list[HierarchyNode]:
        resolved = await self.resolve_class_id(ontology, class_id)
        encoded = quote(resolved, safe="")
        data = await self._get(
            f"/ontologies/{ontology}/classes/{encoded}/parents",
            {
                "include": "prefLabel",
                "display_context": "false",
                "display_links": "false",
            },
        )
        items = data if isinstance(data, list) else data.get("collection") or []
        return [
            self._node_from_item(item, ontology)
            for item in items
            if isinstance(item, dict)
        ]

    async def children(self, ontology: str, class_id: str) -> list[HierarchyNode]:
        resolved = await self.resolve_class_id(ontology, class_id)
        encoded = quote(resolved, safe="")
        data = await self._get(
            f"/ontologies/{ontology}/classes/{encoded}/children",
            {
                "include": "prefLabel",
                "display_context": "false",
                "display_links": "false",
                "pagesize": 100,
            },
        )
        items = data if isinstance(data, list) else data.get("collection") or []
        return [
            self._node_from_item(item, ontology)
            for item in items
            if isinstance(item, dict)
        ]


def _exact_first_preserve_order(hits: list[SearchHit]) -> list[SearchHit]:
    """Partition exact matches first without reordering within each partition."""
    exact = [h for h in hits if h.exact_match]
    rest = [h for h in hits if not h.exact_match]
    return exact + rest
