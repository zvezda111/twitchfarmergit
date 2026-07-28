"""Открывает Twitch /drops/inventory в том же браузере, что и клейм.

Ничего не кликает — только логинит по токену и держит окно открытым,
чтобы вручную проверить, что видит аккаунт (и работает ли прокси).

Заполни TOKEN и PROXY ниже (PROXY можно оставить пустым) и запусти:

    cd /root/twitch-farmer
    xvfb-run -a ./venv/bin/python open_inventory.py

Аргументами тоже можно:
    ./venv/bin/python open_inventory.py <token> host:port:user:pass
"""

import asyncio
import sys

from patchright.async_api import async_playwright

# ---- заполнить ----------------------------------------------------------
TOKEN = ""
# формат: host:port:user:pass  (или "host:port" без авторизации, или "")
PROXY = ""
# -------------------------------------------------------------------------

URL = "https://www.twitch.tv/drops/inventory"


def parse_proxy(raw: str) -> dict | None:
    raw = raw.strip()
    if not raw:
        return None
    parts = raw.split(":", 3)
    if len(parts) < 2:
        raise SystemExit(f"не понял прокси: {raw}")
    host, port = parts[0], parts[1]
    cfg = {"server": f"http://{host}:{port}"}
    if len(parts) == 4:
        cfg["username"], cfg["password"] = parts[2], parts[3]
    return cfg


async def main() -> None:
    token = (sys.argv[1] if len(sys.argv) > 1 else TOKEN).strip()
    proxy = parse_proxy(sys.argv[2] if len(sys.argv) > 2 else PROXY)
    if not token:
        raise SystemExit("укажи TOKEN в файле или первым аргументом")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(**({"proxy": proxy} if proxy else {}))
        await context.add_cookies([{
            "name": "auth-token", "value": token,
            "domain": ".twitch.tv", "path": "/",
        }])
        page = await context.new_page()

        def on_claim_response(response):
            if "gql.twitch.tv" not in response.url:
                return

            async def report():
                try:
                    body = await response.json()
                except Exception:
                    return
                for item in (body if isinstance(body, list) else [body]):
                    if not isinstance(item, dict):
                        continue
                    op = (item.get("extensions") or {}).get("operationName")
                    if op != "DropsPage_ClaimDropRewards":
                        continue
                    errors = item.get("errors")
                    status = (
                        (item.get("data") or {}).get("claimDropRewards") or {}
                    ).get("status")
                    print(f"CLAIM: status={status} errors={errors}")

            asyncio.create_task(report())

        page.on("response", on_claim_response)

        if proxy:
            await page.goto("https://api.ipify.org?format=json", timeout=120000)
            print("IP:", (await page.inner_text("body")).strip())

        await page.goto(URL, timeout=120000)
        await asyncio.sleep(8)
        buttons = page.locator(
            'button:has-text("Получить сейчас"), button:has-text("Claim Now")'
        )
        print("кнопок клейма на странице:", await buttons.count())
        print("браузер открыт, Ctrl+C чтобы закрыть")

        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
