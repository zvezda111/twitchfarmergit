"""Isolated Twitch farming worker process."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from queue import Full
from typing import Any

from client import TwitchMiner
from config import MinerConfig
from loguru import logger


def _put(event_queue: Any, event: dict) -> None:
    try:
        event_queue.put_nowait(event)
    except (Full, OSError, EOFError):
        pass


def _log_sink(message: Any, event_queue: Any) -> None:
    record = message.record
    owner = record["extra"].get("owner")
    if owner is None:
        return
    text = record["message"]
    if "<!DOCTYPE" in text or "<html" in text or "<script" in text:
        return
    if len(text) > 500:
        text = text[:500] + "..."
    _put(
        event_queue,
        {
            "type": "log",
            "login": record["extra"].get("login") or "account",
            "level": record["level"].name.lower(),
            "message": text,
        },
    )


async def _publish_cards(
    miners: dict[str, TwitchMiner], event_queue: Any
) -> None:
    while True:
        for login, miner in miners.items():
            _put(
                event_queue,
                {
                    "type": "card",
                    "login": login,
                    "current_game": miner.current_game,
                    "watch_minutes": miner.watch_minutes,
                },
            )
        await asyncio.sleep(1)


async def _run_worker(
    owner_id: int,
    accounts: list[dict],
    proxies: list[dict],
    claim_proxies: list[dict],
    streamers: list[str],
    config_values: dict[str, Any],
    event_queue: Any,
    stagger: float,
) -> None:
    tokens = [account["token"] for account in accounts]
    config = MinerConfig(
        tokens=tokens,
        data_dir=Path(config_values["data_dir"]),
    )
    config.streamers = list(streamers)
    for key, value in config_values.items():
        if key != "data_dir" and hasattr(config, key):
            setattr(config, key, value)

    miners: dict[str, TwitchMiner] = {}
    for index, account in enumerate(accounts):
        login = account.get("login") or f"account_{index}"
        proxy = proxies[index % len(proxies)] if proxies else None
        claim_proxy = (
            claim_proxies[index % len(claim_proxies)]
            if claim_proxies else None
        )
        miners[login] = TwitchMiner(
            account["token"],
            index + 1,
            config,
            proxy=proxy,
            claim_proxy=claim_proxy,
            owner=owner_id,
            login=login,
        )

    publisher = asyncio.create_task(_publish_cards(miners, event_queue))
    tasks: list[asyncio.Task] = []
    try:
        for index, (login, miner) in enumerate(miners.items()):
            _put(
                event_queue,
                {
                    "type": "log",
                    "login": "system",
                    "level": "info",
                    "message": f"starting miner for {login} ({index + 1}/{len(miners)})",
                },
            )
            tasks.append(asyncio.create_task(miner.run()))
            if stagger and index < len(miners) - 1:
                await asyncio.sleep(stagger)
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        publisher.cancel()
        await asyncio.gather(publisher, return_exceptions=True)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for miner in miners.values():
            try:
                await asyncio.wait_for(miner.shutdown(), timeout=5)
            except Exception:
                pass


def run_worker(
    owner_id: int,
    accounts: list[dict],
    proxies: list[dict],
    claim_proxies: list[dict],
    streamers: list[str],
    config_values: dict[str, Any],
    event_queue: Any,
    stagger: float,
) -> None:
    """Multiprocessing target; all arguments are spawn/pickle compatible."""
    # Become session/group leader so the panel can reap this worker AND every
    # process it spawns (browsers etc.) in one os.killpg on stop.
    try:
        os.setsid()
    except OSError:
        pass
    logger.remove()
    logger.add(
        lambda message: _log_sink(message, event_queue),
        level="INFO",
        format="{message}",
        filter=lambda record: record["extra"].get("owner") is not None,
    )
    try:
        asyncio.run(
            _run_worker(
                owner_id,
                accounts,
                proxies,
                claim_proxies,
                streamers,
                config_values,
                event_queue,
                stagger,
            )
        )
    except BaseException as exc:
        _put(
            event_queue,
            {
                "type": "log",
                "login": "system",
                "level": "error",
                "message": f"worker stopped: {type(exc).__name__}",
            },
        )
    finally:
        try:
            event_queue.cancel_join_thread()
        except Exception:
            pass
