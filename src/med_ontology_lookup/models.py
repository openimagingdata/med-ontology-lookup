"""Shared result models for ontology lookups."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Backend(str, Enum):
    """API backend used for a result."""

    BIOPORTAL = "bioportal"
    UMLS = "umls"


class SearchHit(BaseModel):
    """A single search hit from BioPortal or UMLS."""

    concept_id: str = Field(description="Full URI (BioPortal) or CUI/code (UMLS)")
    code: str = Field(description="Short code or CUI (last path segment when URI)")
    ontology: str = Field(description="Ontology acronym, e.g. RADLEX, SNOMEDCT, UMLS")
    pref_label: str = Field(description="Preferred label")
    synonyms: list[str] = Field(default_factory=list)
    definition: str | None = None
    semantic_types: list[str] = Field(default_factory=list)
    cui: str | None = Field(default=None, description="UMLS CUI when known")
    ui_link: str | None = None
    backend: Backend
    exact_match: bool = Field(
        default=False,
        description="True when the preferred label or a synonym equals the query (case-insensitive)",
    )
    raw: dict[str, Any] | None = Field(default=None, exclude=True)


class SearchResults(BaseModel):
    """Paginated or capped search results."""

    query: str
    total_count: int | None = None
    results: list[SearchHit]
    backend: Backend | None = None
    warnings: list[str] = Field(
        default_factory=list,
        description="Partial-failure notes (one backend or ontology failed; others succeeded)",
    )


class Concept(BaseModel):
    """Detailed concept record."""

    concept_id: str
    code: str
    ontology: str
    pref_label: str
    synonyms: list[str] = Field(default_factory=list)
    definition: str | None = None
    semantic_types: list[str] = Field(default_factory=list)
    cuis: list[str] = Field(default_factory=list)
    obsolete: bool | None = None
    ui_link: str | None = None
    backend: Backend
    raw: dict[str, Any] | None = Field(default=None, exclude=True)


class HierarchyNode(BaseModel):
    """A parent or child concept (one hop)."""

    concept_id: str
    code: str
    ontology: str
    pref_label: str
    backend: Backend


class SourceCode(BaseModel):
    """A source-asserted code linked to a UMLS CUI."""

    code: str
    source: str = Field(description="UMLS root source abbreviation, e.g. SNOMEDCT_US")
    name: str
    term_type: str | None = None
    cui: str | None = None
    obsolete: bool | None = None


class CrosswalkResult(BaseModel):
    """Codes in other vocabularies for a concept or CUI."""

    query: str
    cui: str | None = None
    preferred_name: str | None = None
    semantic_types: list[str] = Field(default_factory=list)
    source_codes: list[SourceCode] = Field(default_factory=list)
