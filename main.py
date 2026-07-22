"""Twitch Farmer — FastAPI backend.

Локально, без интернета: статика лежит в ./static, данные в ./data.
Запуск:
    python -m uvicorn main:app --reload
или просто:
    python main.py
"""
from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import os
import random
import re
import secrets
import shutil
import signal
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Empty
from typing import Any
from urllib.parse import quote

import aiohttp
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import auth as auth_mod
import backup as backup_mod
from campaigns import (
    InvalidTokenError,
    fetch_all_campaigns,
    load_catalog,
    resolve_streamers,
    save_catalog,
)
from auth import AuthError, AuthStore, RateLimiter

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"
DATA_DIR.mkdir(exist_ok=True)

# данные каждого пользователя изолированы в data/users/<uid>/
USERS_DIR = DATA_DIR / "users"

# legacy-пути (единое хранилище старых версий) — мигрируются в каталог админа
LEGACY_ACCOUNTS_FILE = DATA_DIR / "accounts.json"
LEGACY_STREAMERS_FILE = DATA_DIR / "streamers.txt"
LEGACY_STREAMER_CONFIGS_FILE = DATA_DIR / "streamer_configs.json"
LEGACY_PROXIES_FILE = DATA_DIR / "proxies.json"
POOL_PROXIES_FILE = DATA_DIR / "pool_proxies.json"
CONVERT_PROXIES_FILE = DATA_DIR / "convert_proxies.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
DEFAULT_CONVERT_CONCURRENCY = 3
CAMPAIGN_REFRESH_SECONDS = float(os.getenv("CAMPAIGN_REFRESH_SECONDS", "7200"))
CAMPAIGN_TOKEN: str | None = None
CAMPAIGN_LOGIN: str | None = None
MAX_API_BODY_BYTES = 8 * 1024 * 1024
ACTION_COOLDOWNS = {
    "proxy-check": 30.0,
    "account-check": 10.0,
    "farm-start": 15.0,
    "convert-start": 15.0,
    "account-check-bulk": 15.0,
}


def user_dir(uid: int) -> Path:
    d = USERS_DIR / str(int(uid))
    d.mkdir(parents=True, exist_ok=True)
    return d


def accounts_file(uid: int) -> Path:
    return user_dir(uid) / "accounts.json"


def streamers_file(uid: int) -> Path:
    return user_dir(uid) / "streamers.txt"


def streamer_configs_file(uid: int) -> Path:
    return user_dir(uid) / "streamer_configs.json"


def selected_campaigns_file(uid: int) -> Path:
    return user_dir(uid) / "selected_campaigns.json"


def proxies_file(uid: int) -> Path:
    return user_dir(uid) / "proxies.json"

# Import real Twitch miner
from client import TwitchMiner
from convert_worker import ANDROID_CLIENT_ID, run_convert_worker
from farm_worker import run_worker
from loguru import logger

# Configure loguru to write to file
logger.remove()
logger.add("miner.log", rotation="10 MB", level="INFO", encoding="utf-8")
logger.add(lambda msg: print(msg, end=""), level="INFO")  # Also print to console


# ───────── Модели ──────────────────────────────────────────────────────────
class Campaign(BaseModel):
    name: str = ""
    progress: int = 0
    season: str = ""
    drops: dict[str, Any] = Field(default_factory=dict)


class Account(BaseModel):
    login: str
    password: str = ""
    token: str = ""
    role: str = ""
    campaigns: list[Campaign] = Field(default_factory=lambda: [Campaign()])
    token_type: str | None = None
    check_snapshot: dict[str, Any] | None = None


class BulkCheckRequest(BaseModel):
    logins: list[str] | None = None
    checks: dict[str, bool] = Field(default_factory=dict)


class ConvertRequest(BaseModel):
    logins: list[str] | None = None
    concurrency: int | None = None


class ImportRequest(BaseModel):
    template: str
    data: str


class FarmStartRequest(BaseModel):
    logins: list[str] = Field(default_factory=list)
    stagger: float = 5.0
    concurrency: int | None = None


class CampaignSelectionRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    logins: list[str]
    template: str = "{login}:{password}:{token}"


class BulkRoleRequest(BaseModel):
    logins: list[str]
    role: str


class BulkDeleteRequest(BaseModel):
    logins: list[str] = Field(default_factory=list)


class ProxyImportRequest(BaseModel):
    data: str


class ProxyKeysRequest(BaseModel):
    keys: list[str] = Field(default_factory=list)


class StreamerConfigPayload(BaseModel):
    nicks: list[str] = Field(default_factory=list)


class StreamerConfigsState(BaseModel):
    active: str | None = None
    configs: dict[str, list[str]] = Field(default_factory=dict)


class SettingsRequest(BaseModel):
    convert_concurrency: int | None = None


# ───────── Хранилище ───────────────────────────────────────────────────────
def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_accounts(uid: int) -> list[dict]:
    raw = _read_json(accounts_file(uid), [])
    if not isinstance(raw, list):
        return []
    cleaned: list[dict] = []
    for a in raw:
        if not isinstance(a, dict) or "login" not in a:
            continue
        a.setdefault("password", "")
        a.setdefault("token", "")
        a.setdefault("role", "")
        a.setdefault("token_type", None)
        a.setdefault("check_snapshot", None)
        camps = a.get("campaigns")
        if not isinstance(camps, list) or not camps:
            a["campaigns"] = [{"name": "", "progress": 0, "season": "", "drops": {}}]
        else:
            for c in camps:
                c.setdefault("name", "")
                c.setdefault("progress", 0)
                c.setdefault("season", "")
                c.setdefault("drops", {})
        cleaned.append(a)
    return cleaned


def save_accounts(uid: int, accs: list[dict]) -> None:
    _write_json(accounts_file(uid), accs)


def load_proxies(uid: int) -> list[dict]:
    raw = _read_json(proxies_file(uid), [])
    if not isinstance(raw, list):
        return []
    proxies: list[dict] = []
    for proxy in raw:
        if not isinstance(proxy, dict):
            continue
        proxy.setdefault("raw", "")
        proxy.setdefault("scheme", "http")
        proxy.setdefault("host", "")
        proxy.setdefault("port", 0)
        proxy.setdefault("username", "")
        proxy.setdefault("password", "")
        proxy.setdefault("status", "unknown")
        proxy.setdefault("latency_ms", None)
        if proxy["raw"] and proxy["host"] and proxy["port"]:
            proxies.append(proxy)
    return proxies


def classify_token_type(status: int, payload: Any) -> str:
    if status != 200 or not isinstance(payload, dict):
        return "invalid"
    return "mobile" if payload.get("client_id") == ANDROID_CLIENT_ID else "web"


def _drop_summary(campaigns: list[dict]) -> dict[str, int]:
    summary = {"farmed": 0, "received": 0, "in_progress": 0}
    for campaign in campaigns:
        for drop in campaign.get("drops") or []:
            status = drop.get("status")
            if status == "ready":
                summary["farmed"] += 1
            elif status == "claimed":
                summary["received"] += 1
            elif status == "in_progress":
                summary["in_progress"] += 1
    return summary


async def _check_account_inventory(
    token: str, proxy: dict | None = None
) -> dict[str, Any]:
    """Validate one token and classify its current Twitch drop inventory."""
    client_id = TwitchMiner.CLIENT_ID
    user_agent = TwitchMiner.USER_AGENT
    gql_url = TwitchMiner.GQL_URL
    validate_url = TwitchMiner.VALIDATE_URL
    timeout = aiohttp.ClientTimeout(total=25)
    device_id = secrets.token_hex(16)
    session_id = secrets.token_hex(8)
    proxy_url = None
    if proxy:
        scheme = (proxy.get("scheme") or "http").lower()
        host = proxy.get("host")
        port = proxy.get("port")
        if host and port and not scheme.startswith("socks"):
            auth = ""
            username = proxy.get("username") or ""
            if username:
                password = proxy.get("password") or ""
                auth = f"{quote(str(username), safe='')}:{quote(str(password), safe='')}@"
            proxy_url = f"{scheme}://{auth}{host}:{port}"

    result: dict[str, Any] = {
        "valid": False,
        "token_type": "invalid",
        "campaigns": [],
        "awarded": [],
        "drops_summary": {"farmed": 0, "received": 0, "in_progress": 0},
    }
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US",
        "Authorization": f"OAuth {token}",
        "Client-Id": client_id,
        "Client-Session-Id": session_id,
        "User-Agent": user_agent,
        "X-Device-Id": device_id,
        "Origin": "https://www.twitch.tv",
        "Referer": "https://www.twitch.tv/",
    }
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            request_kwargs = {"proxy": proxy_url} if proxy_url else {}
            async with session.get(
                validate_url,
                headers={"Authorization": f"OAuth {token}"},
                **request_kwargs,
            ) as response:
                try:
                    validate_payload = await response.json()
                except (ValueError, aiohttp.ContentTypeError):
                    validate_payload = None
                result["token_type"] = classify_token_type(
                    response.status, validate_payload
                )
                if response.status != 200:
                    result["error"] = f"токен невалиден (HTTP {response.status})"
                    return result

            operation = {
                "operationName": "Inventory",
                "variables": {"fetchRewardCampaigns": True},
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": (
                            "d86775d0ef16a63a33ad52e80eaff963b2d5b72fada7c991504a57496e1d8e4b"
                        ),
                    }
                },
            }
            async with session.post(
                gql_url,
                json=[operation],
                headers=headers,
                **request_kwargs,
            ) as response:
                if response.status != 200:
                    result["error"] = f"не удалось получить инвентарь (HTTP {response.status})"
                    return result
                payload = await response.json()
            data = payload[0] if isinstance(payload, list) and payload else payload
            current_user = (data.get("data") or {}).get("currentUser") or {}
            inventory = current_user.get("inventory") or {}
            campaigns: list[dict[str, Any]] = []
            for campaign in inventory.get("dropCampaignsInProgress") or []:
                drops: list[dict[str, Any]] = []
                for drop in campaign.get("timeBasedDrops") or []:
                    self_data = drop.get("self") or {}
                    current = self_data.get("currentMinutesWatched", 0) or 0
                    required = drop.get("requiredMinutesWatched", 0) or 0
                    if self_data.get("isClaimed"):
                        status = "claimed"
                    elif self_data.get("dropInstanceID"):
                        status = "ready"
                    else:
                        status = "in_progress"
                    drops.append({
                        "name": drop.get("name") or "—",
                        "status": status,
                        "current": current,
                        "required": required,
                    })
                campaigns.append({
                    "name": campaign.get("name") or "—",
                    "drops": drops,
                })
            awarded = []
            for game_drop in inventory.get("gameEventDrops") or []:
                name = game_drop.get("name")
                if name and name not in awarded:
                    awarded.append(name)
            result["valid"] = True
            result["campaigns"] = campaigns
            result["awarded"] = awarded
            result["drops_summary"] = _drop_summary(campaigns)
            return result
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        result["error"] = f"ошибка проверки инвентаря: {type(exc).__name__}"
        return result
    except (ValueError, KeyError, IndexError, TypeError):
        result["error"] = "ошибка разбора ответа инвентаря"
        return result


def save_proxies(uid: int, proxies: list[dict]) -> None:
    _write_json(proxies_file(uid), proxies)


def load_pool_proxies() -> list[dict]:
    raw = _read_json(POOL_PROXIES_FILE, [])
    if not isinstance(raw, list):
        return []
    proxies: list[dict] = []
    for proxy in raw:
        if not isinstance(proxy, dict):
            continue
        proxy.setdefault("raw", "")
        proxy.setdefault("scheme", "http")
        proxy.setdefault("host", "")
        proxy.setdefault("port", 0)
        proxy.setdefault("username", "")
        proxy.setdefault("password", "")
        proxy.setdefault("status", "unknown")
        proxy.setdefault("latency_ms", None)
        if proxy["raw"] and proxy["host"] and proxy["port"]:
            proxies.append(proxy)
    return proxies


def save_pool_proxies(proxies: list[dict]) -> None:
    _write_json(POOL_PROXIES_FILE, proxies)


def load_convert_proxies() -> list[dict]:
    raw = _read_json(CONVERT_PROXIES_FILE, [])
    if not isinstance(raw, list):
        return []
    proxies: list[dict] = []
    for proxy in raw:
        if not isinstance(proxy, dict):
            continue
        proxy.setdefault("raw", "")
        proxy.setdefault("scheme", "http")
        proxy.setdefault("host", "")
        proxy.setdefault("port", 0)
        proxy.setdefault("username", "")
        proxy.setdefault("password", "")
        proxy.setdefault("status", "unknown")
        proxy.setdefault("latency_ms", None)
        if proxy["raw"] and proxy["host"] and proxy["port"]:
            proxies.append(proxy)
    return proxies


def save_convert_proxies(proxies: list[dict]) -> None:
    _write_json(CONVERT_PROXIES_FILE, proxies)


def _valid_port(value: str) -> bool:
    try:
        return 1 <= int(value) <= 65535
    except (TypeError, ValueError):
        return False


def _parse_proxy_line(line: str) -> dict | None:
    raw = line.strip()
    if not raw:
        return None
    scheme = "http"
    value = raw
    if "://" in value:
        scheme, value = value.split("://", 1)
        scheme = scheme.lower().strip()
        if not scheme or not value:
            return None

    username = ""
    password = ""
    if "@" in value:
        credentials, value = value.rsplit("@", 1)
        if ":" not in credentials:
            return None
        username, password = credentials.split(":", 1)
    elif value.count(":") == 3:
        parts = value.split(":")
        if _valid_port(parts[1]):
            value, port, username, password = parts
        elif _valid_port(parts[3]):
            username, password, value, port = parts
        else:
            return None
        if not value or not username:
            return None
        return {
            "raw": raw, "scheme": scheme, "host": value, "port": int(port),
            "username": username, "password": password,
            "status": "unknown", "latency_ms": None,
        }

    if ":" not in value:
        return None
    host, port = value.rsplit(":", 1)
    if not host or not _valid_port(port):
        return None
    return {
        "raw": raw, "scheme": scheme, "host": host, "port": int(port),
        "username": username, "password": password,
        "status": "unknown", "latency_ms": None,
    }


def load_cfg(uid: int) -> dict:
    raw = _read_json(streamer_configs_file(uid), {"active": None, "configs": {}})
    if not isinstance(raw, dict):
        raw = {"active": None, "configs": {}}
    raw.setdefault("active", None)
    raw.setdefault("configs", {})
    return raw


def save_cfg(uid: int, cfg: dict) -> None:
    _write_json(streamer_configs_file(uid), cfg)
    active = cfg.get("active")
    if active and active in cfg.get("configs", {}):
        nicks = cfg["configs"][active]
        streamers_file(uid).write_text(
            "\n".join(nicks) + ("\n" if nicks else ""), encoding="utf-8"
        )


def load_selected_campaigns(uid: int) -> list[str]:
    value = _read_json(selected_campaigns_file(uid), [])
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item) for item in value if item))


def save_selected_campaigns(uid: int, campaign_ids: list[str]) -> None:
    _write_json(selected_campaigns_file(uid), campaign_ids)


async def refresh_campaign_catalog() -> dict:
    """Refresh the shared catalog using an available user account token."""
    global CAMPAIGN_TOKEN, CAMPAIGN_LOGIN
    accounts: list[dict] = []
    for user in store.list_users():
        accounts.extend(load_accounts(user.id))
    candidates: list[tuple[str, str]] = []
    if CAMPAIGN_TOKEN and CAMPAIGN_LOGIN:
        candidates.append((CAMPAIGN_TOKEN, CAMPAIGN_LOGIN))
    candidates.extend(
        (account.get("token"), account.get("login") or "")
        for account in accounts
        if account.get("token")
        and account.get("token") != CAMPAIGN_TOKEN
    )
    for token, login in candidates:
        campaigns = await fetch_all_campaigns(token, login=login)
        if campaigns:
            CAMPAIGN_TOKEN = token
            CAMPAIGN_LOGIN = login
            return save_catalog(campaigns)
    return load_catalog()


async def campaign_catalog_refresher() -> None:
    while True:
        catalog = load_catalog()
        if (
            not catalog["campaigns"]
            or time.time() - float(catalog["fetched_at"] or 0)
            >= CAMPAIGN_REFRESH_SECONDS
        ):
            try:
                await refresh_campaign_catalog()
            except Exception:
                logger.exception("campaign catalog refresh failed")
        await asyncio.sleep(max(60.0, CAMPAIGN_REFRESH_SECONDS))


def best_campaign(acc: dict) -> dict:
    camps = acc.get("campaigns") or []
    named = [c for c in camps if (c.get("name") or "").strip()]
    if not named:
        return camps[0] if camps else {"name": "", "progress": 0, "season": "", "drops": {}}
    return max(named, key=lambda c: c.get("progress", 0))


def campaign_payloads(acc: dict) -> list[dict]:
    """Return only safe campaign fields for farm cards and WebSocket clients."""
    result: list[dict] = []
    for campaign in acc.get("campaigns") or []:
        if not isinstance(campaign, dict):
            continue
        result.append(
            {
                "name": campaign.get("name", "") or "",
                "progress": int(campaign.get("progress", 0) or 0),
                "season": campaign.get("season", "") or "",
                "drops": dict(campaign.get("drops") or {}),
            }
        )
    return result


def campaign_for_game(acc: dict, game_name: str | None) -> dict:
    campaigns = acc.get("campaigns") or []
    if game_name:
        for campaign in campaigns:
            if campaign.get("name") == game_name:
                return campaign
    return best_campaign(acc)


def working_proxies(uid: int) -> list[dict]:
    owner = store.get_user(int(uid))
    source = (
        load_pool_proxies()
        if owner and owner.proxy_mode == "pool"
        else load_proxies(int(uid))
    )
    return [
        proxy for proxy in source
        if proxy.get("status") == "valid"
        and (proxy.get("scheme") or "http").lower() in {"http", "https"}
    ]


# ───────── Парсер импорта (как в оригинале) ────────────────────────────────
def parse_import(template: str, data: str) -> list[dict]:
    template = (template or "").strip()
    data = (data or "").strip()
    if not template or not data:
        return []
    fields = re.findall(r"\{(\w+)\}", template)
    if not fields:
        return []

    seps = [":", "|", ";", "\t", ","]
    sep = next((d for d in seps if d in template), None)
    pat = None
    if not sep:
        pat = re.escape(template)
        for f in fields:
            pat = pat.replace(re.escape("{" + f + "}"), "([^\\n\\r]*?)", 1)
        pat = "^" + pat + "$"

    accs: list[dict] = []
    for raw_line in data.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        acc: dict = {
            "login": "",
            "password": "",
            "token": "",
            "role": "",
            "campaigns": [{"name": "", "progress": 0, "season": "", "drops": {}}],
        }
        values: list[str]
        field_names: list[str]
        if sep:
            values = [p.strip() for p in line.split(sep)]
            field_names = [
                match.group(1) if (match := re.fullmatch(r"\s*\{(\w+)\}\s*", part))
                else ""
                for part in template.split(sep)
            ]
        else:
            m = re.match(pat, line)
            if not m:
                continue
            values = list(m.groups())
            field_names = fields

        for i, f in enumerate(field_names):
            if not f:
                continue
            v = values[i] if i < len(values) else ""
            if f == "login":
                acc["login"] = v
            elif f == "password":
                acc["password"] = v
            elif f == "token":
                acc["token"] = v
            elif f == "role":
                acc["role"] = v
            elif f == "campaign":
                acc["campaigns"][0]["name"] = v
            elif f == "season":
                acc["campaigns"][0]["season"] = v
            elif f == "progress":
                try:
                    acc["campaigns"][0]["progress"] = int(v)
                except ValueError:
                    pass
        if acc["login"] or acc["token"]:
            if not acc["login"]:
                acc["login"] = "id_" + acc["token"][:8]
            accs.append(acc)
    return accs


# ───────── Реальный Twitch фарма ───────────────────────────────────────────────
class FarmEngine:
    """Реальный Twitch фарма с интеграцией через TwitchMiner."""

    # ─── публикация ─────────────────────────────────────────────────────
    async def broadcast(self, msg: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    # ─── isolated worker lifecycle ─────────────────────────────────────
    def __init__(self, owner_id: int) -> None:
        self.owner_id = int(owner_id)
        self.running = False
        self.task: asyncio.Task | None = None
        self.clients: set[WebSocket] = set()
        self.cards: dict[str, dict] = {}
        self.logs: list[dict] = []
        self.farm_accounts: dict[str, dict] = {}
        self.process = None
        self.go_process: asyncio.subprocess.Process | None = None
        self.go_engine = False
        self.mp_queue = None
        self.queue_drain_task: asyncio.Task | None = None
        self.last_start_counts = {
            "launched": 0,
            "skipped_web": 0,
            "skipped_unknown": 0,
            "skipped_invalid": 0,
        }

    def state(self) -> dict:
        alive = bool(
            (self.process and self.process.is_alive())
            or (self.go_process and self.go_process.returncode is None)
        )
        return {
            "running": alive,
            "logs": self.logs[-200:],
            "cards": [{"login": k, **v} for k, v in self.cards.items()],
        }

    def _workers_alive(self) -> bool:
        return bool(
            (self.process and self.process.is_alive())
            or (self.go_process and self.go_process.returncode is None)
        )

    async def start(
        self,
        selected_logins: list[str] | None = None,
        stagger: float = 5.0,
    ) -> None:
        self.last_start_error = None
        if (
            (self.process and self.process.is_alive())
            or (self.go_process and self.go_process.returncode is None)
        ):
            self.running = True
            await self._log("system", "warn", "farm already running")
            return
        if self.process is not None:
            try:
                self.process.close()
            except Exception:
                pass
        self.process = None
        self.go_process = None
        self.go_engine = False
        self.mp_queue = None
        self.running = False
        await self._log("system", "info", "starting farm...")

        accs = load_accounts(self.owner_id)
        if selected_logins:
            selected = set(selected_logins)
            accs = [a for a in accs if a.get("login") in selected]
        stagger = max(0.0, min(120.0, float(stagger)))
        if not accs:
            await self._log("system", "warn", "no accounts to farm")
            return
        await self._log("system", "info", f"found {len(accs)} accounts")
        self.last_start_counts = {
            "launched": 0,
            "skipped_web": sum(
                1 for a in accs
                if a.get("token_type") == "web" and not a.get("token")
            ),
            "skipped_unknown": sum(
                1 for a in accs if a.get("token_type") in {None, ""}
            ),
            "skipped_invalid": sum(
                1 for a in accs if a.get("token_type") == "invalid"
            ),
        }
        mobile_accs = [
            a for a in accs
            if a.get("token_type") == "mobile" and a.get("token")
        ]
        web_accs = [
            a for a in accs
            if a.get("token_type") == "web" and a.get("token")
        ]
        farm_accs = mobile_accs + web_accs
        tokens = [a["token"] for a in farm_accs]
        if not tokens:
            await self._log("system", "warn", "no tokens found in accounts")
            return
        await self._log("system", "info", f"found {len(tokens)} tokens")

        valid_proxies = working_proxies(self.owner_id)
        claim_proxies = load_convert_proxies()
        if valid_proxies:
            await self._log("system", "info", f"using {len(valid_proxies)} working proxy(s)")
        else:
            await self._log("system", "info", "no working proxies configured, farming directly")

        selected_ids = load_selected_campaigns(self.owner_id)
        catalog = load_catalog()
        campaigns = [
            campaign for campaign in catalog["campaigns"]
            if str(campaign.get("id")) in selected_ids
        ]
        if not campaigns:
            self.last_start_error = "выберите кампанию для фарма"
            await self._log("system", "warn", self.last_start_error)
            return

        streamers: list[str] = []
        invalid_tokens = 0
        valid_token_seen = False
        good_account: dict | None = None
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=25)
        ) as session:
            for campaign in campaigns:
                # Token validity is global, so once one account token works we
                # reuse it for the remaining campaigns instead of re-probing all.
                candidates = (
                    [good_account]
                    if good_account
                    else (mobile_accs or web_accs)
                )
                for account in candidates:
                    try:
                        resolved = await resolve_streamers(
                            account["token"],
                            account.get("login") or "",
                            str(campaign.get("id") or ""),
                            campaign.get("game_name") or "",
                            campaign.get("game_slug") or None,
                            max_channels=30,
                            session=session,
                        )
                    except InvalidTokenError:
                        invalid_tokens += 1
                        continue
                    valid_token_seen = True
                    if not resolved:
                        continue
                    good_account = account
                    for streamer in resolved:
                        if streamer not in streamers:
                            streamers.append(streamer)
                    break
                if len(streamers) >= 40:
                    break
        if not streamers:
            self.last_start_error = (
                "токены аккаунтов недействительны — перезалейте аккаунты"
                if invalid_tokens and not valid_token_seen
                else "не удалось найти стримеров для выбранных кампаний"
            )
            await self._log("system", "warn", self.last_start_error)
            return
        await self._log("system", "info", f"resolved {len(streamers)} campaign streamers")
        streamers_file(self.owner_id).write_text(
            "\n".join(streamers) + "\n", encoding="utf-8"
        )

        self.cards.clear()
        self.farm_accounts = {a["login"]: a for a in farm_accs if a.get("login")}
        for account in farm_accs:
            login = account.get("login")
            if not login:
                continue
            best = campaign_for_game(account, None)
            self.cards[login] = {
                "started_at": time.time(),
                "campaign": best.get("name", "") or "—",
                "progress": int(best.get("progress", 0) or 0),
                "season": best.get("season", ""),
                "drops": dict(best.get("drops") or {}),
                "campaigns": campaign_payloads(account),
                "log": "Initializing...",
            }

        config_values = {
            "connection_timeout": 30,
            "retry_delay": 5,
            "max_retries": 3,
            "watch_interval": 60,
            "inventory_refresh": 300,
            "inventory_check_minutes": 1,
            "offline_check_interval": 120,
            "data_dir": str(user_dir(self.owner_id)),
        }
        go_requested = os.getenv("FARM_ENGINE", "python").strip().lower() == "go"
        go_binary = Path(
            os.getenv("GO_WORKER_BIN", str(ROOT / "goworker" / "twitchfarmer-goworker"))
        )
        if not go_binary.is_absolute():
            go_binary = ROOT / go_binary
        go_available = go_requested and os.access(go_binary, os.X_OK)
        if go_requested and not go_available:
            await self._log(
                "system",
                "warn",
                "Go farm worker binary missing or not executable; falling back to Python worker",
            )
        go_accs = mobile_accs if go_available else []
        python_accs = web_accs if go_available else farm_accs
        if go_available and go_accs:
            job = {
                "owner_id": self.owner_id,
                "accounts": [
                    {"login": a.get("login", ""), "token": a["token"]}
                    for a in go_accs
                ],
                "proxies": valid_proxies,
                "streamers": list(streamers),
                "config": config_values,
                "stagger": stagger,
            }
            go_process = None
            try:
                go_process = await asyncio.create_subprocess_exec(
                    str(go_binary),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                )
                assert go_process.stdin is not None
                go_process.stdin.write(
                    (json.dumps(job, ensure_ascii=False) + "\n").encode("utf-8")
                )
                await go_process.stdin.drain()
                go_process.stdin.close()
                self.go_process = go_process
                self.go_engine = True
            except Exception:
                if go_process and go_process.returncode is None:
                    try:
                        go_process.kill()
                    except Exception:
                        pass
                await self._log(
                    "system",
                    "warn",
                    "Go farm worker failed to start; falling back to Python worker",
                )
                go_available = False
                go_accs = []
                python_accs = farm_accs

        if python_accs:
            ctx = mp.get_context("spawn")
            event_queue = ctx.Queue()
            process = ctx.Process(
                target=run_worker,
                args=(
                    self.owner_id,
                    [
                        {"login": a.get("login", ""), "token": a["token"]}
                        for a in python_accs
                    ],
                    valid_proxies,
                    claim_proxies,
                    list(streamers),
                    config_values,
                    event_queue,
                    stagger,
                ),
            )
            try:
                process.start()
            except Exception:
                event_queue.close()
                await self._log("system", "error", "failed to start farm worker")
                raise
            self.process = process
            self.mp_queue = event_queue
        self.running = True
        self.last_start_counts["launched"] = len(farm_accs)
        await self.broadcast({"type": "running", "running": True})
        await self.broadcast({"type": "snapshot", "cards": list(self.cards.items())})
        await self._log("system", "info", f"farm started, {len(farm_accs)} account(s)")
        engine_label = (
            "Go + Python"
            if self.go_engine and self.process
            else "Go"
            if self.go_engine
            else "Python"
        )
        await self._log(
            "system",
            "info",
            f"engine: {engine_label} worker process",
        )
        self.queue_drain_task = asyncio.create_task(self._drain_worker_events())
        self.task = self.queue_drain_task

    async def _drain_worker_events(self) -> None:
        drains = []
        if self.process is not None and self.mp_queue is not None:
            drains.append(asyncio.create_task(self._drain_python_worker_events()))
        if self.go_process is not None:
            drains.append(asyncio.create_task(self._drain_go_worker_events()))
        if not drains:
            return
        try:
            await asyncio.gather(*drains)
        except asyncio.CancelledError:
            for drain in drains:
                drain.cancel()
            await asyncio.gather(*drains, return_exceptions=True)
            raise
        finally:
            if self.running and not self._workers_alive():
                self.running = False
                await self._log("system", "info", "farm stopped")
                await self.broadcast({"type": "running", "running": False})

    async def _drain_python_worker_events(self) -> None:
        loop = asyncio.get_running_loop()
        process = self.process
        event_queue = self.mp_queue
        if process is None or event_queue is None:
            return
        account_cache: dict[str, dict] = {}
        account_cache_at = 0.0
        try:
            while self.running or process.is_alive():
                try:
                    event = await loop.run_in_executor(
                        None, event_queue.get, True, 0.5
                    )
                except Empty:
                    if not process.is_alive():
                        break
                    continue
                except (EOFError, OSError):
                    break
                if not isinstance(event, dict):
                    continue
                kind = event.get("type")
                login = event.get("login") or "system"
                if kind == "log":
                    message = str(event.get("message") or "")[:500]
                    await self._log(login, event.get("level", "info"), message)
                    if login in self.cards:
                        self.cards[login]["log"] = message
                        await self.broadcast({
                            "type": "card",
                            "login": login,
                            "log": message,
                        })
                elif kind == "card" and login in self.cards:
                    current_game = event.get("current_game")
                    if time.time() - account_cache_at >= 5:
                        account_cache = {
                            item.get("login"): item
                            for item in load_accounts(self.owner_id)
                            if item.get("login")
                        }
                        account_cache_at = time.time()
                    account = account_cache.get(login)
                    if account is not None:
                        self.farm_accounts[login] = account
                    else:
                        account = self.farm_accounts.get(login)
                    if account:
                        best = campaign_for_game(account, current_game)
                        updated = {
                            "campaign": best.get("name", "") or "—",
                            "progress": int(best.get("progress", 0) or 0),
                            "season": best.get("season", ""),
                            "drops": dict(best.get("drops") or {}),
                            "campaigns": campaign_payloads(account),
                            "current_game": current_game,
                            "watch_minutes": int(event.get("watch_minutes") or 0),
                        }
                        card = self.cards[login]
                        if any(card.get(k) != value for k, value in updated.items()):
                            card.update(updated)
                            await self.broadcast({
                                "type": "card", "login": login, **updated
                            })
        except asyncio.CancelledError:
            raise
        finally:
            if process is not None and not process.is_alive():
                try:
                    process.close()
                    event_queue.close()
                except Exception:
                    pass
                if self.process is process:
                    self.process = None
                    self.mp_queue = None

    async def _drain_go_worker_events(self) -> None:
        process = self.go_process
        if process is None or process.stdout is None:
            return
        account_cache: dict[str, dict] = {}
        account_cache_at = 0.0
        try:
            while self.running or process.returncode is None:
                line = await process.stdout.readline()
                if not line:
                    break
                try:
                    event = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get("type")
                login = event.get("login") or "system"
                if kind == "log":
                    message = str(event.get("message") or "")[:500]
                    await self._log(login, event.get("level", "info"), message)
                    if login in self.cards:
                        self.cards[login]["log"] = message
                        await self.broadcast({
                            "type": "card",
                            "login": login,
                            "log": message,
                        })
                elif kind == "progress" and login in self.cards:
                    await self._merge_go_progress(login, event.get("progress") or [])
                elif kind == "card" and login in self.cards:
                    current_game = event.get("current_game")
                    if time.time() - account_cache_at >= 5:
                        account_cache = {
                            item.get("login"): item
                            for item in load_accounts(self.owner_id)
                            if item.get("login")
                        }
                        account_cache_at = time.time()
                    account = account_cache.get(login)
                    if account is not None:
                        self.farm_accounts[login] = account
                    else:
                        account = self.farm_accounts.get(login)
                    if account:
                        best = campaign_for_game(account, current_game)
                        updated = {
                            "campaign": best.get("name", "") or "—",
                            "progress": int(best.get("progress", 0) or 0),
                            "season": best.get("season", ""),
                            "drops": dict(best.get("drops") or {}),
                            "campaigns": campaign_payloads(account),
                            "current_game": current_game,
                            "watch_minutes": int(event.get("watch_minutes") or 0),
                        }
                        go_progress = event.get("progress")
                        if go_progress is not None:
                            updated["progress"] = int(go_progress)
                        card = self.cards[login]
                        if any(card.get(k) != value for k, value in updated.items()):
                            card.update(updated)
                            await self.broadcast({
                                "type": "card", "login": login, **updated
                            })
        except asyncio.CancelledError:
            raise
        finally:
            if process.returncode is None:
                try:
                    await process.wait()
                except Exception:
                    pass
            if self.go_process is process:
                self.go_process = None
                self.go_engine = False

    async def _merge_go_progress(self, login: str, rows: list[dict]) -> None:
        accounts = load_accounts(self.owner_id)
        account = next(
            (item for item in accounts if item.get("login") == login),
            None,
        )
        if account is None:
            account = self.farm_accounts.get(login)
            if account is None:
                return
            return

        changed = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            campaign_name = str(row.get("campaign") or "")
            drop_name = str(row.get("drop") or "")
            game_name = str(row.get("game_name") or "")
            if not drop_name:
                continue
            campaigns = account.setdefault("campaigns", [])
            if not isinstance(campaigns, list):
                campaigns = []
                account["campaigns"] = campaigns
            campaign = next(
                (
                    item for item in campaigns
                    if isinstance(item, dict)
                    and campaign_name
                    and item.get("season") == campaign_name
                    and (not game_name or item.get("name") == game_name)
                ),
                None,
            )
            if campaign is None and campaign_name:
                campaign = next(
                    (
                        item for item in campaigns
                        if isinstance(item, dict)
                        and item.get("season") == campaign_name
                    ),
                    None,
                )
            if campaign is None and game_name:
                campaign = next(
                    (
                        item for item in campaigns
                        if isinstance(item, dict)
                        and item.get("name") == game_name
                    ),
                    None,
                )
            if campaign is None:
                campaign = {
                    "name": game_name or campaign_name,
                    "progress": 0,
                    "season": campaign_name,
                    "drops": {},
                }
                campaigns.append(campaign)
                changed = True
            campaign.setdefault("name", game_name or campaign_name)
            campaign.setdefault("season", campaign_name)
            drops = campaign.setdefault("drops", {})
            if not isinstance(drops, dict):
                drops = {}
                campaign["drops"] = drops
            current = int(row.get("current") or 0)
            required = int(row.get("required") or 0)
            percent = (
                min(100, max(0, int(current * 100 / required)))
                if required > 0 else 0
            )
            value = {
                "current": current,
                "required": required,
                "progress": percent,
            }
            if drops.get(drop_name) != value:
                drops[drop_name] = value
                changed = True
            values = [
                int(item.get("progress") or 0)
                for item in drops.values()
                if isinstance(item, dict)
            ]
            campaign_progress = (
                int(sum(values) / len(values)) if values else 0
            )
            if campaign.get("progress") != campaign_progress:
                campaign["progress"] = campaign_progress
                changed = True

        if not changed:
            return
        async with _account_write_lock(self.owner_id):
            current_accounts = load_accounts(self.owner_id)
            current_account = next(
                (
                    item for item in current_accounts
                    if item.get("login") == login
                ),
                None,
            )
            if current_account is None:
                return
            current_account["campaigns"] = account.get("campaigns", [])
            _save_accounts_atomic(self.owner_id, current_accounts)
            account = current_account
            self.farm_accounts[login] = account
        current_game = self.cards[login].get("current_game")
        best = campaign_for_game(account, current_game)
        updated = {
            "campaign": best.get("name", "") or "—",
            "progress": int(best.get("progress", 0) or 0),
            "season": best.get("season", ""),
            "drops": dict(best.get("drops") or {}),
            "campaigns": campaign_payloads(account),
        }
        card = self.cards[login]
        if any(card.get(key) != value for key, value in updated.items()):
            card.update(updated)
            await self.broadcast({"type": "card", "login": login, **updated})

    async def stop(self) -> None:
        process = self.process
        go_process = self.go_process
        if not self.running and not (
            (process and process.is_alive())
            or (go_process and go_process.returncode is None)
        ):
            self.cards.clear()
            return
        self.running = False
        drain = self.queue_drain_task
        self.queue_drain_task = None
        self.task = None
        if drain:
            drain.cancel()
            try:
                await drain
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        if process and process.is_alive():
            loop = asyncio.get_running_loop()
            pid = process.pid
            try:
                pgid = os.getpgid(pid)
            except Exception:
                pgid = None

            def _killpg() -> None:
                # Reap orphaned descendants (e.g. browsers) only when the worker
                # is its own session/group leader (setsid succeeded). Never
                # signal the app's own process group.
                if pgid is not None and pgid == pid and pgid != os.getpgrp():
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass

            def terminate_and_join() -> None:
                try:
                    process.terminate()
                    process.join(4)
                    if process.is_alive():
                        process.kill()
                        process.join(3)
                except Exception:
                    pass
                _killpg()
        if go_process and go_process.returncode is None:
            pid = go_process.pid
            try:
                pgid = os.getpgid(pid)
            except Exception:
                pgid = None
            if pgid is not None and pgid == pid and pgid != os.getpgrp():
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
            try:
                await asyncio.wait_for(go_process.wait(), timeout=4)
            except asyncio.TimeoutError:
                if pgid is not None and pgid == pid and pgid != os.getpgrp():
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass
                try:
                    go_process.kill()
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(go_process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    pass

        if process and process.is_alive():
            loop = asyncio.get_running_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, terminate_and_join), timeout=10
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except Exception:
                    pass
                _killpg()
        if process and not process.is_alive():
            try:
                process.close()
            except Exception:
                pass
        if self.mp_queue is not None:
            try:
                self.mp_queue.cancel_join_thread()
                self.mp_queue.close()
            except Exception:
                pass
        self.process = None
        self.go_process = None
        self.go_engine = False
        self.mp_queue = None
        self.farm_accounts.clear()
        self.cards.clear()
        await self._log("system", "info", "farm stopped")
        await self.broadcast({"type": "running", "running": False})

    async def _log(self, login: str, level: str, message: str) -> None:
        entry = {"ts": time.time(), "login": login, "level": level, "message": message}
        self.logs.append(entry)
        if len(self.logs) > 500:
            self.logs = self.logs[-300:]
        await self.broadcast({"type": "log", **entry})


# ───────── Конвертация web-токенов ────────────────────────────────────────────
def _save_accounts_atomic(uid: int, accounts: list[dict]) -> None:
    path = accounts_file(uid)
    fd, temp_name = tempfile.mkstemp(prefix=".accounts-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(accounts, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def load_global_settings() -> dict:
    data = _read_json(SETTINGS_FILE, {})
    return data if isinstance(data, dict) else {}


def get_convert_concurrency_setting() -> int:
    raw = load_global_settings().get("convert_concurrency")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        try:
            value = int(os.getenv("CONVERT_CONCURRENCY", str(DEFAULT_CONVERT_CONCURRENCY)))
        except ValueError:
            value = DEFAULT_CONVERT_CONCURRENCY
    return max(1, min(32, value))


def _convert_concurrency(value: int | None = None) -> int:
    if value is None:
        return get_convert_concurrency_setting()
    return max(1, min(32, int(value)))


class ConvertEngine:
    """Browser-based web-token conversion isolated in a killable process."""

    def __init__(self, owner_id: int) -> None:
        self.owner_id = int(owner_id)
        self.running = False
        self.done = 0
        self.total = 0
        self.minted = 0
        self.bad_password = 0
        self.twofa = 0
        self.timeout = 0
        self.error = 0
        self.concurrency = _convert_concurrency()
        self._auto_farm = None
        self.clients: set[WebSocket] = set()
        self.process = None
        self.mp_queue = None
        self.queue_drain_task: asyncio.Task | None = None

    def state(self) -> dict:
        return {
            "running": bool(self.process and self.process.is_alive()),
            "done": self.done,
            "total": self.total,
            "minted": self.minted,
            "bad_password": self.bad_password,
            "2fa": self.twofa,
            "timeout": self.timeout,
            "error": self.error,
            "concurrency": self.concurrency,
        }

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def start(
        self,
        logins: list[str] | None = None,
        concurrency: int | None = None,
    ) -> None:
        if self.process and self.process.is_alive():
            self.running = True
            return
        self.concurrency = _convert_concurrency(concurrency)
        accounts = load_accounts(self.owner_id)
        wanted = set(logins) if logins is not None else None
        accounts = [
            account for account in accounts
            if (
                (wanted is not None and account.get("login") in wanted)
                or (wanted is None and account.get("token_type") == "web")
            )
            and account.get("token")
        ]
        self.done = self.minted = self.bad_password = self.twofa = 0
        self.timeout = self.error = 0
        self.total = len(accounts)
        if not accounts:
            self.running = False
            return
        source = accounts_file(self.owner_id)
        backup = source.with_name(f"{source.name}.bak-{int(time.time())}")
        if source.exists():
            shutil.copy2(source, backup)
        ctx = mp.get_context("spawn")
        event_queue = ctx.Queue()
        process = ctx.Process(
            target=run_convert_worker,
            args=(
                accounts,
                load_convert_proxies(),
                event_queue,
                self.concurrency,
                user_dir(self.owner_id) / "convert_debug",
            ),
        )
        process.start()
        self.process = process
        self.mp_queue = event_queue
        self.running = True
        self.queue_drain_task = asyncio.create_task(self._drain())

    async def _apply_minted(self, login: str, token: str) -> None:
        accounts = load_accounts(self.owner_id)
        for account in accounts:
            if account.get("login") == login:
                account["token"] = token
                account["token_type"] = "mobile"
                account["check_snapshot"] = None
                break
        _save_accounts_atomic(self.owner_id, accounts)

    async def _drain(self) -> None:
        loop = asyncio.get_running_loop()
        process = self.process
        queue = self.mp_queue
        if process is None or queue is None:
            return
        try:
            while self.running or process.is_alive():
                try:
                    event = await loop.run_in_executor(None, queue.get, True, 0.5)
                except Empty:
                    if not process.is_alive():
                        break
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get("type")
                if kind == "convert_result":
                    token = event.pop("new_token", None)
                    if event.get("status") == "minted" and token:
                        await self._apply_minted(event.get("login", ""), token)
                    elif event.get("status") == "minted":
                        event["status"] = "error"
                    status = event.get("status", "error")
                    if status not in {"minted", "bad_password", "2fa", "timeout", "error"}:
                        status = "error"
                    if status == "2fa":
                        self.twofa += 1
                    else:
                        setattr(self, status, getattr(self, status) + 1)
                    self.done += 1
                    await self.broadcast(event)
                elif kind == "convert_log":
                    stage_messages = {
                        "auth_started": "convert_stage_auth_started",
                        "authorization_received": (
                            "convert_stage_authorization_received"
                        ),
                        "token_received": "convert_stage_token_received",
                    }
                    message_key = stage_messages.get(event.get("stage"))
                    login = event.get("login", "")
                    if message_key:
                        farm_eng = get_engine(self.owner_id)
                        await farm_eng._log(login, "info", message_key)
                elif kind == "convert_progress":
                    self.done = int(event.get("done", self.done))
                    await self.broadcast({
                        "type": "convert_progress",
                        "done": self.done,
                        "total": self.total,
                    })
                elif kind == "convert_done":
                    self.minted = int(event.get("minted", self.minted))
                    self.bad_password = int(event.get("bad_password", self.bad_password))
                    self.twofa = int(event.get("2fa", self.twofa))
                    self.timeout = int(event.get("timeout", self.timeout))
                    self.error = int(event.get("error", self.error))
                    await self.broadcast({
                        "type": "convert_done",
                        "minted": self.minted,
                        "bad_password": self.bad_password,
                        "2fa": self.twofa,
                        "timeout": self.timeout,
                        "error": self.error,
                        "total": self.total,
                    })
                    if self._auto_farm:
                        info = self._auto_farm
                        self._auto_farm = None
                        all_accs = load_accounts(self.owner_id)
                        # ограничиваем исходным выбором пользователя: фармим
                        # только выбранные мобильные + только что сконвертированные
                        # из выбранных веб-аккаунтов (пустой выбор = все)
                        sel = set(info.get("logins") or [])
                        mobile_logins = [
                            a.get("login") for a in all_accs
                            if a.get("token_type") == "mobile" and a.get("login")
                            and (not sel or a.get("login") in sel)
                        ]
                        limit = int(info.get("limit") or 0)
                        if not info.get("is_admin") and limit > 0:
                            mobile_logins = mobile_logins[:limit]
                        farm_eng = get_engine(self.owner_id)
                        await farm_eng.start(
                            mobile_logins, info.get("stagger", 5.0)
                        )
                        await self.broadcast({
                            "type": "farm_auto_started",
                            "launched": len(mobile_logins),
                            "running": farm_eng.running,
                        })
                    break
        except asyncio.CancelledError:
            raise
        finally:
            self.running = False

    async def stop(self) -> None:
        process = self.process
        self.running = False
        self._auto_farm = None
        if self.queue_drain_task:
            self.queue_drain_task.cancel()
            try:
                await self.queue_drain_task
            except (asyncio.CancelledError, Exception):
                pass
        if process and process.is_alive():
            loop = asyncio.get_running_loop()
            pid = process.pid

            def kill() -> None:
                try:
                    pgid = os.getpgid(pid)
                except Exception:
                    pgid = None
                try:
                    process.terminate()
                    process.join(4)
                    if process.is_alive():
                        process.kill()
                        process.join(3)
                except Exception:
                    pass
                if pgid is not None and pgid == pid and pgid != os.getpgrp():
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass

            await loop.run_in_executor(None, kill)
        if process and not process.is_alive():
            try:
                process.close()
            except Exception:
                pass
        if self.mp_queue is not None:
            try:
                self.mp_queue.cancel_join_thread()
                self.mp_queue.close()
            except Exception:
                pass
        self.process = None
        self.mp_queue = None
        self.queue_drain_task = None


# ───────── Массовая проверка аккаунтов ───────────────────────────────────────
CHECK_TASKS: dict[int, asyncio.Task] = {}
CHECK_STATES: dict[int, dict[str, int | bool]] = {}
ACCOUNT_WRITE_LOCKS: dict[int, asyncio.Lock] = {}


def _account_write_lock(uid: int) -> asyncio.Lock:
    uid = int(uid)
    lock = ACCOUNT_WRITE_LOCKS.get(uid)
    if lock is None:
        lock = asyncio.Lock()
        ACCOUNT_WRITE_LOCKS[uid] = lock
    return lock


def _check_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "valid": bool(result.get("valid")),
        "token_type": result.get("token_type"),
        "campaigns": result.get("campaigns") or [],
        "drops_summary": result.get("drops_summary") or {
            "farmed": 0, "received": 0, "in_progress": 0
        },
        "awarded": result.get("awarded") or [],
        "checked_at": time.time(),
    }


async def _run_bulk_check(
    uid: int, accounts: list[dict], checks: dict[str, bool]
) -> None:
    engine = get_engine(uid)
    total = len(accounts)
    state = {"running": True, "done": 0, "total": total}
    CHECK_STATES[uid] = state
    semaphore = asyncio.Semaphore(25)
    proxies = working_proxies(uid)
    updates: dict[str, tuple[dict, dict]] = {}

    async def check_one(index: int, account: dict) -> None:
        async with semaphore:
            proxy = proxies[index % len(proxies)] if proxies else None
            result = await _check_account_inventory(account.get("token") or "", proxy)
            snapshot = _check_snapshot(result)
            updates[account.get("login", "")] = (result, snapshot)
            state["done"] = int(state["done"]) + 1
            drops = snapshot["drops_summary"]
            await engine.broadcast({
                "type": "check_result",
                "login": account.get("login", ""),
                "valid": bool(result.get("valid")),
                "token_type": result.get("token_type"),
                "campaigns": snapshot["campaigns"] if checks.get("campaigns", True) else [],
                "drops_summary": drops if checks.get("drops", True) else {
                    "farmed": 0, "received": 0, "in_progress": 0
                },
                "awarded": snapshot["awarded"] if checks.get("drops", True) else [],
            })
            await engine.broadcast({
                "type": "check_progress",
                "done": state["done"],
                "total": total,
            })

    try:
        await asyncio.gather(
            *(check_one(index, account) for index, account in enumerate(accounts))
        )
        async with _account_write_lock(uid):
            current = load_accounts(uid)
            by_login = {item.get("login"): item for item in current}
            ok = invalid = 0
            for login, (result, snapshot) in updates.items():
                item = by_login.get(login)
                if item is None:
                    continue
                item["token_type"] = result.get("token_type")
                item["check_snapshot"] = snapshot
                if result.get("valid"):
                    ok += 1
                else:
                    invalid += 1
            _save_accounts_atomic(uid, current)
        await engine.broadcast({
            "type": "check_done", "total": total, "ok": ok, "invalid": invalid
        })
    except asyncio.CancelledError:
        raise
    finally:
        state["running"] = False
        CHECK_TASKS.pop(uid, None)


# ───────── Реестр движков (по одному на пользователя) ───────────────────────
ENGINES: dict[int, FarmEngine] = {}
CONVERT_ENGINES: dict[int, ConvertEngine] = {}


def get_engine(uid: int) -> FarmEngine:
    uid = int(uid)
    eng = ENGINES.get(uid)
    if eng is None:
        eng = FarmEngine(uid)
        ENGINES[uid] = eng
    return eng


def get_convert_engine(uid: int) -> ConvertEngine:
    uid = int(uid)
    engine = CONVERT_ENGINES.get(uid)
    if engine is None:
        engine = ConvertEngine(uid)
        CONVERT_ENGINES[uid] = engine
    return engine


# ───────── Auth / панель пользователей ──────────────────────────────────────
PANEL_DB = DATA_DIR / "panel.db"
store = AuthStore(PANEL_DB)
rate_limiter = RateLimiter()

# пути, доступные без активной сессии
PUBLIC_API = {"/api/auth/login"}
# пути, доступные при истёкшей подписке / отключённом аккаунте
SUB_EXEMPT = {"/api/auth/me", "/api/auth/logout"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _client_ip(request: Request) -> str:
    # доверяем только прямому соединению; XFF намеренно не используем,
    # чтобы клиент не мог подделать IP для обхода rate-limit
    return request.client.host if request.client else "unknown"


def _migrate_legacy_data(uid: int) -> None:
    """Переносит старое единое хранилище (data/*.json) в каталог админа."""
    pairs = [
        (LEGACY_ACCOUNTS_FILE, accounts_file(uid)),
        (LEGACY_PROXIES_FILE, proxies_file(uid)),
        (LEGACY_STREAMER_CONFIGS_FILE, streamer_configs_file(uid)),
        (LEGACY_STREAMERS_FILE, streamers_file(uid)),
    ]
    for src, dst in pairs:
        try:
            if src.exists() and not dst.exists():
                dst.write_bytes(src.read_bytes())
                logger.info(f"[MIGRATE] {src.name} → users/{uid}/{dst.name}")
        except Exception as e:
            logger.warning(f"[MIGRATE] {src.name} failed: {e!r}")


def bootstrap_admin() -> None:
    """Создаёт первого администратора, если пользователей ещё нет."""
    if store.count_users() > 0:
        return
    username = os.getenv("PANEL_ADMIN_USER", "admin").strip() or "admin"
    password = os.getenv("PANEL_ADMIN_PASSWORD", "").strip()
    generated = False
    if not password:
        password = secrets_token()
        generated = True
    try:
        admin = store.create_user(
            username, password, role="admin", thread_limit=10_000
        )
    except AuthError as e:
        logger.error(f"failed to bootstrap admin: {e.message}")
        return
    _migrate_legacy_data(admin.id)
    if generated:
        creds_file = DATA_DIR / "INITIAL_ADMIN.txt"
        creds_file.write_text(
            f"username: {username}\npassword: {password}\n", encoding="utf-8"
        )
        try:
            os.chmod(creds_file, 0o600)
        except OSError:
            pass
        logger.warning(
            f"[ADMIN CREATED] username='{username}', "
            f"password saved to {creds_file} — смените после входа!"
        )
    else:
        logger.info(f"[ADMIN CREATED] username='{username}' (из env)")


def secrets_token() -> str:
    import secrets as _s
    return _s.token_urlsafe(12)


# ───────── App ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    bootstrap_admin()
    store.purge_expired_sessions()
    backup_task = asyncio.create_task(backup_mod.backup_scheduler(store))
    campaign_task = asyncio.create_task(campaign_catalog_refresher())
    try:
        yield
    finally:
        backup_task.cancel()
        campaign_task.cancel()
        try:
            await backup_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await campaign_task
        except (asyncio.CancelledError, Exception):
            pass
        for eng in list(ENGINES.values()):
            try:
                await eng.stop()
            except Exception:
                pass
        for eng in list(CONVERT_ENGINES.values()):
            try:
                await eng.stop()
            except Exception:
                pass


app = FastAPI(title="Twitch Farmer", lifespan=lifespan)


# ───────── Middleware: безопасность + аутентификация + CSRF ─────────────────
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method

    if path.startswith("/api/") and method in {"POST", "PUT"}:
        content_length = request.headers.get("content-length")
        try:
            if content_length is not None and int(content_length) > MAX_API_BODY_BYTES:
                return JSONResponse(
                    {"detail": "request body too large"}, status_code=413
                )
        except ValueError:
            return JSONResponse({"detail": "invalid content length"}, status_code=400)

    # аутентификация только для /api/* (кроме публичных)
    if path.startswith("/api/") and path not in PUBLIC_API:
        token = request.cookies.get(auth_mod.SESSION_COOKIE, "")
        session = store.get_session(token)
        if not session:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        user = store.get_user(session["user_id"])
        if not user or not user.enabled:
            return JSONResponse({"detail": "account disabled"}, status_code=403)

        # CSRF для небезопасных методов (double-submit + серверная проверка)
        if method not in SAFE_METHODS:
            header = request.headers.get("X-CSRF-Token", "")
            if not header or not hmac_equal(header, session["csrf"]):
                return JSONResponse({"detail": "csrf token invalid"}, status_code=403)

        # только админ — к /api/admin/*
        if path.startswith("/api/admin/") and not user.is_admin:
            return JSONResponse({"detail": "admin only"}, status_code=403)

        # подписка/срок действия (админ и служебные пути — исключение)
        if (
            not user.is_admin
            and path not in SUB_EXEMPT
            and not user.subscription_active
        ):
            return JSONResponse(
                {"detail": "subscription expired"}, status_code=403
            )

        request.state.user = user
        request.state.session = session

    response = await call_next(request)

    # security-заголовки на все ответы
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: https://static-cdn.jtvnw.net; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
    )
    return response


def hmac_equal(a: str, b: str) -> bool:
    import hmac as _h
    return _h.compare_digest(a, b)


def _uid(request: Request) -> int:
    """ID текущего пользователя (проставлен middleware для всех /api/*)."""
    return int(request.state.user.id)


def _throttle_user(request: Request, action: str) -> None:
    key = f"action:{_uid(request)}:{action}"
    wait = rate_limiter.check(key)
    if wait > 0:
        retry_after = str(int(wait) + 1)
        raise HTTPException(
            429,
            f"too many requests, retry in {retry_after}s",
            headers={"Retry-After": retry_after},
        )
    rate_limiter.record_cooldown(key, ACTION_COOLDOWNS[action])


@app.exception_handler(AuthError)
async def _auth_error_handler(request: Request, exc: AuthError):  # noqa: ARG001
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


# ───── accounts ────────────────────────────────────────────────────────────
@app.get("/api/accounts")
def api_accounts(request: Request) -> list[dict]:
    return load_accounts(_uid(request))


@app.post("/api/accounts/{login}/check")
async def api_account_check(request: Request, login: str) -> dict:
    _throttle_user(request, "account-check")
    uid = _uid(request)
    accs = load_accounts(uid)
    account = next((item for item in accs if item.get("login") == login), None)
    if account is None:
        raise HTTPException(404, "account not found")

    proxies = working_proxies(uid)
    proxy = proxies[0] if proxies else None
    result = await _check_account_inventory(account.get("token") or "", proxy)
    snapshot = {
        "valid": bool(result.get("valid")),
        "token_type": result.get("token_type"),
        "campaigns": result.get("campaigns") or [],
        "drops_summary": result.get("drops_summary") or {},
        "awarded": result.get("awarded") or [],
        "checked_at": time.time(),
    }
    async with _account_write_lock(uid):
        current = load_accounts(uid)
        current_account = next(
            (item for item in current if item.get("login") == login),
            None,
        )
        if current_account is None:
            raise HTTPException(404, "account not found")
        current_account["token_type"] = result.get("token_type")
        current_account["check_snapshot"] = snapshot
        _save_accounts_atomic(uid, current)
    return result


@app.post("/api/accounts/check-bulk")
async def api_accounts_check_bulk(
    request: Request, body: BulkCheckRequest
) -> dict:
    _throttle_user(request, "account-check-bulk")
    uid = _uid(request)
    existing = load_accounts(uid)
    wanted = set(body.logins) if body.logins is not None else None
    accounts = [
        account for account in existing
        if wanted is None or account.get("login") in wanted
    ]
    current = CHECK_TASKS.get(uid)
    if current and not current.done():
        raise HTTPException(409, "account check already running")
    task = asyncio.create_task(_run_bulk_check(uid, accounts, body.checks))
    CHECK_TASKS[uid] = task
    CHECK_STATES[uid] = {"running": True, "done": 0, "total": len(accounts)}
    return {"running": True, "done": 0, "total": len(accounts)}


@app.get("/api/accounts/check/state")
def api_accounts_check_state(request: Request) -> dict:
    state = CHECK_STATES.get(
        _uid(request), {"running": False, "done": 0, "total": 0}
    )
    return {
        "running": bool(state.get("running")),
        "done": int(state.get("done", 0)),
        "total": int(state.get("total", 0)),
    }


@app.post("/api/accounts/convert")
async def api_accounts_convert(
    request: Request, body: ConvertRequest
) -> dict:
    _throttle_user(request, "convert-start")
    engine = get_convert_engine(_uid(request))
    if engine.process and engine.process.is_alive():
        raise HTTPException(409, "conversion already running")
    await engine.start(body.logins, body.concurrency)
    return engine.state()


@app.post("/api/accounts/convert/stop")
async def api_accounts_convert_stop(request: Request) -> dict:
    engine = get_convert_engine(_uid(request))
    await engine.stop()
    return engine.state()


@app.get("/api/convert/state")
def api_convert_state(request: Request) -> dict:
    return get_convert_engine(_uid(request)).state()


@app.get("/api/campaigns")
def api_campaigns(request: Request) -> dict:
    uid = _uid(request)
    catalog = load_catalog()
    known = {str(item.get("id")) for item in catalog["campaigns"]}
    selected = [item for item in load_selected_campaigns(uid) if item in known]
    return {
        "fetched_at": catalog["fetched_at"],
        "campaigns": catalog["campaigns"],
        "selected": selected,
    }


@app.post("/api/campaigns/refresh")
async def api_campaigns_refresh(request: Request) -> dict:
    if not request.state.user.is_admin:
        raise HTTPException(403, "admin only")
    uid = _uid(request)
    catalog = await refresh_campaign_catalog()
    known = {str(item.get("id")) for item in catalog["campaigns"]}
    selected = [item for item in load_selected_campaigns(uid) if item in known]
    return {
        "fetched_at": catalog["fetched_at"],
        "campaigns": catalog["campaigns"],
        "selected": selected,
    }


@app.post("/api/admin/campaigns/refresh")
async def api_admin_campaigns_refresh(request: Request) -> dict:
    catalog = await refresh_campaign_catalog()
    return {
        "fetched_at": catalog["fetched_at"],
        "campaigns": catalog["campaigns"],
    }


@app.get("/api/campaigns/selected")
def api_campaigns_selected(request: Request) -> list[str]:
    return load_selected_campaigns(_uid(request))


@app.put("/api/campaigns/selected")
def api_campaigns_selected_update(
    request: Request, body: CampaignSelectionRequest
) -> list[str]:
    catalog_ids = {
        str(item.get("id")) for item in load_catalog()["campaigns"]
    }
    selected = list(dict.fromkeys(
        item for item in body.ids if str(item) in catalog_ids
    ))
    save_selected_campaigns(_uid(request), selected)
    return selected


@app.post("/api/accounts", status_code=201)
def api_account_create(request: Request, acc: Account) -> dict:
    uid = _uid(request)
    accs = load_accounts(uid)
    if any(a.get("login") == acc.login for a in accs):
        raise HTTPException(409, f"account '{acc.login}' already exists")
    accs.append(acc.model_dump())
    save_accounts(uid, accs)
    return acc.model_dump()


@app.put("/api/accounts/{login}")
def api_account_update(request: Request, login: str, acc: Account) -> dict:
    uid = _uid(request)
    accs = load_accounts(uid)
    for i, a in enumerate(accs):
        if a.get("login") == login:
            updated = acc.model_dump()
            if acc.token_type is None and a.get("token_type") is not None:
                updated["token_type"] = a.get("token_type")
            if acc.check_snapshot is None and a.get("check_snapshot") is not None:
                updated["check_snapshot"] = a.get("check_snapshot")
            accs[i] = updated
            save_accounts(uid, accs)
            return accs[i]
    raise HTTPException(404, "not found")


@app.delete("/api/accounts/{login}", status_code=204)
def api_account_delete(request: Request, login: str):
    uid = _uid(request)
    accs = load_accounts(uid)
    new = [a for a in accs if a.get("login") != login]
    if len(new) == len(accs):
        raise HTTPException(404, "not found")
    save_accounts(uid, new)
    return Response(status_code=204)


@app.post("/api/accounts/import")
def api_import(request: Request, req: ImportRequest) -> dict:
    uid = _uid(request)
    parsed = parse_import(req.template, req.data)
    if not parsed:
        return {"imported": 0, "duplicates": 0, "accounts": []}
    accs = load_accounts(uid)
    existing = {a.get("login") for a in accs}
    new: list[dict] = []
    duplicates = 0
    for a in parsed:
        if a["login"] in existing:
            duplicates += 1
            continue
        existing.add(a["login"])
        new.append(a)
    accs.extend(new)
    save_accounts(uid, accs)
    return {"imported": len(new), "duplicates": duplicates, "accounts": new}


@app.post("/api/accounts/export")
def api_export(request: Request, req: ExportRequest) -> dict:
    accs = load_accounts(_uid(request))
    by_login = {a["login"]: a for a in accs}
    lines: list[str] = []
    for login in req.logins:
        a = by_login.get(login)
        if not a:
            continue
        c = best_campaign(a)
        try:
            line = req.template.format(
                login=a.get("login", ""),
                password=a.get("password", ""),
                token=a.get("token", ""),
                role=a.get("role", ""),
                campaign_name=c.get("name", ""),
                campaign_progress=c.get("progress", 0),
                campaign_season=c.get("season", ""),
            )
        except Exception as e:
            raise HTTPException(400, f"bad template: {e}") from e
        lines.append(line)
    return {"text": "\n".join(lines), "count": len(lines)}


@app.post("/api/accounts/bulk-role")
def api_bulk_role(request: Request, req: BulkRoleRequest) -> dict:
    uid = _uid(request)
    accs = load_accounts(uid)
    updated = 0
    for a in accs:
        if a.get("login") in req.logins:
            a["role"] = req.role
            updated += 1
    save_accounts(uid, accs)
    return {"updated": updated}


@app.post("/api/accounts/bulk-delete")
def api_bulk_delete(request: Request, req: BulkDeleteRequest) -> dict:
    uid = _uid(request)
    selected = set(req.logins)
    accs = load_accounts(uid)
    remaining = [a for a in accs if a.get("login") not in selected]
    deleted = len(accs) - len(remaining)
    save_accounts(uid, remaining)
    return {"deleted": deleted}


# ───── proxies ─────────────────────────────────────────────────────────────
def _pool_mode_user(request: Request) -> bool:
    user = request.state.user
    return not user.is_admin and user.proxy_mode == "pool"


@app.get("/api/proxies")
def api_proxies(request: Request) -> list[dict]:
    if _pool_mode_user(request):
        return []
    return load_proxies(_uid(request))


@app.post("/api/proxies/import")
def api_proxies_import(request: Request, req: ProxyImportRequest) -> dict:
    if _pool_mode_user(request):
        raise HTTPException(403, "proxy pool is managed by the administrator")
    uid = _uid(request)
    proxies = load_proxies(uid)
    existing = {(p["host"], p["port"], p["username"]) for p in proxies}
    new: list[dict] = []
    skipped = 0
    for line in req.data.splitlines():
        proxy = _parse_proxy_line(line)
        if not proxy:
            skipped += 1
            continue
        key = (proxy["host"], proxy["port"], proxy["username"])
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        new.append(proxy)
    proxies.extend(new)
    save_proxies(uid, proxies)
    return {
        "imported": len(new),
        "duplicates": skipped,
        "proxies": new,
    }


@app.post("/api/proxies/bulk-delete")
def api_proxies_bulk_delete(request: Request, req: ProxyKeysRequest) -> dict:
    if _pool_mode_user(request):
        raise HTTPException(403, "proxy pool is managed by the administrator")
    uid = _uid(request)
    selected = set(req.keys)
    proxies = load_proxies(uid)
    remaining = [p for p in proxies if p.get("raw") not in selected]
    deleted = len(proxies) - len(remaining)
    save_proxies(uid, remaining)
    return {"deleted": deleted}


async def _check_proxies(proxies: list[dict]) -> None:
    semaphore = asyncio.Semaphore(50)
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        import aiohttp_socks
    except ImportError:
        aiohttp_socks = None

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async def check(proxy: dict) -> None:
            async with semaphore:
                proxy["status"] = "invalid"
                proxy["latency_ms"] = None
                scheme = (proxy.get("scheme") or "http").lower()
                if scheme.startswith("socks") and aiohttp_socks is None:
                    proxy["status"] = "unsupported"
                    return
                proxy_url = (
                    f"{scheme}://{proxy['host']}:{proxy['port']}"
                )
                if proxy.get("username"):
                    proxy_url = (
                        f"{scheme}://{proxy['username']}:{proxy.get('password', '')}"
                        f"@{proxy['host']}:{proxy['port']}"
                    )
                started = time.perf_counter()
                try:
                    if scheme.startswith("socks"):
                        connector = aiohttp_socks.ProxyConnector.from_url(proxy_url)
                        async with aiohttp.ClientSession(
                            connector=connector, timeout=timeout
                        ) as socks_session:
                            async with socks_session.get("https://api.ipify.org") as response:
                                response.raise_for_status()
                                await response.read()
                    else:
                        async with session.get(
                            "https://api.ipify.org", proxy=proxy_url
                        ) as response:
                            response.raise_for_status()
                            await response.read()
                    proxy["status"] = "valid"
                    proxy["latency_ms"] = round(
                        (time.perf_counter() - started) * 1000
                    )
                except Exception:
                    pass

        await asyncio.gather(*(check(proxy) for proxy in proxies))


@app.post("/api/proxies/check")
async def api_proxies_check(
    request: Request, req: ProxyKeysRequest | None = None
) -> list[dict]:
    if _pool_mode_user(request):
        raise HTTPException(403, "proxy pool is managed by the administrator")
    _throttle_user(request, "proxy-check")
    uid = _uid(request)
    proxies = load_proxies(uid)
    keys = set(req.keys) if req and req.keys else None
    selected = [p for p in proxies if keys is None or p.get("raw") in keys]
    await _check_proxies(selected)
    save_proxies(uid, proxies)
    return proxies


@app.get("/api/admin/proxy-pool")
async def api_admin_proxy_pool() -> list[dict]:
    return load_pool_proxies()


@app.post("/api/admin/proxy-pool/import")
async def api_admin_proxy_pool_import(req: ProxyImportRequest) -> dict:
    proxies = load_pool_proxies()
    existing = {(p["host"], p["port"], p["username"]) for p in proxies}
    new: list[dict] = []
    skipped = 0
    for line in req.data.splitlines():
        proxy = _parse_proxy_line(line)
        if not proxy:
            skipped += 1
            continue
        key = (proxy["host"], proxy["port"], proxy["username"])
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        new.append(proxy)
    proxies.extend(new)
    save_pool_proxies(proxies)
    return {"imported": len(new), "duplicates": skipped, "proxies": new}


@app.post("/api/admin/proxy-pool/bulk-delete")
async def api_admin_proxy_pool_bulk_delete(req: ProxyKeysRequest) -> dict:
    selected = set(req.keys)
    proxies = load_pool_proxies()
    remaining = [p for p in proxies if p.get("raw") not in selected]
    save_pool_proxies(remaining)
    return {"deleted": len(proxies) - len(remaining)}


@app.post("/api/admin/proxy-pool/check")
async def api_admin_proxy_pool_check(
    req: ProxyKeysRequest | None = None,
) -> list[dict]:
    proxies = load_pool_proxies()
    keys = set(req.keys) if req and req.keys else None
    selected = [p for p in proxies if keys is None or p.get("raw") in keys]
    await _check_proxies(selected)
    save_pool_proxies(proxies)
    return proxies


@app.get("/api/admin/convert-proxy-pool")
async def api_admin_convert_proxy_pool() -> list[dict]:
    return load_convert_proxies()


@app.post("/api/admin/convert-proxy-pool/import")
async def api_admin_convert_proxy_pool_import(req: ProxyImportRequest) -> dict:
    proxies = load_convert_proxies()
    existing = {(p["host"], p["port"], p["username"]) for p in proxies}
    new: list[dict] = []
    skipped = 0
    for line in req.data.splitlines():
        proxy = _parse_proxy_line(line)
        if not proxy:
            skipped += 1
            continue
        key = (proxy["host"], proxy["port"], proxy["username"])
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        new.append(proxy)
    proxies.extend(new)
    save_convert_proxies(proxies)
    return {"imported": len(new), "duplicates": skipped, "proxies": new}


@app.post("/api/admin/convert-proxy-pool/bulk-delete")
async def api_admin_convert_proxy_pool_bulk_delete(req: ProxyKeysRequest) -> dict:
    selected = set(req.keys)
    proxies = load_convert_proxies()
    remaining = [p for p in proxies if p.get("raw") not in selected]
    save_convert_proxies(remaining)
    return {"deleted": len(proxies) - len(remaining)}


@app.post("/api/admin/convert-proxy-pool/check")
async def api_admin_convert_proxy_pool_check(
    req: ProxyKeysRequest | None = None,
) -> list[dict]:
    proxies = load_convert_proxies()
    keys = set(req.keys) if req and req.keys else None
    selected = [p for p in proxies if keys is None or p.get("raw") in keys]
    await _check_proxies(selected)
    save_convert_proxies(proxies)
    return proxies


# ───── streamer configs ────────────────────────────────────────────────────
@app.get("/api/streamers/configs")
def api_cfg_get(request: Request) -> dict:
    return load_cfg(_uid(request))


class CfgCreate(BaseModel):
    name: str


@app.post("/api/streamers/configs", status_code=201)
def api_cfg_create(request: Request, payload: CfgCreate) -> dict:
    uid = _uid(request)
    cfg = load_cfg(uid)
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "empty name")
    if name in cfg["configs"]:
        raise HTTPException(409, "exists")
    cfg["configs"][name] = []
    if not cfg.get("active"):
        cfg["active"] = name
    save_cfg(uid, cfg)
    return cfg


@app.put("/api/streamers/configs/{name}")
def api_cfg_update(request: Request, name: str, payload: StreamerConfigPayload) -> dict:
    uid = _uid(request)
    cfg = load_cfg(uid)
    if name not in cfg["configs"]:
        raise HTTPException(404, "not found")
    seen: set[str] = set()
    cleaned: list[str] = []
    for n in payload.nicks:
        n = (n or "").strip()
        if not n or n.lower() in seen:
            continue
        seen.add(n.lower())
        cleaned.append(n)
    cfg["configs"][name] = cleaned
    save_cfg(uid, cfg)
    return cfg


class CfgRename(BaseModel):
    new_name: str


@app.post("/api/streamers/configs/{name}/rename")
def api_cfg_rename(request: Request, name: str, payload: CfgRename) -> dict:
    uid = _uid(request)
    cfg = load_cfg(uid)
    if name not in cfg["configs"]:
        raise HTTPException(404, "not found")
    new = payload.new_name.strip()
    if not new or new == name:
        raise HTTPException(400, "bad name")
    if new in cfg["configs"]:
        raise HTTPException(409, "exists")
    cfg["configs"][new] = cfg["configs"].pop(name)
    if cfg.get("active") == name:
        cfg["active"] = new
    save_cfg(uid, cfg)
    return cfg


@app.delete("/api/streamers/configs/{name}")
def api_cfg_delete(request: Request, name: str) -> dict:
    uid = _uid(request)
    cfg = load_cfg(uid)
    if name not in cfg["configs"]:
        raise HTTPException(404, "not found")
    cfg["configs"].pop(name)
    if cfg.get("active") == name:
        cfg["active"] = next(iter(cfg["configs"]), None)
    save_cfg(uid, cfg)
    return cfg


@app.post("/api/streamers/configs/{name}/activate")
def api_cfg_activate(request: Request, name: str) -> dict:
    uid = _uid(request)
    cfg = load_cfg(uid)
    if name not in cfg["configs"]:
        raise HTTPException(404, "not found")
    cfg["active"] = name
    save_cfg(uid, cfg)
    return cfg


# ───── farm ────────────────────────────────────────────────────────────────
@app.get("/api/farm/state")
def api_farm_state(request: Request) -> dict:
    return get_engine(_uid(request)).state()


@app.post("/api/farm/start")
async def api_farm_start(request: Request, req: FarmStartRequest | None = None) -> dict:
    logger.info("API: farm start requested")
    _throttle_user(request, "farm-start")
    user = request.state.user
    eng = get_engine(user.id)
    logins = list(req.logins) if req and req.logins else []
    stagger = req.stagger if req else 5.0
    all_accounts = load_accounts(user.id)
    by_login = {a.get("login"): a for a in all_accounts}
    requested = (
        [a for a in all_accounts if a.get("login")]
        if not logins
        else [by_login[login] for login in logins if login in by_login]
    )
    launchable = [
        a for a in requested
        if a.get("token_type") in {"mobile", "web"} and a.get("token")
    ]
    skipped = {
        "skipped_web": sum(
            1 for a in requested
            if a.get("token_type") == "web" and not a.get("token")
        ),
        "skipped_unknown": sum(
            1 for a in requested if a.get("token_type") in {None, ""}
        ),
        "skipped_invalid": sum(
            1 for a in requested if a.get("token_type") == "invalid"
        ),
    }

    # лимит потоков: сколько аккаунтов пользователь может фармить одновременно
    if not user.is_admin:
        limit = int(user.thread_limit or 0)
        if limit <= 0:
            raise HTTPException(
                403, "thread limit is 0 — обратитесь к администратору"
            )
        if not requested:
            raise HTTPException(400, "нет аккаунтов для запуска")
        accepted = [
            a.get("login") for a in launchable[:limit] if a.get("login")
        ]
        over_limit = [
            a.get("login") for a in launchable[limit:] if a.get("login")
        ]
        if not accepted:
            return {
                "running": False,
                "limit": limit,
                "accepted": [],
                "over_limit": over_limit,
                "launched": 0,
                **skipped,
            }
        # для не-admin всегда передаём явный список (без fallback ко всем)
        await eng.start(accepted, stagger)
        if eng.last_start_error:
            raise HTTPException(400, eng.last_start_error)
        logger.info("API: farm start completed")
        return {
            "running": eng.running,
            "limit": limit,
            "accepted": accepted,
            "over_limit": over_limit,
            "launched": len(accepted),
            **skipped,
        }

    accepted = [a.get("login") for a in launchable if a.get("login")]
    if not accepted:
        return {
            "running": False,
            "accepted": [],
            "over_limit": [],
            "launched": 0,
            **skipped,
        }
    await eng.start(accepted, stagger)
    if eng.last_start_error:
        raise HTTPException(400, eng.last_start_error)
    logger.info("API: farm start completed")
    return {
        "running": eng.running,
        "accepted": accepted,
        "over_limit": [],
        "launched": len(accepted),
        **skipped,
    }


@app.post("/api/farm/stop")
async def api_farm_stop(request: Request) -> dict:
    uid = _uid(request)
    convert_eng = get_convert_engine(uid)
    await convert_eng.stop()
    eng = get_engine(uid)
    await eng.stop()
    return {"running": eng.running}


@app.websocket("/ws/farm")
async def ws_farm(ws: WebSocket) -> None:
    token = ws.cookies.get(auth_mod.SESSION_COOKIE, "")
    session = store.get_session(token)
    if not session:
        await ws.close(code=1008)
        return
    user = store.get_user(session["user_id"])
    if not user or not user.enabled or not user.subscription_active:
        await ws.close(code=1008)
        return
    await ws.accept()
    eng = get_engine(user.id)
    convert = get_convert_engine(user.id)
    eng.clients.add(ws)
    convert.clients.add(ws)
    try:
        await ws.send_json({"type": "init", "state": eng.state()})
        await ws.send_json({"type": "convert_state", **convert.state()})
        while True:
            # клиент может присылать пинги; нам контент не нужен
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        eng.clients.discard(ws)
        convert.clients.discard(ws)


# ───── auth ────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str = Field(max_length=256)
    password: str = Field(max_length=256)
    totp: str | None = Field(default=None, max_length=16)


def _set_session_cookies(resp: JSONResponse, token: str, csrf: str) -> None:
    resp.set_cookie(
        auth_mod.SESSION_COOKIE, token,
        max_age=auth_mod.SESSION_TTL_SECONDS,
        httponly=True, samesite="strict", secure=auth_mod.COOKIE_SECURE, path="/",
    )
    # csrf cookie читается JS-ом и отправляется обратно в заголовке (double-submit)
    resp.set_cookie(
        auth_mod.CSRF_COOKIE, csrf,
        max_age=auth_mod.SESSION_TTL_SECONDS,
        httponly=False, samesite="strict", secure=auth_mod.COOKIE_SECURE, path="/",
    )


@app.post("/api/auth/login")
async def api_login(request: Request, body: LoginRequest) -> JSONResponse:
    ip = _client_ip(request)
    ua = request.headers.get("User-Agent", "")

    # rate-limit: по IP и по (IP+логин) — против брутфорса и распыления
    for key in (f"ip:{ip}", f"user:{ip}:{body.username[:64]}"):
        wait = rate_limiter.check(key)
        if wait > 0:
            store.audit("login_ratelimited", body.username, ip)
            resp = JSONResponse(
                {"detail": f"too many attempts, retry in {int(wait) + 1}s"},
                status_code=429,
            )
            resp.headers["Retry-After"] = str(int(wait) + 1)
            return resp

    row = store.verify_credentials(body.username, body.password)
    if row is None:
        for key in (f"ip:{ip}", f"user:{ip}:{body.username[:64]}"):
            rate_limiter.record_failure(key)
        store.audit("login_failed", body.username, ip)
        # generic-ошибка — против перечисления пользователей
        return JSONResponse({"detail": "invalid credentials"}, status_code=401)

    if not row["enabled"]:
        store.audit("login_disabled", body.username, ip)
        return JSONResponse({"detail": "invalid credentials"}, status_code=401)

    # опциональная 2FA
    if row["totp_secret"]:
        if not body.totp or not auth_mod.verify_totp(row["totp_secret"], body.totp):
            store.audit("login_totp_failed", body.username, ip)
            return JSONResponse(
                {"detail": "totp required", "totp_required": True}, status_code=401
            )

    # проверка подписки для не-админов
    user = store.get_user(row["id"])
    if user is not None and not user.is_admin and not user.subscription_active:
        store.audit("login_no_subscription", body.username, ip)
        return JSONResponse({"detail": "subscription expired"}, status_code=403)

    # успех: регенерируем сессию (защита от session fixation)
    rate_limiter.record_success(f"ip:{ip}")
    rate_limiter.record_success(f"user:{ip}:{body.username[:64]}")
    token, csrf = store.create_session(row["id"], ip, ua)
    store.touch_login(row["id"])
    store.audit("login_ok", body.username, ip)
    resp = JSONResponse({"ok": True, "user": user.public() if user else None})
    _set_session_cookies(resp, token, csrf)
    return resp


@app.post("/api/auth/logout")
async def api_logout(request: Request) -> JSONResponse:
    token = request.cookies.get(auth_mod.SESSION_COOKIE, "")
    if token:
        store.delete_session(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth_mod.SESSION_COOKIE, path="/")
    resp.delete_cookie(auth_mod.CSRF_COOKIE, path="/")
    return resp


@app.get("/api/auth/me")
async def api_me(request: Request) -> dict:
    user = request.state.user
    return {"user": user.public(), "csrf": request.state.session["csrf"]}


# ───── admin: управление пользователями ─────────────────────────────────────
class AdminUserCreate(BaseModel):
    username: str = Field(max_length=256)
    password: str = Field(max_length=256)
    role: str = "user"
    thread_limit: int = 1
    subscription_days: float | None = None
    enabled: bool = True
    proxy_mode: str = "own"


class AdminUserUpdate(BaseModel):
    role: str | None = None
    thread_limit: int | None = None
    enabled: bool | None = None
    subscription_days: float | None = None      # установить срок = now + N дней
    add_subscription_days: float | None = None  # продлить на N дней
    proxy_mode: str | None = None


class AdminPasswordReset(BaseModel):
    password: str = Field(max_length=256)


@app.get("/api/admin/users")
async def api_admin_users() -> list[dict]:
    result: list[dict] = []
    for user in store.list_users():
        item = user.public()
        engine = ENGINES.get(user.id)
        farming = bool(engine and engine.process and engine.process.is_alive())
        item.update(
            {
                "accounts_count": len(load_accounts(user.id)),
                "proxy_count": (
                    0 if user.proxy_mode == "pool"
                    else len(load_proxies(user.id))
                ),
                "farming": farming,
                "farming_accounts": (
                    len(engine.cards) if farming and engine else 0
                ),
                "uses_shared_pool": user.proxy_mode == "pool",
            }
        )
        result.append(item)
    return result


@app.get("/api/admin/settings")
async def api_admin_settings() -> dict:
    return {"convert_concurrency": get_convert_concurrency_setting()}


@app.put("/api/admin/settings")
async def api_admin_settings_update(request: Request, body: SettingsRequest) -> dict:
    data = load_global_settings()
    if body.convert_concurrency is not None:
        data["convert_concurrency"] = max(1, min(32, int(body.convert_concurrency)))
    _write_json(SETTINGS_FILE, data)
    store.audit("settings_updated", "convert_concurrency", _client_ip(request),
                f"value={data.get('convert_concurrency')} by={request.state.user.username}")
    return {"convert_concurrency": get_convert_concurrency_setting()}


@app.post("/api/admin/users", status_code=201)
async def api_admin_user_create(request: Request, body: AdminUserCreate) -> dict:
    user = store.create_user(
        body.username, body.password, role=body.role,
        thread_limit=body.thread_limit,
        subscription_days=body.subscription_days, enabled=body.enabled,
        proxy_mode=body.proxy_mode,
    )
    store.audit("user_created", body.username, _client_ip(request),
                f"by={request.state.user.username}")
    await backup_mod.send_backup(store, reason="user_created")
    return user.public()


@app.put("/api/admin/users/{user_id}")
async def api_admin_user_update(
    request: Request, user_id: int, body: AdminUserUpdate
) -> dict:
    target = store.get_user(user_id)
    if not target:
        raise HTTPException(404, "user not found")
    # нельзя снять/понизить последнего активного админа
    if target.is_admin and store.count_admins(exclude_id=user_id) == 0:
        if (body.role is not None and body.role != "admin") or body.enabled is False:
            raise HTTPException(400, "cannot demote/disable the last admin")
    sub_until = None
    if body.subscription_days is not None:
        sub_until = (
            time.time() + body.subscription_days * 86400
            if body.subscription_days > 0 else 0
        )
    user = store.update_user(
        user_id, role=body.role, thread_limit=body.thread_limit,
        enabled=body.enabled, subscription_until=sub_until,
        add_subscription_days=body.add_subscription_days,
        proxy_mode=body.proxy_mode,
    )
    store.audit("user_updated", target.username, _client_ip(request),
                f"by={request.state.user.username}")
    await backup_mod.send_backup(store, reason="user_updated")
    return user.public()


@app.post("/api/admin/users/{user_id}/password")
async def api_admin_user_password(
    request: Request, user_id: int, body: AdminPasswordReset
) -> dict:
    target = store.get_user(user_id)
    if not target:
        raise HTTPException(404, "user not found")
    store.set_password(user_id, body.password)
    store.audit("password_reset", target.username, _client_ip(request),
                f"by={request.state.user.username}")
    return {"ok": True}


@app.delete("/api/admin/users/{user_id}", status_code=204)
async def api_admin_user_delete(request: Request, user_id: int):
    target = store.get_user(user_id)
    if not target:
        raise HTTPException(404, "user not found")
    if target.id == request.state.user.id:
        raise HTTPException(400, "cannot delete yourself")
    if target.is_admin and store.count_admins(exclude_id=user_id) == 0:
        raise HTTPException(400, "cannot delete the last admin")
    store.delete_user(user_id)
    store.audit("user_deleted", target.username, _client_ip(request),
                f"by={request.state.user.username}")
    await backup_mod.send_backup(store, reason="user_deleted")
    return Response(status_code=204)


@app.get("/api/admin/audit")
async def api_admin_audit() -> list[dict]:
    return store.recent_audit(100)


@app.get("/api/admin/backup/status")
async def api_admin_backup_status() -> dict:
    return {
        "configured": backup_mod.is_configured(),
        "interval_hours": backup_mod.INTERVAL_HOURS,
        "include_accounts": backup_mod.INCLUDE_ACCOUNTS,
    }


@app.post("/api/admin/backup")
async def api_admin_backup(request: Request) -> dict:
    result = await backup_mod.send_backup(store, reason="manual")
    store.audit("backup_manual", request.state.user.username, _client_ip(request),
                result.get("detail", ""))
    return result


# ───── static ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/admin")
def admin_page() -> FileResponse:
    # доступ проверяется на клиенте (loadMe) и на сервере для всех /api/admin/*
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
