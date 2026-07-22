"""Бэкапы пользователей и подписок панели в Telegram-бота.

Настройка через переменные окружения (секреты НЕ хардкодятся):
    TELEGRAM_BOT_TOKEN   — токен бота от @BotFather
    TELEGRAM_CHAT_ID     — id чата/канала, куда слать бэкапы
    PANEL_BACKUP_INTERVAL_HOURS  — период авто-бэкапа (по умолчанию 6, 0 = выкл.)
    PANEL_BACKUP_INCLUDE_ACCOUNTS — "1" чтобы приложить и data/accounts.json

Если токен/чат не заданы — бэкапы просто отключены (ошибки не бросаются).
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp
from loguru import logger

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
INTERVAL_HOURS = float(os.getenv("PANEL_BACKUP_INTERVAL_HOURS", "6") or 0)
INCLUDE_ACCOUNTS = os.getenv("PANEL_BACKUP_INCLUDE_ACCOUNTS", "0") in (
    "1", "true", "True",
)


def is_configured() -> bool:
    return bool(BOT_TOKEN and CHAT_ID)


async def _send_document(
    session: aiohttp.ClientSession, filename: str, content: bytes, caption: str
) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    form = aiohttp.FormData()
    form.add_field("chat_id", CHAT_ID)
    form.add_field("caption", caption[:1024])
    form.add_field(
        "document", content, filename=filename, content_type="application/json"
    )
    async with session.post(url, data=form) as resp:
        if resp.status != 200:
            body = await resp.text()
            logger.warning(f"telegram backup failed: {resp.status} {body[:200]}")
            return False
        return True


async def send_backup(
    store, reason: str = "manual", include_accounts: Optional[bool] = None
) -> dict:
    """Отправить бэкап пользователей/подписок в Telegram.

    ``store`` — экземпляр AuthStore (даёт export_backup()).
    Возвращает {"ok": bool, "reason": str, "detail": str}.
    """
    if not is_configured():
        return {
            "ok": False,
            "reason": reason,
            "detail": "telegram not configured (set TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)",
        }

    payload = store.export_backup()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    caption = (
        f"Panel backup ({reason})\n"
        f"users: {payload.get('user_count', 0)}\n"
        f"time: {payload.get('generated_at', '')}"
    )
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    inc = INCLUDE_ACCOUNTS if include_accounts is None else include_accounts
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            ok = await _send_document(
                session, f"panel-users-{ts}.json", content, caption
            )
            if inc:
                import json as _json

                bundle: dict[str, object] = {}
                # аккаунты каждого пользователя изолированы в data/users/<uid>/
                for acc_path in sorted(Path("data/users").glob("*/accounts.json")):
                    uid = acc_path.parent.name
                    try:
                        bundle[uid] = _json.loads(
                            acc_path.read_text(encoding="utf-8")
                        )
                    except Exception:
                        continue
                # legacy-файл (до миграции), если ещё есть
                legacy = Path("data/accounts.json")
                if legacy.exists():
                    try:
                        bundle["legacy"] = _json.loads(
                            legacy.read_text(encoding="utf-8")
                        )
                    except Exception:
                        pass
                if bundle:
                    await _send_document(
                        session,
                        f"accounts-{ts}.json",
                        _json.dumps(bundle, ensure_ascii=False, indent=2).encode(
                            "utf-8"
                        ),
                        f"Twitch accounts backup ({reason})",
                    )
        return {"ok": ok, "reason": reason, "detail": "sent" if ok else "send failed"}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"telegram backup error: {e!r}")
        return {"ok": False, "reason": reason, "detail": str(e)}


async def backup_scheduler(store) -> None:
    """Фоновая задача: периодический авто-бэкап."""
    if not is_configured() or INTERVAL_HOURS <= 0:
        logger.info(
            "telegram backup scheduler disabled "
            "(not configured or interval<=0)"
        )
        return
    interval = INTERVAL_HOURS * 3600
    logger.info(f"telegram backup scheduler started (every {INTERVAL_HOURS}h)")
    while True:
        try:
            await asyncio.sleep(interval)
            await send_backup(store, reason="scheduled")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"scheduled backup error: {e!r}")
