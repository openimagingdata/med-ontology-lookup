"""Shared result models for ontology lookups."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from med_ontology_lookup.http_util import sanitize_endpoint


class Backend(str, Enum):
    """API backend used for a result."""

    BIOPORTAL = "bioportal"
    UMLS = "umls"


class ProviderOperation(str, Enum):
    """Remote provider operation that produced a failure."""

    SEARCH = "search"
    RESOLVE_CLASS = "resolve_class"
    GET_CONCEPT = "get_concept"
    GET_DEFINITIONS = "get_definitions"
    GET_ATOMS = "get_atoms"
    GET_SOURCE = "get_source"
    PARENTS = "parents"
    CHILDREN = "children"


class FailureCategory(str, Enum):
    """Stable category for a provider failure."""

    NOT_FOUND = "not_found"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    LICENSING = "licensing"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    UNAVAILABLE = "unavailable"
    INVALID_JSON = "invalid_json"
    INVALID_RESPONSE = "invalid_response"
    TRANSPORT = "transport"
    HTTP_ERROR = "http_error"


class StatusOrigin(str, Enum):
    """Known origin of an HTTP status, when it can be established."""

    PROVIDER = "provider"
    PROXY = "proxy"
    UNKNOWN = "unknown"


class ProviderFailure(BaseModel):
    """Credential-safe facts about one failed provider operation."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    provider: Backend
    operation: ProviderOperation
    category: FailureCategory
    endpoint: str
    http_status: int | None = None
    status_origin: StatusOrigin = StatusOrigin.UNKNOWN
    ontology: str | None = None

    @field_validator("endpoint")
    @classmethod
    def _sanitize_endpoint(cls, value: str) -> str:
        return sanitize_endpoint(value)

    def summary(self) -> str:
        """Return a concise message derived only from safe fields."""
        label = f"{self.provider.value} {self.operation.value}: {self.category.value}"
        if self.http_status is not None:
            label += f" (HTTP {self.http_status})"
        if self.ontology:
            label += f" [{self.ontology}]"
        if self.endpoint:
            label += f" at {self.endpoint}"
        return label


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
    failures: list[ProviderFailure] = Field(
        default_factory=list,
        description="Typed provider failures when another attempted search succeeded",
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
