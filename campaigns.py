"""Twitch Drops campaign catalog and streamer resolution helpers."""

from __future__ import annotations

import json
import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

import aiohttp

from client import TwitchMiner

ROOT = Path(__file__).resolve().parent
CATALOG_FILE = ROOT / "data" / "campaigns.json"
GQL_URL = TwitchMiner.GQL_URL
CLIENT_ID = TwitchMiner.CLIENT_ID
USER_AGENT = TwitchMiner.USER_AGENT

_CAMPAIGNS_HASH = "5a4da2ab3d5b47c9f9ce864e727b2cb346af1e3ea8b897fe8f704a97ff017619"
_DETAILS_HASH = "039277bf98f3130929262cc7c6efd9c141ca3749cb6dca442fc8ead9a53f77c1"
_DIRECTORY_HASH = "86bcceb4e8b1a51256ff8eed8bd8aae4acacf80d737efe904f84f3aeadf8cafd"
_REDIRECT_HASH = "1f0300090caceec51f33c5e20647aceff9017f740f223c3c532ba6fa59f6b6cc"


class InvalidTokenError(Exception):
    """Twitch rejected the OAuth token used for a GraphQL request."""


def _operation(name: str, digest: str, variables: dict[str, Any]) -> dict:
    return {
        "operationName": name,
        "extensions": {
            "persistedQuery": {"version": 1, "sha256Hash": digest}
        },
        "variables": variables,
    }


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "*/*",
        "Authorization": f"OAuth {token}",
        "Client-Id": CLIENT_ID,
        "Client-Session-Id": uuid.uuid4().hex[:16],
        "User-Agent": USER_AGENT,
        "X-Device-Id": uuid.uuid4().hex,
        "Origin": "https://www.twitch.tv",
        "Referer": "https://www.twitch.tv/",
    }


async def _post(
    session: aiohttp.ClientSession,
    token: str,
    operation: dict,
) -> dict:
    try:
        async with session.post(
            GQL_URL,
            json=[operation],
            headers=_headers(token),
            timeout=aiohttp.ClientTimeout(total=25),
        ) as response:
            if response.status == 401:
                raise InvalidTokenError
            if response.status >= 400:
                return {}
            payload = await response.json(content_type=None)
            payload = payload[0] if isinstance(payload, list) and payload else payload
            errors = payload.get("errors") if isinstance(payload, dict) else None
            if any(
                any(
                    marker in str(error.get("message", "")).lower()
                    for marker in (
                        "unauthorized",
                        "invalid token",
                        "token is invalid",
                        "invalid oauth",
                    )
                )
                for error in errors or []
                if isinstance(error, dict)
            ):
                raise InvalidTokenError
            return payload
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return {}


async def fetch_all_campaigns(
    token: str,
    session: aiohttp.ClientSession | None = None,
    login: str | None = None,
) -> list[dict]:
    """Fetch and normalize currently active Drops campaigns."""
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
    try:
        result = await _post(
            session,
            token,
            _operation(
                "ViewerDropsDashboard",
                _CAMPAIGNS_HASH,
                {"fetchRewardCampaigns": False},
            ),
        )
        current_user = (result.get("data") or {}).get("currentUser") or {}
        campaigns = []
        for campaign in current_user.get("dropCampaigns") or []:
            if campaign.get("status") != "ACTIVE":
                continue
            game = campaign.get("game") or {}
            campaigns.append(
                {
                    "id": str(campaign.get("id") or ""),
                    "name": campaign.get("name") or "",
                    "game_name": game.get("displayName") or "",
                    "game_slug": game.get("slug") or "",
                    "box_art": game.get("boxArtURL") or "",
                    "owner": (campaign.get("owner") or {}).get("name") or "",
                    "starts_at": campaign.get("startAt"),
                    "ends_at": campaign.get("endAt"),
                    "details_url": campaign.get("detailsURL") or "",
                    "account_link_url": campaign.get("accountLinkURL") or "",
                    "is_account_connected": bool(
                        (campaign.get("self") or {}).get("isAccountConnected")
                    ),
                }
            )
        campaigns = [item for item in campaigns if item["id"] and item["name"]]
        if login:
            await enrich_campaign_drops(token, login, campaigns, session=session)
        return campaigns
    except Exception:
        # Catalog refresh treats a bad/expired token as "no campaigns" and
        # falls through to the next candidate token; only the farm-start
        # resolve path needs the InvalidTokenError signal.
        return []
    finally:
        if own_session and session:
            await session.close()


async def _campaign_drops(
    token: str,
    login: str,
    campaign_id: str,
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    async with semaphore:
        result = await _post(
            session,
            token,
            _operation(
                "DropCampaignDetails",
                _DETAILS_HASH,
                {"channelLogin": login, "dropID": campaign_id},
            ),
        )
    drop_campaign = (
        ((result.get("data") or {}).get("user") or {}).get("dropCampaign")
        or {}
    )
    drops: list[dict] = []
    for drop in drop_campaign.get("timeBasedDrops") or []:
        required = int(drop.get("requiredMinutesWatched") or 0)
        for edge in drop.get("benefitEdges") or []:
            benefit = edge.get("benefit") or {}
            name = benefit.get("name") or drop.get("name") or ""
            if name:
                drops.append(
                    {
                        "name": name,
                        "image": benefit.get("imageAssetURL") or "",
                        "required_minutes": required,
                    }
                )
    return drops


async def enrich_campaign_drops(
    token: str,
    login: str,
    campaigns: list[dict],
    session: aiohttp.ClientSession | None = None,
) -> list[dict]:
    """Attach reward tiles without allowing individual failures to abort refresh."""
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
    semaphore = asyncio.Semaphore(8)
    try:
        tasks = [
            _campaign_drops(token, login, str(campaign["id"]), session, semaphore)
            for campaign in campaigns
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for campaign, result in zip(campaigns, results):
            campaign["drops"] = result if isinstance(result, list) else []
        return campaigns
    finally:
        if own_session and session:
            await session.close()


async def _game_slug(
    token: str,
    session: aiohttp.ClientSession,
    game_name: str,
    game_slug: str | None,
) -> str:
    if game_slug:
        return game_slug
    result = await _post(
        session,
        token,
        _operation("DirectoryGameRedirect", _REDIRECT_HASH, {"name": game_name}),
    )
    data = result.get("data") or {}
    game = data.get("game") or data.get("directoryGameRedirect") or {}
    slug = game.get("slug") if isinstance(game, dict) else None
    if slug:
        return slug
    return game_name.lower().replace(" ", "-").strip()


async def resolve_streamers(
    token: str,
    login: str,
    campaign_id: str,
    game_name: str,
    game_slug: str | None,
    max_channels: int = 30,
    session: aiohttp.ClientSession | None = None,
) -> list[str]:
    """Resolve campaign ACL channels, intersected with live game channels."""
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
    try:
        details = await _post(
            session,
            token,
            _operation(
                "DropCampaignDetails",
                _DETAILS_HASH,
                {"channelLogin": login, "dropID": campaign_id},
            ),
        )
        drop_campaign = (
            ((details.get("data") or {}).get("user") or {}).get("dropCampaign")
            or {}
        )
        acl = [
            str(channel.get("login") or "").lower()
            for channel in ((drop_campaign.get("allow") or {}).get("channels") or [])
        ]
        acl = list(dict.fromkeys(item for item in acl if item))[:max_channels]

        slug = await _game_slug(token, session, game_name, game_slug)
        directory = await _post(
            session,
            token,
            _operation(
                "DirectoryPage_Game",
                _DIRECTORY_HASH,
                {
                    "limit": max_channels,
                    "slug": slug,
                    "imageWidth": 50,
                    "includeCostreaming": False,
                    "options": {
                        "broadcasterLanguages": [],
                        "freeformTags": None,
                        "includeRestricted": ["SUB_ONLY_LIVE"],
                        "recommendationsContext": {"platform": "web"},
                        "sort": "RELEVANCE",
                        "systemFilters": [],
                        "tags": [],
                        "requestID": "JIRA-VXP-2397",
                    },
                    "sortTypeIsRecency": False,
                },
            ),
        )
        edges = (
            (((directory.get("data") or {}).get("game") or {}).get("streams") or {})
            .get("edges")
            or []
        )
        live = [
            str(
                ((edge.get("node") or {}).get("broadcaster") or {}).get("login")
                or ""
            ).lower()
            for edge in edges
        ]
        live = list(dict.fromkeys(item for item in live if item))
        if acl:
            intersection = [item for item in live if item in set(acl)]
            return (intersection or acl)[:max_channels]
        return live[:max_channels]
    except InvalidTokenError:
        raise
    except Exception:
        return []
    finally:
        if own_session and session:
            await session.close()


def load_catalog() -> dict:
    try:
        payload = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {
                "fetched_at": float(payload.get("fetched_at") or 0),
                "campaigns": payload.get("campaigns")
                if isinstance(payload.get("campaigns"), list)
                else [],
            }
    except (OSError, ValueError, TypeError):
        pass
    return {"fetched_at": 0, "campaigns": []}


def save_catalog(campaign_list: list[dict]) -> dict:
    payload = {"fetched_at": time.time(), "campaigns": campaign_list}
    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CATALOG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CATALOG_FILE)
    return payload
