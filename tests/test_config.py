"""Settings / API-key loading."""

from med_ontology_lookup.config import Settings


def test_empty_bioportal_env_falls_back_to_bioontology(monkeypatch):
    monkeypatch.setenv("BIOPORTAL_API_KEY", "")
    monkeypatch.setenv("BIOONTOLOGY_API_KEY", "from-alias")
    monkeypatch.delenv("UMLS_API_KEY", raising=False)
    settings = Settings()
    assert settings.bioportal_key() == "from-alias"


def test_does_not_read_dotenv_file(tmp_path, monkeypatch):
    """Keys come from the process environment only; use uv --env-file to load files."""
    monkeypatch.delenv("BIOPORTAL_API_KEY", raising=False)
    monkeypatch.delenv("BIOONTOLOGY_API_KEY", raising=False)
    monkeypatch.delenv("UMLS_API_KEY", raising=False)
    (tmp_path / ".env").write_text("BIOONTOLOGY_API_KEY=from-file\nUMLS_API_KEY=from-file\n")
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.bioportal_key() is None
    assert settings.umls_key() is None


def test_blank_umls_key_is_unset(monkeypatch):
    monkeypatch.setenv("UMLS_API_KEY", "   ")
    monkeypatch.delenv("BIOPORTAL_API_KEY", raising=False)
    monkeypatch.delenv("BIOONTOLOGY_API_KEY", raising=False)
    settings = Settings()
    assert settings.umls_key() is None
