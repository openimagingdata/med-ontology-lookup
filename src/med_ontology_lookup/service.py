"""Unified ontology lookup facade."""

from __future__ import annotations

import asyncio
from typing import Literal

import httpx

from med_ontology_lookup.clients.bioportal import BioPortalClient
from med_ontology_lookup.clients.umls import UMLSClient
from med_ontology_lookup.config import (
    DEFAULT_BIOPORTAL_ONTOLOGIES,
    UMLS_SAB_TO_BIOPORTAL,
    Settings,
    get_settings,
)
from med_ontology_lookup.detect import InputKind, detect_input
from med_ontology_lookup.models import (
    Backend,
    Concept,
    CrosswalkResult,
    HierarchyNode,
    SearchHit,
    SearchResults,
)
from med_ontology_lookup.semantic_types import hit_matches_types, resolve_semantic_types

BackendChoice = Literal["bioportal", "umls", "both", "auto"]


class OntologyLookup:
    """High-level API combining BioPortal and UMLS.

    Prefer using as an async context manager so HTTP clients are closed cleanly::

        async with OntologyLookup() as mol:
            hits = await mol.search("pneumothorax")
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        bioportal_api_key: str | None = None,
        umls_api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._http = http_client
        self._owns_http = http_client is None
        self._bioportal = BioPortalClient(
            api_key=bioportal_api_key,
            client=http_client,
            settings=self.settings,
        )
        self._umls = UMLSClient(
            api_key=umls_api_key,
            client=http_client,
            settings=self.settings,
        )
        # If we share an external client, clients must not close it
        if http_client is not None:
            self._bioportal._owns_client = False
            self._umls._owns_client = False

    async def __aenter__(self) -> OntologyLookup:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.settings.http_timeout)
            self._bioportal._client = self._http
            self._bioportal._owns_client = False
            self._umls._client = self._http
            self._umls._owns_client = False
        else:
            self._bioportal._client = self._http
            self._umls._client = self._http
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None
            self._bioportal._client = None
            self._umls._client = None

    @property
    def bioportal(self) -> BioPortalClient:
        return self._bioportal

    @property
    def umls(self) -> UMLSClient:
        return self._umls

    def _has_bioportal(self) -> bool:
        return bool(self._bioportal.api_key)

    def _has_umls(self) -> bool:
        return bool(self._umls.api_key)

    def _resolve_backends(self, choice: BackendChoice) -> list[Backend]:
        if choice == "bioportal":
            return [Backend.BIOPORTAL]
        if choice == "umls":
            return [Backend.UMLS]
        # "both" and "auto": use every configured backend.
        # auto used to prefer BioPortal alone, which hid UMLS CUIs whenever
        # BIOPORTAL_API_KEY was set — not what callers expect from a dual-API tool.
        if choice in ("both", "auto"):
            backends: list[Backend] = []
            if self._has_bioportal():
                backends.append(Backend.BIOPORTAL)
            if self._has_umls():
                backends.append(Backend.UMLS)
            if not backends:
                raise ValueError(
                    "No API keys configured. Set BIOPORTAL_API_KEY and/or UMLS_API_KEY."
                )
            return backends
        raise ValueError(f"Unknown backend choice: {choice!r}")

    async def search(
        self,
        query: str,
        *,
        ontologies: list[str] | None = None,
        backend: BackendChoice = "auto",
        limit: int = 25,
        exact: bool = False,
        semantic_types: list[str] | None = None,
        types_strict: bool = False,
    ) -> SearchResults:
        """Search for *query* across configured backends.

        BioPortal is queried **per ontology** (in parallel) so large vocabularies
        like SNOMED do not crowd out RADLEX/FMA/LOINC. Results are interleaved by
        ontology (including UMLS) so each source stays visible.

        Type filters (``semantic_types``):
          - ``types_strict=False`` (CLI ``-t`` / ``--types``): keep hits matching the
            types **or** with no type annotation (common for RadLex).
          - ``types_strict=True`` (CLI ``-T`` / ``--types-strict``): keep only hits
            that have a matching type; untyped hits are dropped.
        """
        backends = self._resolve_backends(backend)
        onts = [o.upper() for o in (ontologies or list(DEFAULT_BIOPORTAL_ONTOLOGIES))]
        stypes = resolve_semantic_types(semantic_types)

        # When allowing untyped hits, do not push the type filter to backends —
        # BioPortal/UMLS would drop untyped classes before we can keep them.
        # Over-fetch so client-side filtering still fills *limit*.
        api_stypes = stypes if (stypes and types_strict) else None
        fetch_limit = limit * 3 if stypes else limit

        tasks = []
        if Backend.BIOPORTAL in backends and self._has_bioportal():
            tasks.append(
                (
                    Backend.BIOPORTAL,
                    self._bioportal.search_balanced(
                        query,
                        max_results=fetch_limit,
                        ontologies=onts,
                        require_exact_match=exact,
                        semantic_types=api_stypes,
                    ),
                )
            )
        if Backend.UMLS in backends and self._has_umls():
            search_type = "exact" if exact else "words"
            # When the user names ontologies, map them to UMLS SABs.
            # When using defaults, leave sabs unrestricted so general UMLS CUIs appear
            # alongside BioPortal source hits.
            umls_sabs = (
                [self._umls.normalize_sab(o) for o in ontologies]
                if ontologies
                else None
            )
            tasks.append(
                (
                    Backend.UMLS,
                    self._umls.search(
                        query,
                        sabs=umls_sabs,
                        search_type=search_type,
                        page_size=min(fetch_limit, 200),
                        semantic_types=api_stypes,
                    ),
                )
            )

        if not tasks:
            raise ValueError("No usable backend for search with current API keys.")

        results_lists = await asyncio.gather(
            *[t[1] for t in tasks], return_exceptions=True
        )
        merged: list[SearchHit] = []
        primary_backend: Backend | None = None
        errors: list[tuple[Backend, BaseException]] = []
        for (b, _), result in zip(tasks, results_lists, strict=True):
            if isinstance(result, BaseException):
                errors.append((b, result))
                continue
            primary_backend = primary_backend or b
            if isinstance(result, SearchResults):
                merged.extend(result.results)
            else:
                # search_all / search_balanced returns list[SearchHit]
                merged.extend(result)  # type: ignore[arg-type]

        if not merged and errors:
            # Surface failures instead of returning a silent empty table.
            if len(errors) == 1:
                raise errors[0][1]
            parts = [f"{b.value}: {type(e).__name__}: {e}" for b, e in errors]
            raise RuntimeError("All search backends failed: " + "; ".join(parts))

        # Deduplicate by (backend, concept_id)
        seen: set[tuple[str, str]] = set()
        unique: list[SearchHit] = []
        for hit in merged:
            key = (hit.backend.value, hit.concept_id)
            if key in seen:
                continue
            seen.add(key)
            unique.append(hit)

        if stypes:
            unique = [
                h
                for h in unique
                if hit_matches_types(h.semantic_types, stypes, strict=types_strict)
            ]

        # Interleave by ontology so RADLEX/FMA/LOINC/SNOMED/UMLS all appear.
        preferred_order = list(onts) + ["UMLS"]
        ordered = self._interleave_by_ontology(
            unique, limit=limit, preferred_order=preferred_order
        )

        return SearchResults(
            query=query,
            total_count=len(unique),
            results=ordered,
            backend=primary_backend if len(backends) == 1 else None,
        )

    @staticmethod
    def _interleave_by_ontology(
        hits: list[SearchHit],
        *,
        limit: int,
        preferred_order: list[str] | None = None,
    ) -> list[SearchHit]:
        """Round-robin hits across ontologies; exact matches first within each.

        Within each partition (exact / non-exact), original source order is kept
        so backend relevance ranking is not replaced by alphabetical labels.
        """
        by_ont: dict[str, list[SearchHit]] = {}
        for hit in hits:
            by_ont.setdefault(hit.ontology or "?", []).append(hit)
        for ont_key, group in list(by_ont.items()):
            exact = [h for h in group if h.exact_match]
            rest = [h for h in group if not h.exact_match]
            by_ont[ont_key] = exact + rest

        preferred = [o for o in (preferred_order or []) if o in by_ont]
        # Preserve first-seen ontology order for the rest (not alphabetical)
        remaining = [o for o in by_ont if o not in preferred]
        order = preferred + remaining

        indices = {o: 0 for o in order}
        out: list[SearchHit] = []
        while len(out) < limit:
            progressed = False
            for o in order:
                i = indices[o]
                group = by_ont[o]
                if i < len(group):
                    out.append(group[i])
                    indices[o] = i + 1
                    progressed = True
                    if len(out) >= limit:
                        break
            if not progressed:
                break
        return out

    async def get(
        self,
        identifier: str,
        *,
        ontology: str | None = None,
        backend: BackendChoice = "auto",
    ) -> Concept:
        """Fetch a concept by CUI, source code, or BioPortal class id."""
        detected = detect_input(identifier)
        ont = ontology or detected.ontology_hint

        if detected.kind == InputKind.CUI:
            if not self._has_umls():
                raise ValueError("UMLS_API_KEY required to resolve CUIs.")
            concept = await self._umls.get_cui(detected.value)
            defs = await self._umls.get_definitions(detected.value)
            if defs:
                concept = concept.model_copy(update={"definition": defs[0]})
            return concept

        # Prefer BioPortal when ontology is a BioPortal acronym
        use_bp = self._has_bioportal() and backend in ("auto", "bioportal", "both")
        use_umls = self._has_umls() and backend in ("auto", "umls", "both")

        if use_bp and ont and ont.upper() not in {"UMLS"}:
            try:
                return await self._bioportal.get_class(ont.upper(), detected.value)
            except httpx.HTTPStatusError:
                if not use_umls:
                    raise

        if use_umls:
            if not ont:
                raise ValueError(
                    "Ontology/source required for non-CUI get via UMLS "
                    "(e.g. ontology='SNOMEDCT' or 'SNOMEDCT_US')."
                )
            return await self._umls.get_source(ont, detected.value)

        raise ValueError(
            f"Cannot get {identifier!r}: need BIOPORTAL_API_KEY and/or UMLS_API_KEY "
            "and an ontology when not a CUI."
        )

    async def crosswalk(
        self,
        query: str,
        *,
        from_source: str | None = None,
        to_sources: list[str] | None = None,
    ) -> CrosswalkResult:
        """Map a term, code, or CUI to codes in target vocabularies (UMLS)."""
        if not self._has_umls():
            raise ValueError("UMLS_API_KEY required for crosswalk.")
        detected = detect_input(query)
        source = from_source or (
            detected.ontology_hint if detected.kind == InputKind.CODE else None
        )
        return await self._umls.crosswalk(
            detected.value,
            from_source=source,
            to_sources=to_sources,
        )

    async def parents(
        self,
        identifier: str,
        *,
        ontology: str,
        backend: BackendChoice = "auto",
    ) -> list[HierarchyNode]:
        return await self._hierarchy("parents", identifier, ontology=ontology, backend=backend)

    async def children(
        self,
        identifier: str,
        *,
        ontology: str,
        backend: BackendChoice = "auto",
    ) -> list[HierarchyNode]:
        return await self._hierarchy("children", identifier, ontology=ontology, backend=backend)

    async def _hierarchy(
        self,
        direction: Literal["parents", "children"],
        identifier: str,
        *,
        ontology: str,
        backend: BackendChoice,
    ) -> list[HierarchyNode]:
        detected = detect_input(identifier)
        code = detected.value
        ont = ontology.upper()

        prefer_bp = backend in ("auto", "bioportal", "both") and self._has_bioportal()
        prefer_umls = backend in ("auto", "umls", "both") and self._has_umls()

        bp_ont = UMLS_SAB_TO_BIOPORTAL.get(ont, ont)

        if prefer_bp and bp_ont not in {"UMLS"}:
            try:
                if direction == "parents":
                    return await self._bioportal.parents(bp_ont, code)
                return await self._bioportal.children(bp_ont, code)
            except httpx.HTTPStatusError:
                if not prefer_umls:
                    raise

        if prefer_umls:
            if direction == "parents":
                return await self._umls.parents(ont, code)
            return await self._umls.children(ont, code)

        raise ValueError("No usable backend for hierarchy lookup.")

    async def lookup(
        self,
        query: str,
        *,
        ontologies: list[str] | None = None,
        limit: int = 15,
        exact: bool = False,
    ) -> SearchResults | Concept | CrosswalkResult:
        """Smart entry point: auto-detect input kind and run the best operation.

        - CUI → get concept (+ definition when available)
        - Code with ontology hint → get that concept
        - Free text → search
        """
        detected = detect_input(query)
        if detected.kind == InputKind.CUI:
            return await self.get(detected.value)
        if detected.kind == InputKind.CODE and detected.ontology_hint:
            try:
                return await self.get(detected.value, ontology=detected.ontology_hint)
            except (httpx.HTTPError, ValueError):
                # Fall back to search if direct get fails
                return await self.search(
                    detected.value,
                    ontologies=ontologies or [detected.ontology_hint],
                    limit=limit,
                    exact=True,
                )
        return await self.search(
            detected.value,
            ontologies=ontologies,
            limit=limit,
            exact=exact,
        )
