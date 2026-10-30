from pydantic import SecretStr

from backend.app.config import Settings


def test_settings_parse_environment_style_cors_list() -> None:
    settings = Settings(cors_origins="https://campus.example, http://localhost:3000")
    assert settings.cors_origins == [
        "https://campus.example",
        "http://localhost:3000",
    ]


def test_secret_setting_is_not_exposed_by_repr() -> None:
    settings = Settings(gemini_api_key=SecretStr("test-secret"))
    assert "test-secret" not in repr(settings)
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "test-secret"
