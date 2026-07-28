"""Launch the exact same browser the converter (convert_worker.py) uses.

patchright (stealth Playwright fork) -> system Google Chrome (channel="chrome"),
headful, with the same launch args. Keeps the browser open until you press
Enter / Ctrl+C so you can use it interactively.

Run it under a display. On the headless server use xvfb-run:
    cd /root/twitch-farmer
    xvfb-run -a ./venv/bin/python launch_browser.py
"""

import asyncio

from patchright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel="chrome",              # system Google Chrome, same as converter
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.twitch.tv/")

        print("Browser is open. Press Ctrl+C to close.")
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
