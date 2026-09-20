from orchestrator.config import Settings


def test_cors_origins_accepts_deployment_comma_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com, https://admin.example.com")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["https://app.example.com", "https://admin.example.com"]
