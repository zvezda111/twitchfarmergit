#!/usr/bin/env python3
"""
Скрипт-копия старого test() + _gql_request_claim_drop.

Поведение 1-в-1 со старой версией:
  - читает инвентарь;
  - для каждого дропа печатает name / id / claim_id / can_claim / is_claimed;
  - если у дропа есть claim_id — спрашивает в консоли token и device_id
    и шлёт мутацию DropsPage_ClaimDropRewards БЕЗ Client-Integrity.

ВАЖНО (как в оригинале): в заголовке Authorization используется основной
OAuth-токен аккаунта (--token), а введённый в консоли 'token' — как и в старом
коде — по сути игнорируется (оставлен для идентичности). Реально влияет device_id.

Запуск:
    python claim_drop_test.py --token <OAuth-токен-аккаунта>
"""
import argparse
import asyncio
import secrets
import string

import aiohttp

GQL_URL = "https://gql.twitch.tv/gql"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
CLIENT_ID = "kd1unb4b3q4t58fwlpcbzcbnm76a8fp"
USER_AGENT = (
    "Dalvik/2.1.0 (Linux; U; Android 13; SM-G991B Build/TP1A.220624.014) "
    "tv.twitch.android.app/29.9.1/2909016"
)
INVENTORY_HASH = "d86775d0ef16a63a33ad52e80eaff963b2d5b72fada7c991504a57496e1d8e4b"
CLAIM_HASH = "a455deea71bdc9015b78eb49f4acfbce8baa7ccbedd28e549bb025bd0f751930"


class MiniMiner:
    def __init__(self, access_token, session):
        self.access_token = access_token
        self.session = session
        self.session_id = "".join(secrets.choice(string.hexdigits.lower()) for _ in range(16))
        self.device_id = "".join(secrets.choice(string.hexdigits.lower()) for _ in range(32))
        self.active_drops = {}

    async def _gql_request(self, operation: dict) -> dict:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US",
            "Authorization": f"OAuth {self.access_token}",
            "Client-Id": CLIENT_ID,
            "Client-Session-Id": self.session_id,
            "User-Agent": USER_AGENT,
            "X-Device-Id": self.device_id,
            "Origin": "https://www.twitch.tv",
            "Referer": "https://www.twitch.tv/",
        }
        async with self.session.post(GQL_URL, json=[operation], headers=headers) as r:
            data = await r.json()
            if isinstance(data, list):
                data = data[0]
            return data

    async def fetch_inventory(self):
        op = {
            "operationName": "Inventory",
            "variables": {"fetchRewardCampaigns": True},
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": INVENTORY_HASH}},
        }
        data = await self._gql_request(op)
        cur = (data.get("data") or {}).get("currentUser") or {}
        prog = (cur.get("inventory") or {}).get("dropCampaignsInProgress") or []
        for c in prog:
            for d in c.get("timeBasedDrops") or []:
                se = d.get("self") or {}
                drop = type("Drop", (), {})()
                drop.name = d.get("name")
                drop.id = d.get("id")
                drop.claim_id = se.get("dropInstanceID")
                drop.required_minutes = d.get("requiredMinutesWatched", 0)
                drop.current_minutes = se.get("currentMinutesWatched", 0) or 0
                drop.is_claimed = se.get("isClaimed", False)
                drop.can_claim = (
                    not drop.is_claimed
                    and drop.current_minutes >= drop.required_minutes
                    and drop.claim_id is not None
                )
                self.active_drops[drop.id] = drop

    async def _gql_request_claim_drop(self, operation: dict, token, device_id) -> dict:
        headers = {
            "Accept": "*/*",
            "Authorization": f"OAuth {self.access_token}",
            "Client-Id": CLIENT_ID,
            "Client-Session-Id": self.session_id,
            "User-Agent": USER_AGENT,
            "X-Device-Id": device_id,
            "Origin": "https://www.twitch.tv",
            "Referer": "https://www.twitch.tv/",
        }
        async with self.session.post(GQL_URL, json=[operation], headers=headers) as response:
            response.raise_for_status()
            data = await response.json()
            if isinstance(data, list):
                data = data[0]
            if "errors" in data:
                print(data)
            return data

    async def test(self):
        await self.fetch_inventory()
        for drop_id, drop in self.active_drops.items():
            print(f"Дроп: {drop.name}")
            print(f"  ID: {drop.id}")
            print(f"  claim_id: {drop.claim_id}")
            print(f"  can_claim: {drop.can_claim}")
            print(f"  is_claimed: {drop.is_claimed}")
            print("-" * 50)
            operation = {
                "operationName": "DropsPage_ClaimDropRewards",
                "variables": {"input": {"dropInstanceID": drop.claim_id}},
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": CLAIM_HASH,
                    }
                },
            }
            if drop.claim_id:
                token = input("token: ")
                di = input("device_id: ")
                result = await self._gql_request_claim_drop(operation, token, di)
                print(result)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", help="OAuth токен аккаунта")
    args = ap.parse_args()
    access_token = args.token or input("OAuth токен: ").strip()

    async with aiohttp.ClientSession() as session:
        async with session.get(
            VALIDATE_URL, headers={"Authorization": f"OAuth {access_token}"}
        ) as r:
            if r.status != 200:
                print(f"Токен невалиден (HTTP {r.status}) — прекращаю.")
                return
            login = (await r.json()).get("login")
        print(f"Аккаунт: {login}\n")

        miner = MiniMiner(access_token, session)
        await miner.test()


if __name__ == "__main__":
    asyncio.run(main())
