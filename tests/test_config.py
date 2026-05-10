import os
import pytest
from unittest.mock import patch

from config import load_config


def _make_yaml(teams_enabled=True, zalo_enabled=False):
    return f"""
schedule: "0 8 * * 1-5"
dashboard_id: 1
channels:
  teams:
    enabled: {"true" if teams_enabled else "false"}
  zalo:
    enabled: {"true" if zalo_enabled else "false"}
"""


def test_load_config_reads_cards_and_env(tmp_path):
    (tmp_path / "config.yaml").write_text(_make_yaml())
    env = {
        "METABASE_URL": "http://metabase.local",
        "METABASE_API_KEY": "key123",
        "TEAMS_WEBHOOK_URL": "https://webhook.url",
        "ZALO_ACCESS_TOKEN": "",
    }
    with patch.dict(os.environ, env, clear=True):
        config = load_config(str(tmp_path / "config.yaml"))

    assert config.dashboard_id == 1
    assert config.metabase_url == "http://metabase.local"
    assert config.metabase_api_key == "key123"
    assert config.teams_webhook_url == "https://webhook.url"
    assert config.channels.teams.enabled is True
    assert config.channels.zalo.enabled is False


def test_load_config_raises_if_metabase_url_missing(tmp_path):
    (tmp_path / "config.yaml").write_text(_make_yaml(teams_enabled=False))
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(KeyError):
            load_config(str(tmp_path / "config.yaml"))


def test_load_config_raises_if_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/config.yaml")


def test_load_config_raises_if_teams_enabled_but_webhook_missing(tmp_path):
    (tmp_path / "config.yaml").write_text(_make_yaml(teams_enabled=True))
    env = {"METABASE_URL": "http://m.local", "METABASE_API_KEY": "k"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="TEAMS_WEBHOOK_URL"):
            load_config(str(tmp_path / "config.yaml"))


def test_load_config_teams_webhook_is_none_when_not_set(tmp_path):
    (tmp_path / "config.yaml").write_text(_make_yaml(teams_enabled=False))
    env = {"METABASE_URL": "http://m.local", "METABASE_API_KEY": "k"}
    with patch.dict(os.environ, env, clear=True):
        config = load_config(str(tmp_path / "config.yaml"))
    assert config.teams_webhook_url is None


def test_load_config_raises_if_zalo_enabled_but_token_missing(tmp_path):
    (tmp_path / "config.yaml").write_text(_make_yaml(zalo_enabled=True))
    env = {"METABASE_URL": "http://m.local", "METABASE_API_KEY": "k", "TEAMS_WEBHOOK_URL": "https://wh.url"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="ZALO_ACCESS_TOKEN"):
            load_config(str(tmp_path / "config.yaml"))
