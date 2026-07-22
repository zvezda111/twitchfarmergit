#!/usr/bin/env python3
"""
Скрипт-копия API-пути проекта: клеймит дроп ТАК ЖЕ, как _claim_drop_api в
client.py — Android client-id, те же заголовки _gql_request, БЕЗ Client-Integrity.
 
Это ровно то, что делает автоклейм в цикле фарма. Скрипт нужен, чтобы вживую
проверить, проходит ли такой клейм или упирается в IntegrityCheckFailed.
 
Порядок работы:
  1. Валидирует OAuth токен.
  2. Генерирует device_id/session_id так же, как client.py (случайно).
  3. Читает инвентарь, находит первый готовый к клейму дроп (есть dropInstanceID,
     не заклеймлен) — или берёт --instance.
  4. Шлёт мутацию DropsPage_ClaimDropRewards теми же заголовками, что _gql_request.
 
Запуск:
    python claim_drop_api.py --token <OAuth-токен> [--instance <dropInstanceID>]
"""
import argparse
import asyncio
import json
import secrets
import string
 
import aiohttp
 
# Ровно как в client.py
GQL_URL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kd1unb4b3q4t58fwlpcbzcbnm76a8fp"
USER_AGENT = (
    "Dalvik/2.1.0 (Linux; U; Android 13; SM-G991B Build/TP1A.220624.014) "
    "tv.twitch.android.app/29.9.1/2909016"
)
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
 
INVENTORY_HASH = "d86775d0ef16a63a33ad52e80eaff963b2d5b72fada7c991504a57496e1d8e4b"
CLAIM_HASH = "a455deea71bdc9015b78eb49f4acfbce8baa7ccbedd28e549bb025bd0f751930"
 
 
def gql_headers(token, device_id, session_id):
    # Тот же набор заголовков, что и _gql_request в client.py (без Client-Integrity).
    return {
        "Accept": "*/*",
        "Accept-Language": "en-US",
        "Authorization": f"OAuth {token}",
        "Client-Id": CLIENT_ID,
        "Client-Session-Id": session_id,
        "User-Agent": USER_AGENT,
        "X-Device-Id": device_id,
        "Origin": "https://www.twitch.tv",
        "Referer": "https://www.twitch.tv/",
    }
 
 
async def gql(session, token, device_id, session_id, operation, integrity=None):
    headers = gql_headers(token, device_id, session_id)
    if integrity is not None:
        headers["Client-Integrity"] = integrity
    async with session.post(
        GQL_URL, json=[operation], headers=headers
    ) as r:
        status = r.status
        data = await r.json()
        if isinstance(data, list):
            data = data[0]
        return status, data
 
 
async def find_claimable(session, token, device_id, session_id):
    op = {
        "operationName": "Inventory",
        "variables": {"fetchRewardCampaigns": True},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": INVENTORY_HASH}},
    }
    _, data = await gql(session, token, device_id, session_id, op)
    cur = (data.get("data") or {}).get("currentUser") or {}
    prog = (cur.get("inventory") or {}).get("dropCampaignsInProgress") or []
    for c in prog:
        for drop in c.get("timeBasedDrops") or []:
            self_edge = drop.get("self") or {}
            iid = self_edge.get("dropInstanceID")
            if iid and not self_edge.get("isClaimed"):
                return drop.get("name"), iid
    return None, None
 
 
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", help="OAuth токен аккаунта")
    ap.add_argument("--instance", help="dropInstanceID (если не задан — найдётся сам)")
    args = ap.parse_args()
 
    token = args.token or input("OAuth токен: ").strip()
 
    # X-Device-Id вписывается вручную; если оставить пустым — сгенерируется как в client.py
    device_id = input("X-Device-Id (Enter — сгенерировать случайный): ").strip()
    if not device_id:
        device_id = "".join(secrets.choice(string.hexdigits.lower()) for _ in range(32))
    session_id = "".join(secrets.choice(string.hexdigits.lower()) for _ in range(16))
    session_id = input(f"Client-Session-Id (Enter — сгенерировать случайный): [{session_id}] ").strip() or session_id
    integrity = input("Client-Integrity (Enter — пустой): ").strip()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            VALIDATE_URL, headers={"Authorization": f"OAuth {token}"}
        ) as r:
            if r.status != 200:
                print(f"Токен невалиден (HTTP {r.status}) — прекращаю.")
                return
            login = (await r.json()).get("login")
        print(f"Аккаунт: {login}")
        print(f"X-Device-Id: {device_id}")
 
        instance_id = args.instance
        name = "(указан вручную)"
        if not instance_id:
            print("\n[1] Ищу готовый к клейму дроп...")
            name, instance_id = await find_claimable(session, token, device_id, session_id)
            if not instance_id:
                print("Готовых к клейму дропов нет — прекращаю.")
                return
        print(f"Клеймлю дроп: {name}\n  dropInstanceID={instance_id}")
 
        print("\n[2] Отправляю клейм (API-путь, без Client-Integrity)...")
        op = {
            "operationName": "DropsPage_ClaimDropRewards",
            "variables": {"input": {"dropInstanceID": instance_id}},
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": CLAIM_HASH}},
        }
        status, result = await gql(session, token, device_id, session_id, op)
        print(f"HTTP {status}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        node = result if isinstance(result, dict) else {}
        claim = (node.get("data") or {}).get("claimDropRewards")
        if claim and claim.get("status") in ("ELIGIBLE_FOR_ALL", "DROP_INSTANCE_ALREADY_CLAIMED"):
            print(f"\nУСПЕХ: дроп заклеймлен (status={claim.get('status')}).")
        else:
            print("\nНЕ УДАЛОСЬ (см. ответ выше).")
 
 
if __name__ == "__main__":
    asyncio.run(main())
 