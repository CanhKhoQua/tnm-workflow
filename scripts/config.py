from __future__ import annotations

import os
import yaml
from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelConfig:
    enabled: bool


@dataclass(frozen=True)
class ChannelsConfig:
    teams: ChannelConfig
    zalo: ChannelConfig


@dataclass(frozen=True)
class Config:
    dashboard_id: int
    collection_id: int | None
    dashcard_ids: tuple[int, ...] | None
    channels: ChannelsConfig
    metabase_url: str
    metabase_api_key: str
    teams_webhook_url: str | None
    zalo_access_token: str | None
    webapp_url: str | None = None
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None
    r2_public_url: str | None = None


def load_config(config_path: str | None = None) -> Config:
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'configs', 'default.yaml'
        )
    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"config.yaml must be a YAML mapping, got {type(data).__name__}")

    try:
        channels = ChannelsConfig(
            teams=ChannelConfig(enabled=data["channels"]["teams"]["enabled"]),
            zalo=ChannelConfig(enabled=data["channels"]["zalo"]["enabled"]),
        )
        dashboard_id = int(data["dashboard_id"])
    except KeyError as exc:
        raise KeyError(f"Missing required config key {exc} in {config_path}") from exc

    raw_collection_id = data.get("collection_id")
    collection_id = int(raw_collection_id) if raw_collection_id is not None else None

    raw_dashcard_ids = data.get("dashcard_ids")
    dashcard_ids = tuple(int(i) for i in raw_dashcard_ids) if raw_dashcard_ids else None

    teams_webhook_url = data.get("teams_webhook_url") or os.environ.get("TEAMS_WEBHOOK_URL") or None
    zalo_access_token = data.get("zalo_access_token") or os.environ.get("ZALO_ACCESS_TOKEN") or None

    if channels.teams.enabled and not teams_webhook_url:
        raise ValueError("TEAMS_WEBHOOK_URL must be set when channels.teams.enabled is true")

    if channels.zalo.enabled and not zalo_access_token:
        raise ValueError("ZALO_ACCESS_TOKEN must be set when channels.zalo.enabled is true")

    return Config(
        dashboard_id=dashboard_id,
        collection_id=collection_id,
        dashcard_ids=dashcard_ids,
        channels=channels,
        metabase_url=os.environ["METABASE_URL"],
        metabase_api_key=os.environ["METABASE_API_KEY"],
        teams_webhook_url=teams_webhook_url,
        zalo_access_token=zalo_access_token,
        webapp_url=data.get("webapp_url") or None,
        r2_account_id=os.environ.get("R2_ACCOUNT_ID") or None,
        r2_access_key_id=os.environ.get("R2_ACCESS_KEY_ID") or None,
        r2_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY") or None,
        r2_bucket_name=os.environ.get("R2_BUCKET_NAME") or None,
        r2_public_url=os.environ.get("R2_PUBLIC_URL") or None,
    )
