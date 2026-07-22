"""Isolated browser worker for web-to-mobile Twitch token conversion."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Full
from typing import Any
from urllib.parse import quote

import aiohttp

ANDROID_CLIENT_ID = "kd1unb4b3q4t58fwlpcbzcbnm76a8fp"
DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
SCOPES = (
    "channel_read chat:read user_blocks_edit user_blocks_read "
    "user_follows_edit user_read"
)


def _put(event_queue: Any, event: dict) -> None:
    try:
        event_queue.put_nowait(event)
    except (Full, OSError, EOFError):
        pass


def _proxy_url(proxy: dict | None) -> str | None:
    if not proxy:
        return None
    scheme = (proxy.get("scheme") or "http").lower()
    host = proxy.get("host")
    port = proxy.get("port")
    if not host or not port or scheme.startswith("socks"):
        return None
    username = proxy.get("username") or ""
    password = proxy.get("password") or ""
    auth = (
        f"{quote(str(username), safe='')}:{quote(str(password), safe='')}@"
        if username else ""
    )
    return f"{scheme}://{auth}{host}:{port}"


def _browser_proxy(proxy: dict | None) -> dict | None:
    """Playwright proxy dict: creds go in separate keys, not the server URL."""
    if not proxy:
        return None
    scheme = (proxy.get("scheme") or "http").lower()
    host = proxy.get("host")
    port = proxy.get("port")
    if not host or not port or scheme.startswith("socks"):
        return None
    result = {"server": f"{scheme}://{host}:{port}"}
    username = proxy.get("username") or ""
    if username:
        result["username"] = str(username)
        result["password"] = str(proxy.get("password") or "")
    return result


def _approval_timeout_ms() -> int:
    try:
        value = int(os.getenv("CONVERT_APPROVE_TIMEOUT_MS", "35000"))
    except ValueError:
        value = 35000
    return max(5000, min(value, 180000))


async def _validate(session: aiohttp.ClientSession, token: str) -> bool:
    try:
        async with session.get(
            VALIDATE_URL, headers={"Authorization": f"OAuth {token}"}
        ) as response:
            if response.status != 200:
                return False
            payload = await response.json()
            return payload.get("client_id") == ANDROID_CLIENT_ID
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return False


async def _convert_one(
    browser: Any,
    account: dict,
    proxy: dict | None,
    event_queue: Any,
    debug_dir: str | Path | None,
) -> dict:
    login = account.get("login") or ""
    timeout = "timeout"
    device_code = ""
    user_code = ""
    proxy_value = _proxy_url(proxy)
    page = None
    page_html: str | None = None
    page_png: bytes | None = None
    page_url = ""
    page_title = ""
    browser_stage_ran = False

    def debug_dump(status: str, reason: str | None = None) -> None:
        if not browser_stage_ran or not debug_dir:
            return
        try:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            safe_login = re.sub(r"[^A-Za-z0-9_.-]+", "_", login) or "unknown"
            base = Path(debug_dir) / f"{safe_login}_{stamp}_{status}"
            Path(debug_dir).mkdir(parents=True, exist_ok=True)
            metadata = {
                "login": login,
                "timestamp": stamp,
                "status": status,
                "reason": reason or "",
                "url": page_url,
                "title": page_title,
            }
            try:
                (base.with_suffix(".json")).write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            if page_html is not None:
                try:
                    base.with_suffix(".html").write_text(
                        page_html, encoding="utf-8"
                    )
                except Exception:
                    pass
            if page_png is not None:
                try:
                    base.with_suffix(".png").write_bytes(page_png)
                except Exception:
                    pass
        except Exception:
            pass

    def result(status: str, reason: str | None = None) -> dict:
        payload = {
            "type": "convert_result",
            "login": login,
            "status": status,
        }
        if reason:
            payload["reason"] = reason
        return payload

    def finalized(status: str, reason: str | None = None) -> dict:
        debug_dump(status, reason)
        return result(status, reason)

    try:
        request_kwargs = {"proxy": proxy_value} if proxy_value else {}
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=25)
        ) as session:
            async with session.post(
                DEVICE_URL,
                data={"client_id": ANDROID_CLIENT_ID, "scopes": SCOPES},
                **request_kwargs,
            ) as response:
                device = await response.json()
                if response.status != 200:
                    return result("error", "flow")
                device_code = device.get("device_code") or ""
                user_code = device.get("user_code") or ""
                if not device_code or not user_code:
                    return result("error", "flow")
                _put(
                    event_queue,
                    {
                        "type": "convert_log",
                        "login": login,
                        "stage": "auth_started",
                    },
                )

        browser_proxy = _browser_proxy(proxy)
        context_options = {"proxy": browser_proxy} if browser_proxy else {}
        context = await browser.new_context(**context_options)
        browser_stage_ran = True
        browser_result = None
        try:
            approval_timeout_ms = _approval_timeout_ms()

            async def wait_for_button(labels: tuple[str, ...]) -> Any:
                deadline = time.monotonic() + approval_timeout_ms / 1000
                while time.monotonic() < deadline:
                    remaining = max(
                        100, int((deadline - time.monotonic()) * 1000)
                    )
                    for label in labels:
                        try:
                            button = page.get_by_role(
                                "button", name=label, exact=False
                            ).first
                            await button.wait_for(
                                state="visible",
                                timeout=min(1000, remaining),
                            )
                            return button
                        except Exception:
                            pass
                    await asyncio.sleep(0.25)
                return None

            async def settle_page() -> None:
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=approval_timeout_ms
                    )
                except Exception:
                    pass

            await context.add_cookies(
                [{"name": "auth-token", "value": account.get("token", ""),
                  "domain": ".twitch.tv", "path": "/"}]
            )
            page = await context.new_page()
            await page.goto(
                f"https://www.twitch.tv/activate?device-code={user_code}",
                wait_until="domcontentloaded",
                timeout=max(90000, approval_timeout_ms * 2),
            )
            await settle_page()
            accept = await wait_for_button(
                ("Принять", "Отклонить", "Accept", "Reject")
            )
            if accept is None:
                try:
                    body = (await page.content()).lower()
                except Exception:
                    body = ""
                if "loading authorization" in body:
                    try:
                        await page.reload(
                            wait_until="domcontentloaded",
                            timeout=max(90000, approval_timeout_ms * 2),
                        )
                    except Exception:
                        pass
                    await settle_page()
                    accept = await wait_for_button(
                        ("Принять", "Отклонить", "Accept", "Reject")
                    )
            if accept is not None:
                try:
                    await accept.click(timeout=5000)
                except Exception:
                    pass
            activate = await wait_for_button(("Activate", "Активировать"))
            if activate is not None:
                try:
                    await activate.click(timeout=5000)
                except Exception:
                    pass
            password = page.locator("input[type=password]").first
            try:
                await password.wait_for(
                    state="visible", timeout=approval_timeout_ms
                )
                await password.fill(account.get("password", ""))
                verify = await wait_for_button(
                    ("Verify", "Confirm", "Подтвердить")
                )
                if verify is not None:
                    try:
                        await verify.click(timeout=5000)
                    except Exception:
                        pass
                await settle_page()
                body = (await page.content()).lower()
                if "password was incorrect" in body or "неверн" in body:
                    browser_result = result("bad_password")
                else:
                    has_code_text = any(
                        phrase in body
                        for phrase in (
                            "6-значный код",
                            "6-digit code",
                            "verification code",
                            "enter the code",
                            "введите код",
                        )
                    )
                    if has_code_text:
                        browser_result = result("2fa")
            except Exception:
                pass
            if browser_result is None:
                authorize = await wait_for_button(
                    (
                        "Принять", "Authorize", "Allow", "Continue",
                        "Разрешить", "Продолжить",
                    )
                )
                if authorize is not None:
                    try:
                        await authorize.click(timeout=5000)
                    except Exception:
                        pass
        finally:
            if page is not None:
                try:
                    page_html = await page.content()
                except Exception:
                    pass
                try:
                    page_png = await page.screenshot()
                except Exception:
                    pass
                try:
                    page_url = page.url or ""
                except Exception:
                    pass
                try:
                    page_title = await page.title()
                except Exception:
                    pass
            await context.close()

        if browser_result is not None:
            debug_dump(
                browser_result.get("status", "error"),
                browser_result.get("reason"),
            )
            return browser_result

        _put(
            event_queue,
            {
                "type": "convert_log",
                "login": login,
                "stage": "authorization_received",
            },
        )
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=25)
        ) as session:
            for _ in range(10):
                request_kwargs = {"proxy": proxy_value} if proxy_value else {}
                async with session.post(
                    TOKEN_URL,
                    data={
                        "client_id": ANDROID_CLIENT_ID,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    **request_kwargs,
                ) as response:
                    payload = await response.json()
                if response.status == 200 and payload.get("access_token"):
                    token = payload["access_token"]
                    if await _validate(session, token):
                        _put(
                            event_queue,
                            {
                                "type": "convert_log",
                                "login": login,
                                "stage": "token_received",
                            },
                        )
                        return {
                            "type": "convert_result",
                            "login": login,
                            "status": "minted",
                            "new_token": token,
                        }
                    return finalized("error", "flow")
                await asyncio.sleep(5)
        return finalized(timeout, "flow")
    except asyncio.CancelledError:
        raise
    except (aiohttp.ClientHttpProxyError, aiohttp.ClientProxyConnectionError):
        return finalized("error", "proxy")
    except (aiohttp.ClientError, asyncio.TimeoutError, socket.error, OSError):
        return finalized("error", "network")
    except Exception:
        return finalized("error", "flow")


async def _run(
    accounts: list[dict],
    proxies: list[dict],
    event_queue: Any,
    concurrency: int | None,
    debug_dir: str | Path | None,
) -> None:
    from patchright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        if concurrency is None:
            try:
                concurrency = int(os.getenv("CONVERT_CONCURRENCY", "3"))
            except ValueError:
                concurrency = 3
        semaphore = asyncio.Semaphore(max(1, min(int(concurrency), 32)))
        results = {
            "minted": 0,
            "bad_password": 0,
            "2fa": 0,
            "timeout": 0,
            "error": 0,
        }

        async def convert(index: int, account: dict) -> None:
            async with semaphore:
                proxy = proxies[index % len(proxies)] if proxies else None
                event = await _convert_one(
                    browser, account, proxy, event_queue, debug_dir
                )
                status = event.get("status", "error")
                results[status] = results.get(status, 0) + 1
                _put(event_queue, event)
                _put(
                    event_queue,
                    {
                        "type": "convert_progress",
                        "done": sum(results.values()),
                        "total": len(accounts),
                    },
                )

        await asyncio.gather(
            *(convert(index, account) for index, account in enumerate(accounts))
        )
        await browser.close()
        _put(event_queue, {"type": "convert_done", **results})


def run_convert_worker(
    accounts: list[dict],
    proxies: list[dict],
    event_queue: Any,
    concurrency: int | None,
    debug_dir: str | Path | None,
) -> None:
    try:
        os.setsid()
    except OSError:
        pass
    try:
        asyncio.run(
            _run(accounts, proxies, event_queue, concurrency, debug_dir)
        )
    except BaseException:
        _put(
            event_queue,
            {
                "type": "convert_done",
                "minted": 0,
                "bad_password": 0,
                "timeout": 0,
                "error": len(accounts),
            },
        )
    finally:
        try:
            event_queue.cancel_join_thread()
        except Exception:
            pass
