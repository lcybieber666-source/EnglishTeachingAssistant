import importlib
import sys


SENSITIVE_ENV_KEYS = [
    "DASHSCOPE_API_KEY",
    "DB_PASSWORD",
]


def reload_config_module(monkeypatch, env_overrides=None):
    env_overrides = env_overrides or {}

    for key in SENSITIVE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    for key, value in env_overrides.items():
        monkeypatch.setenv(key, value)

    sys.modules.pop("config", None)
    import config

    return importlib.reload(config)


def test_config_reads_sensitive_values_from_environment(monkeypatch):
    config_module = reload_config_module(
        monkeypatch,
        {
            "DASHSCOPE_API_KEY": "env-api-key",
            "DB_PASSWORD": "env-db-password",
        },
    )

    config = config_module.Config()

    assert config.api_key == "env-api-key"
    assert config.db_password == "env-db-password"


def test_config_does_not_ship_sensitive_defaults(monkeypatch):
    config_module = reload_config_module(
        monkeypatch,
        {
            "DASHSCOPE_API_KEY": "",
            "DB_PASSWORD": "",
        },
    )

    config = config_module.Config()

    assert config.api_key == ""
    assert config.db_password == ""
