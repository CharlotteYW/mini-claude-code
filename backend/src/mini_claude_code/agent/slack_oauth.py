"""Slack OAuth v2 install + local installation store (M18).

Simplification: JSON file under workspace — not encrypted; single-tenant learning setup.
"""

from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mini_claude_code.config import Settings, get_settings, resolve_workspace_root

SLACK_OAUTH_AUTHORIZE = "https://slack.com/oauth/v2/authorize"
SLACK_OAUTH_ACCESS = "https://slack.com/api/oauth.v2.access"

# Bot scopes for channel messages + thread replies (Socket Mode).
DEFAULT_BOT_SCOPES = (
    "chat:write",
    "reactions:write",
    "channels:history",
    "groups:history",
    "im:history",
    "mpim:history",
)


@dataclass
class SlackInstallation:
    team_id: str
    team_name: str
    bot_token: str
    bot_user_id: str
    installed_at: str

    @classmethod
    def from_oauth_response(cls, payload: dict[str, Any]) -> SlackInstallation:
        team = payload.get("team") or {}
        bot = payload.get("bot") or {}
        token = payload.get("access_token") or bot.get("bot_access_token")
        if not token:
            raise ValueError("OAuth response missing bot access_token")
        team_id = str(team.get("id") or payload.get("team_id") or "")
        if not team_id:
            raise ValueError("OAuth response missing team id")
        return cls(
            team_id=team_id,
            team_name=str(team.get("name") or ""),
            bot_token=str(token),
            bot_user_id=str(bot.get("bot_user_id") or payload.get("bot_user_id") or ""),
            installed_at=datetime.now(timezone.utc).isoformat(),
        )


def installations_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    if settings.slack_installations_path.strip():
        return Path(settings.slack_installations_path).expanduser().resolve()
    return resolve_workspace_root(settings) / "slack_installations.json"


def generate_oauth_state() -> str:
    return secrets.token_urlsafe(24)


def build_install_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple[str, ...] = DEFAULT_BOT_SCOPES,
) -> str:
    params = {
        "client_id": client_id,
        "scope": ",".join(scopes),
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{SLACK_OAUTH_AUTHORIZE}?{urllib.parse.urlencode(params)}"


def exchange_oauth_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> SlackInstallation:
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        SLACK_OAUTH_ACCESS,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"Slack OAuth token exchange failed: {detail}") from exc
    if not payload.get("ok"):
        raise ValueError(f"Slack OAuth error: {payload.get('error', payload)!r}")
    return SlackInstallation.from_oauth_response(payload)


def load_installations(path: Path | None = None) -> dict[str, SlackInstallation]:
    path = path or installations_path()
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    out: dict[str, SlackInstallation] = {}
    for team_id, item in raw.items():
        if isinstance(item, dict):
            out[str(team_id)] = SlackInstallation(**item)
    return out


def save_installation(
    installation: SlackInstallation,
    path: Path | None = None,
) -> None:
    path = path or installations_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    all_items = load_installations(path)
    all_items[installation.team_id] = installation
    serializable = {tid: asdict(inst) for tid, inst in all_items.items()}
    path.write_text(json.dumps(serializable, indent=2) + "\n", encoding="utf-8")


def get_installation(
    team_id: str,
    path: Path | None = None,
) -> SlackInstallation | None:
    return load_installations(path).get(team_id)


def resolve_bot_token(
    team_id: str | None = None,
    *,
    settings: Settings | None = None,
) -> str | None:
    """Bot token from env override or installation store."""
    settings = settings or get_settings()
    if settings.slack_bot_token.strip():
        return settings.slack_bot_token.strip()
    if not team_id:
        installs = load_installations(installations_path(settings))
        if len(installs) == 1:
            return next(iter(installs.values())).bot_token
        return None
    inst = get_installation(team_id, installations_path(settings))
    return inst.bot_token if inst else None
