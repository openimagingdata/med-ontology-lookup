"""Configuration and API keys."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# BioPortal ontology acronyms used by default for radiology/anatomy work.
DEFAULT_BIOPORTAL_ONTOLOGIES: tuple[str, ...] = ("RADLEX", "SNOMEDCT", "FMA", "LOINC")

# UMLS source abbreviations commonly used for crosswalk targets.
DEFAULT_UMLS_SABS: tuple[str, ...] = ("SNOMEDCT_US", "FMA", "RADLEX", "LNC")

# Map friendly / BioPortal names → UMLS SAB where they differ.
ONTOLOGY_TO_UMLS_SAB: dict[str, str] = {
    "SNOMEDCT": "SNOMEDCT_US",
    "SNOMED": "SNOMEDCT_US",
    "SNOMEDCT_US": "SNOMEDCT_US",
    "RADLEX": "RADLEX",
    "FMA": "FMA",
    "LOINC": "LNC",
    "LNC": "LNC",
    "ICD10CM": "ICD10CM",
    "CPT": "CPT",
}

# Map UMLS SAB → BioPortal ontology acronym where they differ.
UMLS_SAB_TO_BIOPORTAL: dict[str, str] = {
    "SNOMEDCT_US": "SNOMEDCT",
    "LNC": "LOINC",
    "RADLEX": "RADLEX",
    "FMA": "FMA",
    "ICD10CM": "ICD10CM",
    "CPT": "CPT",
}


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bioportal_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("BIOPORTAL_API_KEY", "BIOONTOLOGY_API_KEY"),
        description="BioPortal API key (https://bioportal.bioontology.org/account). "
        "BIOONTOLOGY_API_KEY is accepted as an alias (findingmodel convention).",
    )
    umls_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="UMLS_API_KEY",
        description="UMLS/UTS API key (https://uts.nlm.nih.gov/uts/profile)",
    )
    bioportal_base_url: str = "https://data.bioontology.org"
    umls_base_url: str = "https://uts-ws.nlm.nih.gov/rest"
    umls_version: str = "current"
    http_timeout: float = 30.0

    def bioportal_key(self) -> str | None:
        if self.bioportal_api_key is None:
            return None
        return self.bioportal_api_key.get_secret_value()

    def umls_key(self) -> str | None:
        if self.umls_api_key is None:
            return None
        return self.umls_api_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
