import json
import asyncio
import time
import aiohttp
import re
import gzip
import secrets
import string
from typing import Optional
from datetime import datetime, timezone, timedelta
from collections import OrderedDict
import portalocker
import os
from urllib.parse import quote
from loguru import logger

from config import MinerConfig
from models import Game, Campaign, Drop, Channel
from ws import WebsocketClient



try:
    from patchright.async_api import async_playwright
    BROWSER_AVAILABLE = True
except ImportError:
    BROWSER_AVAILABLE = False


# Одновременных браузерных клеймов на процесс — чтобы сервер не лёг.
BROWSER_CLAIM_CONCURRENCY = int(os.getenv("BROWSER_CLAIM_CONCURRENCY", "3"))
# headless по умолчанию (для Linux-сервера без монитора); отключить: BROWSER_HEADLESS=false
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "true").lower() not in ("0", "false", "no")
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "chrome").strip()

_browser_claim_semaphore: Optional["asyncio.Semaphore"] = None


def _get_browser_semaphore() -> "asyncio.Semaphore":
    """Лениво создаёт семафор в текущем event loop."""
    global _browser_claim_semaphore
    if _browser_claim_semaphore is None:
        _browser_claim_semaphore = asyncio.Semaphore(max(1, BROWSER_CLAIM_CONCURRENCY))
    return _browser_claim_semaphore


class TwitchMiner:
    
    GQL_URL = "https://gql.twitch.tv/gql"
    VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
    # Android-клиент (как в рабочем DevilXD/TwitchDropsMiner): мобильный
    # OAuth-токен консистентен только с android Client-Id и android User-Agent.
    # integrity/Kasada для этого пути не нужны.
    CLIENT_ID = "kd1unb4b3q4t58fwlpcbzcbnm76a8fp"
    USER_AGENT = (
        "Dalvik/2.1.0 (Linux; U; Android 13; SM-G991B Build/TP1A.220624.014) "
        "tv.twitch.android.app/29.9.1/2909016"
    )
    WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
    WEB_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    # Twitch убрал data-a-target у подписи кнопки, поэтому ищем по тексту
    CLAIM_BUTTON_SELECTOR = (
        'button:has-text("Получить сейчас"), '
        'button:has-text("Claim Now"), '
        'button:has(div[data-a-target="tw-core-button-label-text"]'
        ':has-text("Claim"))'
    )
    # сколько раз перезагружать инвентарь, если клейм так и не прошёл
    CLAIM_MAX_RETRIES = 4
    # сколько ждать успешный ответ после клика (Twitch сам повторяет запрос
    # после отказа по integrity)
    CLAIM_WAIT_SECONDS = 60

    def __init__(
        self,
        token: str,
        account_id: int,
        config: MinerConfig,
        proxy: Optional[dict] = None,
        claim_proxy: Optional[dict] = None,
        owner: Optional[int] = None,
        login: Optional[str] = None,
    ):
        self.config = config
        self.account_id = account_id
        self.access_token = token
        self.proxy = proxy
        self.claim_proxy = claim_proxy
        # владелец (id пользователя панели) и логин аккаунта — для маршрутизации
        # логов в движок конкретного пользователя без утечки между аккаунтами
        self.owner = owner
        self.login = login
        self.session: Optional[aiohttp.ClientSession] = None
        self.websocket: Optional[WebsocketClient] = None

        self.user_id: Optional[int] = None
        self.username: Optional[str] = None
        # тип токена: мобильный (Android) клеймится через API, веб — через браузер
        self.is_mobile: bool = True

        self.device_id = ''.join(secrets.choice(string.hexdigits.lower()) for _ in range(32))
        self.session_id = ''.join(secrets.choice(string.hexdigits.lower()) for _ in range(16))
        self.play_session_id = ''.join(secrets.choice(string.hexdigits.lower()) for _ in range(32))
        self.app_session_id = ''.join(secrets.choice(string.hexdigits.lower()) for _ in range(16))

        self.client_integrity: Optional[str] = None
        self.client_integrity_expiration: Optional[int] = None
        self._integrity_unavailable_logged = False

        self.running = False
        self.campaigns: list[Campaign] = []
        # аккаунт уже видел кампании в инвентаре (значит не «пустой»,
        # активировать просмотром не нужно — определяем, что отфармлено)
        self._seen_campaigns = False
        self._all_farmed_logged = False
        self.active_drops: dict[str, Drop] = {}
        # инстансы дропов, которые уже заклеймлены в этой сессии — чтобы
        # не клеймить их повторно каждый цикл (Twitch может возвращать их снова)
        self._claimed_instances: set[str] = set()
        self.channels: OrderedDict[int, Channel] = OrderedDict()
        self.watching_channel: Optional[Channel] = None
        self.current_game: Optional[str] = None
        self.watch_minutes: int = 0
        self._spade_urls: dict[int, str] = {}
        self._last_drop_log_state: Optional[tuple[int, tuple[str, ...]]] = None

        self._playwright = None
        self._browser = None
        self._browser_context = None
        self._browser_page = None

    def _proxy_url(self) -> Optional[str]:
        if not self.proxy:
            return None
        scheme = (self.proxy.get("scheme") or "http").lower()
        host = self.proxy.get("host")
        port = self.proxy.get("port")
        if not host or not port:
            return None
        auth = ""
        username = self.proxy.get("username") or ""
        if username:
            password = self.proxy.get("password") or ""
            auth = f"{quote(str(username), safe='')}:{quote(str(password), safe='')}@"
        return f"{scheme}://{auth}{host}:{port}"

    def _proxy_kwargs(self) -> dict:
        proxy_url = self._proxy_url()
        return {"proxy": proxy_url} if proxy_url else {}

    def _browser_proxy(self) -> Optional[dict]:
        """Прокси для Playwright-клейма из пула переавторизации."""
        proxy = self.claim_proxy or self.proxy
        if not proxy:
            return None
        scheme = (proxy.get("scheme") or "http").lower()
        host = proxy.get("host")
        port = proxy.get("port")
        if not host or not port:
            return None
        cfg = {"server": f"{scheme}://{host}:{port}"}
        username = proxy.get("username") or ""
        if username:
            cfg["username"] = str(username)
            cfg["password"] = str(proxy.get("password") or "")
        return cfg

    @staticmethod
    def _clean_headers(headers: dict) -> dict[str, str]:
        return {
            str(key): str(value)
            for key, value in headers.items()
            if value is not None
        }

    def _log(self, msg: str):
        # логин аккаунта, не токен — токены не должны попадать в логи/UI
        name = self.login or self.username or f"acc{self.account_id}"
        logger.bind(owner=self.owner, login=name).info(f"[{name}] {msg}")

    async def _create_session(self):
        timeout = aiohttp.ClientTimeout(total=self.config.connection_timeout)
        connector = aiohttp.TCPConnector(limit=50)

        headers = {
            "Client-Id": self.CLIENT_ID,
            "User-Agent": self.USER_AGENT,
            "Accept-Language": "en-US",
        }

        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers=self._clean_headers(headers),
        )

        try:
            async with self.session.get(
                "https://www.twitch.tv", **self._proxy_kwargs()
            ) as response:
                cookies = self.session.cookie_jar.filter_cookies("https://www.twitch.tv")
                if "unique_id" in cookies:
                    self.device_id = cookies["unique_id"].value
        except:
            pass

    async def _fetch_client_integrity(self):
        if not self.session or self.session.closed:
            return False

        try:
            import secrets
            import string
            client_request_id = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

            headers = {
                "Accept": "*/*",
                "Authorization": f"OAuth {self.access_token}",
                "Client-Id": self.CLIENT_ID,
                "Client-Request-Id": client_request_id,
                "Client-Session-Id": self.session_id,
                "User-Agent": self.USER_AGENT,
                "X-Device-Id": self.device_id,
                "Origin": "https://www.twitch.tv",
                "Referer": "https://www.twitch.tv/",
            }

            async with self.session.post(
                "https://gql.twitch.tv/integrity",
                headers=self._clean_headers(headers),
                **self._proxy_kwargs(),
            ) as response:
                try:
                    data = await response.json()
                except Exception:
                    data = None
                if response.status == 200 and data and data.get("token"):
                    self.client_integrity = data["token"]
                    self.client_integrity_expiration = data.get("expiration")
                    self._log("проверка целостности клиента выполнена")
                    return True
                if not self._integrity_unavailable_logged:
                    self._log(
                        f"проверка целостности недоступна (HTTP {response.status}) — "
                        "для фарма не требуется, продолжаю"
                    )
                    self._integrity_unavailable_logged = True
        except Exception as e:
            if not self._integrity_unavailable_logged:
                self._log(
                    f"проверка целостности недоступна ({e}) — "
                    "для фарма не требуется, продолжаю"
                )
                self._integrity_unavailable_logged = True
        return False

    async def _gql_request(self, operation: dict) -> dict:
        if not self.running or not self.session or self.session.closed:
            raise RuntimeError("Сессия не создана")

        # Android-путь: integrity/Kasada не требуются (см. DevilXD).
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US",
            "Authorization": f"OAuth {self.access_token}",
            "Client-Id": self.CLIENT_ID,
            "Client-Session-Id": self.session_id,
            "User-Agent": self.USER_AGENT,
            "X-Device-Id": self.device_id,
            "Origin": "https://www.twitch.tv",
            "Referer": "https://www.twitch.tv/",
        }

        async with self.session.post(
            self.GQL_URL,
            json=[operation],
            headers=self._clean_headers(headers),
            **self._proxy_kwargs(),
        ) as response:
            response.raise_for_status()
            data = await response.json()

            if isinstance(data, list):
                data = data[0]

            if "errors" in data:
                raise Exception(data["errors"][0]["message"])

            return data


    async def _gql_request_claim_drop(self, operation: dict, token, device_id, ) -> dict:
        if not self.running or not self.session or self.session.closed:
            raise RuntimeError("Сессия не создана")
        client_id = self.CLIENT_ID if self.is_mobile else self.WEB_CLIENT_ID
        user_agent = self.USER_AGENT if self.is_mobile else self.WEB_USER_AGENT
        headers = {
            "Accept": "*/*",
            "Authorization": f"OAuth {self.access_token}",
            "Client-Id": client_id,
            "Client-Session-Id": self.session_id,
            "User-Agent": user_agent,
            "X-Device-Id": device_id,
            "Origin": "https://www.twitch.tv",
            "Referer": "https://www.twitch.tv/",
        }

        async with self.session.post(
            self.GQL_URL,
            json=[operation],
            headers=self._clean_headers(headers),
            **self._proxy_kwargs(),
        ) as response:
            response.raise_for_status()
            data = await response.json()

            if isinstance(data, list):
                data = data[0]

            if "errors" in data:
                print(data)

            return data

    async def validate_token(self) -> bool:
        if not self.running:
            return False
        if not self.session or self.session.closed:
            await self._create_session()

        try:
            headers = {"Authorization": f"OAuth {self.access_token}"}
            async with self.session.get(
                self.VALIDATE_URL,
                headers=self._clean_headers(headers),
                **self._proxy_kwargs(),
            ) as response:
                if response.status == 401:
                    self._log("аккаунт невалиден: токен отклонён")
                    return False

                data = await response.json()
                self.user_id = int(data["user_id"])
                self.username = data.get("login", f"#{self.account_id}")
                # client_id, для которого выпущен токен: Android → мобильный
                token_client_id = data.get("client_id")
                self.is_mobile = token_client_id == self.CLIENT_ID
                self._log(
                    f"аккаунт валиден (ID {self.user_id}), токен: "
                    f"{'мобильный' if self.is_mobile else 'веб'}"
                )
                return True
        except Exception as e:
            self._log(f"не удалось проверить аккаунт: {e}")
            return False
    async def fetch_json(self, campaign_data: any, filename: str):

        drops = campaign_data.get('timeBasedDrops') or []
        campaign = Campaign.from_data(campaign_data)
        progress = 0
        drops_dict = {}
        max_required = 0
        for drop in drops:
            required = drop.get('requiredMinutesWatched') or 0
            current = (drop.get('self') or {}).get('currentMinutesWatched') or 0
            drop_progress = round(min(current / required * 100, 100)) if required else 0
            drops_dict[drop['name']] = {
                'current': current,
                'required': required,
                'progress': drop_progress,
            }
            if required > max_required:
                max_required = required
        if max_required:
            # overall progress = current watched time / max required among drops
            overall_current = max((d['current'] for d in drops_dict.values()), default=0)
            progress = round(min(overall_current / max_required * 100, 100))
        game_name = campaign.game.name
        season_name = campaign.name

        temp_file = f"{filename}.temp"
        accounts = None
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
            except portalocker.exceptions.LockException:
                self._log("файл аккаунтов занят, обновление пропущено")
                return
            
            try:
                accounts = json.load(f)
            except json.JSONDecodeError:
                self._log("файл аккаунтов повреждён, создаю пустой список")
                accounts = []
            finally:
                portalocker.unlock(f)

        if accounts is None:
            return
        
        # Handle both array and object formats
        accounts_list = accounts if isinstance(accounts, list) else accounts.get('accounts', [])
        account = next((a for a in accounts_list if a['token'] == self.access_token), None)
        if not account:
            self._log("аккаунт не найден в файле данных")
            return

        if not account.get('campaigns'):
            account['campaigns'] = []
        existing_campaign = None
        for camp in account['campaigns']:
            if camp.get('name') == game_name and camp.get('season') == season_name:
                existing_campaign = camp
                break

        campaign_data_to_save = {
            'name': game_name,
            'season': season_name,
            'progress': progress,
            'drops': drops_dict,
        }

        campaign_added = existing_campaign is None
        if existing_campaign:
            existing_campaign.update(campaign_data_to_save)
        else:
            account['campaigns'].append(campaign_data_to_save)
            self._log(f"кампания добавлена: {game_name} / {season_name}")

        try:
            with open(temp_file, 'w', encoding='utf-8') as tf:
                # Save in the same format as loaded (array or object)
                if isinstance(accounts, list):
                    json.dump(accounts, tf, indent=4, ensure_ascii=False)
                else:
                    json.dump(accounts, tf, indent=4, ensure_ascii=False)


            try:
                os.replace(temp_file, filename)
                if campaign_added:
                    self._log("данные аккаунта сохранены")
            except PermissionError as e:
                if getattr(e, "winerror", None) == 5:
                    self._log("нет доступа к файлу данных аккаунта")
                    await asyncio.sleep(0.4)
                else:
                    raise
            except Exception as e:
                self._log(f"не удалось заменить файл данных: {e}")
                raise


        except Exception as e:
            self._log(f"не удалось сохранить данные аккаунта: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def _campaign_selected(self, campaign: Campaign) -> bool:
        """Фармим только кампании, выбранные в панели (если выбор задан)."""
        ids = self.config.campaign_ids
        games = self.config.campaign_games
        if not ids and not games:
            return True
        if campaign.id in ids:
            return True
        game_name = campaign.game.name if campaign.game else ""
        return game_name.lower() in games

    async def fetch_inventory(self):        
        operation = {
            "operationName": "Inventory",
            "variables": {"fetchRewardCampaigns": False},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "d86775d0ef16a63a33ad52e80eaff963b2d5b72fada7c991504a57496e1d8e4b"
                }
            }
        }

        try:
            data = await self._gql_request(operation)
            user_data = data["data"]["currentUser"]
            if not user_data:
                return
            inventory = user_data.get("inventory")
            if not inventory:
                return
            
            campaigns_data = inventory.get("dropCampaignsInProgress", []) or []
            if campaigns_data:
                self._seen_campaigns = True
            self.campaigns.clear()
            self.active_drops.clear()
            now = datetime.now(timezone.utc)

            for campaign_data in campaigns_data:
                try:
                    campaign = Campaign.from_data(campaign_data)
                    
                    if campaign_data.get("status") == "EXPIRED":
                        continue
                    if not self._campaign_selected(campaign):
                        continue
                    if campaign.ends_at < now:
                        continue
                    if campaign.starts_at > now + timedelta(hours=24):
                        continue

                    self.campaigns.append(campaign)
                    await self.fetch_json(campaign_data=campaign_data, filename=str(self.config.tokens_file))


                    for drop in campaign.drops:
                        if drop.can_earn or drop.can_claim:
                            for time_drop in campaign_data.get('timeBasedDrops', []):
                                if time_drop.get('id') == drop.id:
                                    drop_instance_id = time_drop.get('self', {}).get('dropInstanceID')
                                    if drop_instance_id:
                                        drop.claim_id = drop_instance_id
                                    break

                            # уже заклеймлен ранее в этой сессии — пропускаем,
                            # чтобы не зациклиться на повторном клейме
                            if drop.claim_id and drop.claim_id in self._claimed_instances:
                                continue

                            self.active_drops[drop.id] = drop
                except Exception as e:
                    self._log(f"не удалось обработать кампанию: {e}")
                    continue

            claimable = [d for d in self.active_drops.values() if d.can_claim]
            farmable = [d for d in self.active_drops.values() if d.can_earn]
            if self.active_drops:
                self._all_farmed_logged = False
            drop_log_state = (
                len(claimable),
                tuple(sorted(d.name for d in farmable)),
            )
            if drop_log_state != self._last_drop_log_state:
                self._log(
                    f"прогресс: {len(claimable)}/{len(self.active_drops)} дропов "
                    "готово к клейму"
                )
                if farmable:
                    self._log(
                        "фармлю: " + ", ".join(d.name for d in farmable)
                    )
                self._last_drop_log_state = drop_log_state


        except Exception as e:
            self._log(f"не удалось обновить данные аккаунта: {e}")

    def _progress_snapshot(self) -> dict[str, int]:
        """Слепок прогресса по фармабельным дропам (id → отсмотрено минут)."""
        return {
            d.id: d.current_minutes
            for d in self.active_drops.values()
            if d.can_earn
        }

    @staticmethod
    def _progress_advanced(prev: dict[str, int], cur: dict[str, int]) -> bool:
        """True, если прогресс сдвинулся: любой дроп вырос или какой-то завершился."""
        if len(cur) < len(prev):
            return True  # дроп ушёл из фармабельных = завершён/заклеймлен
        for drop_id, prev_min in prev.items():
            if cur.get(drop_id, prev_min) > prev_min:
                return True
        return False

    async def _claim_completed(self) -> None:
        """Клеймит завершённые дропы (иначе они висят на 100% без награды).

        Мобильный токен клеймит запросами к API, веб-токен — только через
        браузер: API-путь для веб-токена Twitch отклоняет по integrity.
        """
        claimable = [
            drop for drop in list(self.active_drops.values())
            if drop.can_claim
            and not (drop.claim_id and drop.claim_id in self._claimed_instances)
        ]
        if not claimable:
            return
        if self.is_mobile:
            for drop in claimable:
                await self._claim_drop_api(drop)
        else:
            await self._claim_all_browser(claimable)

    async def fetch_claimable_instances(self) -> list[tuple[str, str]]:
        """Готовые к клейму дропы прямо из инвентаря: [(dropInstanceID, имя)].

        В отличие от fetch_inventory не отсекает кампании по датам и не
        смотрит на active_drops: награду можно забрать и после того, как
        кампания закончилась.
        """
        operation = {
            "operationName": "Inventory",
            "variables": {"fetchRewardCampaigns": False},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "d86775d0ef16a63a33ad52e80eaff963b2d5b72fada7c991504a57496e1d8e4b"
                }
            }
        }

        instances: list[tuple[str, str]] = []
        try:
            data = await self._gql_request(operation)
            user_data = (data.get("data") or {}).get("currentUser") or {}
            inventory = user_data.get("inventory") or {}
            for campaign_data in inventory.get("dropCampaignsInProgress") or []:
                for time_drop in campaign_data.get("timeBasedDrops") or []:
                    self_data = time_drop.get("self") or {}
                    instance_id = self_data.get("dropInstanceID")
                    if not instance_id or self_data.get("isClaimed"):
                        continue
                    if instance_id in self._claimed_instances:
                        continue
                    current = self_data.get("currentMinutesWatched") or 0
                    required = time_drop.get("requiredMinutesWatched") or 0
                    if current < required:
                        continue
                    instances.append(
                        (instance_id, time_drop.get("name") or time_drop.get("id", ""))
                    )
        except Exception as e:
            self._log(f"не удалось проверить готовые к клейму дропы: {e}")
        return instances

    async def claim_pending_rewards(self) -> int:
        """Забирает всё, что уже готово к клейму. Возвращает число наград.

        Вызывается при старте фарма: на аккаунте могут висеть дропы,
        добитые в прошлый запуск и оставшиеся незаклеймленными.
        """
        instances = await self.fetch_claimable_instances()
        if not instances:
            self._log("готовых к клейму дропов нет")
            return 0

        self._log(f"готовых к клейму дропов: {len(instances)}, забираю")
        if self.is_mobile:
            claimed = set()
            for instance_id, name in instances:
                if await self._claim_instance_api(instance_id, name):
                    claimed.add(instance_id)
        else:
            claimed = await self._claim_instances_browser(instances)

        # неуспешные не помечаем как обработанные — попробуем ещё раз позже
        for instance_id, name in instances:
            if instance_id not in claimed:
                self._log(f"не удалось забрать дроп {name}: Twitch отклонил клейм")
        for drop in list(self.active_drops.values()):
            if drop.claim_id and drop.claim_id in claimed:
                drop.is_claimed = True
                self.active_drops.pop(drop.id, None)

        self._log(f"забрано наград: {len(claimed)} из {len(instances)}")
        return len(claimed)

    async def _claim_all_browser(self, drops: list[Drop]) -> None:
        """Забирает все готовые дропы аккаунта за один запуск браузера."""
        items = [(d.claim_id, d.name) for d in drops if d.claim_id]
        claimed_ids = await self._claim_instances_browser(items)

        for drop in drops:
            if drop.claim_id and drop.claim_id in claimed_ids:
                drop.is_claimed = True
                self._claimed_instances.add(drop.claim_id)
                self._log(f"дроп заклеймлен: {drop.name}")
                if drop.id in self.active_drops:
                    del self.active_drops[drop.id]
            else:
                self._log(
                    f"не удалось забрать дроп {drop.name}: Twitch отклонил клейм"
                )

    async def _claim_instances_browser(
        self, items: list[tuple[str, str]]
    ) -> set[str]:
        """Кликает «Получить сейчас» в /drops/inventory за один запуск браузера.

        Возвращает dropInstanceID, которые Twitch подтвердил заклеймленными.
        """
        claimed_ids: set[str] = set()
        if not items:
            return claimed_ids

        async with _get_browser_semaphore():
            if not await self._init_browser():
                self._log("браузер недоступен, клейм веб-токена невозможен")
                return claimed_ids

            # Twitch часто отклоняет первый клейм по integrity и выдаёт рабочий
            # токен только после этого, поэтому отказ = повод перезагрузиться
            # и кликнуть ещё раз, а не считать дроп незабранным.
            claim_events: list[bool] = []

            async def _on_response(resp):
                if "gql.twitch.tv" not in resp.url:
                    return
                try:
                    body = await resp.json()
                except Exception:
                    return
                for item in (body if isinstance(body, list) else [body]):
                    if not isinstance(item, dict):
                        continue
                    ext = item.get("extensions") or {}
                    if ext.get("operationName") != "DropsPage_ClaimDropRewards":
                        continue
                    status = (
                        (item.get("data") or {}).get("claimDropRewards") or {}
                    ).get("status")
                    ok = status in (
                        "ELIGIBLE_FOR_ALL", "DROP_INSTANCE_ALREADY_CLAIMED"
                    )
                    claim_events.append(ok)
                    if not ok:
                        continue
                    try:
                        post_data = resp.request.post_data
                        if not post_data:
                            continue
                        parsed = json.loads(post_data)
                        for entry in (parsed if isinstance(parsed, list) else [parsed]):
                            iid = (
                                ((entry.get("variables") or {}).get("input") or {})
                                .get("dropInstanceID")
                            )
                            if iid:
                                claimed_ids.add(iid)
                    except Exception:
                        pass

            self._browser_page.on("response", _on_response)

            try:
                self._log(f"получаю награды: {len(items)} шт.")
                await self._open_inventory_page()

                attempts = 0
                max_attempts = len(items) + self.CLAIM_MAX_RETRIES
                while attempts < max_attempts:
                    attempts += 1
                    buttons = self._browser_page.locator(self.CLAIM_BUTTON_SELECTOR)
                    if not await buttons.count():
                        break
                    seen = len(claim_events)
                    try:
                        await buttons.first.scroll_into_view_if_needed()
                        await buttons.first.click()
                    except Exception:
                        break

                    # После отказа по integrity страница Twitch сама повторяет
                    # запрос, поэтому ждём успешный ответ и не трогаем страницу.
                    ok = False
                    for _ in range(self.CLAIM_WAIT_SECONDS):
                        await asyncio.sleep(1)
                        if any(claim_events[seen:]):
                            ok = True
                            break
                    if ok:
                        continue

                    self._log(
                        "клейм не прошёл, перезагружаю страницу и пробую снова"
                    )
                    await asyncio.sleep(5)
                    await self._open_inventory_page()
            except Exception as e:
                self._log(f"ошибка при получении наград: {e}")
            finally:
                await self._close_browser()

        return claimed_ids

    async def _open_inventory_page(self) -> None:
        """Открывает страницу инвентаря и убирает перекрывающие баннеры."""
        await self._browser_page.goto('https://www.twitch.tv/drops/inventory')
        await asyncio.sleep(8)
        await self._dismiss_overlays()
        await self._browser_page.evaluate('window.scrollTo(0, 500)')
        await asyncio.sleep(2)

    async def _dismiss_overlays(self) -> None:
        """Закрывает баннеры Twitch, перекрывающие кнопки клейма."""
        labels = (
            'button[data-a-target="consent-banner-accept"]',
            'button:has-text("Not Now")',
            'button:has-text("Не сейчас")',
            'button:has-text("Accept")',
            'button:has-text("Принять")',
        )
        for selector in labels:
            try:
                element = self._browser_page.locator(selector).first
                if await element.count():
                    await element.click(timeout=3000)
                    await asyncio.sleep(1)
            except Exception:
                pass

    async def watch_stream(self, channel: Channel):
        self.watching_channel = channel
        self.current_game = None
        self.watch_minutes = 0

        broadcast_id = await self._get_broadcast_id(channel)
        if not broadcast_id:
            self._log(f"стример {channel.name} недоступен, просмотр не начат")
            self.watching_channel = None
            return

        spade_url = await self._get_spade_url(channel)
        if not spade_url:
            self._log(
                f"не удалось подготовить просмотр {channel.name}, "
                "использую резервный способ"
            )

        game_name = channel.game.name if channel.game else "неизвестная игра"
        self.current_game = channel.game.name if channel.game else None
        self._log(f"смотрю {channel.name}: играет {game_name}")

        check_interval = max(1, self.config.inventory_check_minutes)
        # периодически перезапрашиваем broadcast_id: за часы стрим может
        # перезапуститься и получить новый id — тогда minute-watched отвечает
        # 200, но прогресс молча не начисляется (главная причина "зависаний")
        refresh_broadcast_minutes = 15
        # сторож прогресса по wall-clock: Twitch обновляет currentMinutesWatched
        # пачками (раз в несколько минут), поэтому считаем "завис" только если
        # прогресс не двигался столько МИНУТ подряд, а не по числу проверок
        stall_window_min = 20
        last_snapshot = self._progress_snapshot()
        last_advance = time.monotonic()

        while self.running and self.watching_channel == channel:
            drops_to_farm = [d for d in self.active_drops.values() if d.can_earn]
            if not drops_to_farm:
                self._log("все доступные дропы нафармлены")
                break

            try:
                # обновляем broadcast_id, чтобы не слать прогресс на устаревший стрим
                if self.watch_minutes > 0 and self.watch_minutes % refresh_broadcast_minutes == 0:
                    fresh_id = await self._get_broadcast_id(channel)
                    if not fresh_id:
                        self._log(f"стример {channel.name} офлайн, просмотр остановлен")
                        break
                    if fresh_id != broadcast_id:
                        self._log(
                            f"стример {channel.name} перезапущен, "
                            "обновляю просмотр"
                        )
                        broadcast_id = fresh_id
                        self._spade_urls.pop(channel.id, None)
                        spade_url = await self._get_spade_url(channel)

                success = await self._send_watch_progress(channel, broadcast_id, spade_url)
                if success:
                    self.watch_minutes += 1
                    claimable_count = sum(
                        drop.can_claim for drop in self.active_drops.values()
                    )
                    self._log(
                        f"смотрю {channel.name}: {self.watch_minutes} мин "
                        f"(прогресс {claimable_count}/{len(self.active_drops)})"
                    )
                else:
                    self._log(f"не удалось передать прогресс просмотра {channel.name}")

                if self.watch_minutes > 0 and self.watch_minutes % check_interval == 0:
                    await self.fetch_inventory()
                    await self._claim_completed()
                    snapshot = self._progress_snapshot()
                    if self._progress_advanced(last_snapshot, snapshot):
                        last_advance = time.monotonic()
                        last_snapshot = snapshot
                    elif time.monotonic() - last_advance >= stall_window_min * 60:
                        self._log(
                            f"прогресс не меняется {stall_window_min} минут, "
                            "выбираю другого стримера"
                        )
                        break

                if not await self._check_stream_online(channel):
                    self._log(f"стример {channel.name} офлайн, просмотр остановлен")
                    break

                await asyncio.sleep(self.config.watch_interval)

            except Exception as e:
                self._log(f"ошибка во время просмотра: {e}")
                await asyncio.sleep(5)

        self._log(f"просмотр {channel.name} завершён, всего {self.watch_minutes} мин")
        self.watching_channel = None
        self.current_game = None

    async def _get_broadcast_id(self, channel: Channel) -> Optional[str]:
        operation = {
            "operationName": "VideoPlayerStreamInfoOverlayChannel",
            "variables": {"channel": channel.login},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "198492e0857f6aedead9665c81c5a06d67b25b58034649687124083ff288597d"
                }
            }
        }

        try:
            data = await self._gql_request(operation)
            user_data = data["data"]["user"]
            if not user_data or not user_data.get("stream"):
                return None
            await self._get_stream_game(channel)
            return user_data["stream"]["id"]
        except:
            return None

    async def _get_stream_game(self, channel: Channel) -> Optional[Game]:
        operation = {
            "query": (
                '{ user(login: "%s") { stream { id game { id name } } } }'
                % json.dumps(channel.login)[1:-1]
            )
        }
        try:
            data = await self._gql_request(operation)
            game_data = ((data.get("data", {}).get("user") or {}).get("stream") or {}).get("game")
            if game_data:
                channel.game = Game.from_data(game_data)
            return channel.game
        except Exception as e:
            self._log(f"не удалось определить игру стримера {channel.name}: {e}")
            return channel.game

    async def _get_spade_url(self, channel: Channel) -> Optional[str]:
        """
        spade_url извлекается по цепочке (как в DevilXD):
        HTML страницы стримера --parse--> settings.js --parse--> spade_url.
        Результат кэшируется на канал.
        """
        if channel.id in self._spade_urls:
            return self._spade_urls[channel.id]

        SETTINGS_PATTERN = r'src="(https://[\w.]+/config/settings\.[0-9a-f]{32}\.js)"'
        SPADE_PATTERN = r'"spade_?url": ?"(https://[.\w\-/]+)"'
        try:
            url = f"https://www.twitch.tv/{channel.login}"
            async with self.session.get(url, **self._proxy_kwargs()) as r1:
                html = await r1.text()
            match = re.search(SPADE_PATTERN, html, re.I)
            if not match:
                settings_match = re.search(SETTINGS_PATTERN, html, re.I)
                if not settings_match:
                    self._log("не удалось подготовить просмотр стримера")
                    return None
                async with self.session.get(
                    settings_match.group(1), **self._proxy_kwargs()
                ) as r2:
                    settings_js = await r2.text()
                match = re.search(SPADE_PATTERN, settings_js, re.I)
                if not match:
                    self._log("не удалось загрузить данные для просмотра стримера")
                    return None
            spade_url = match.group(1)
            self._spade_urls[channel.id] = spade_url
            return spade_url
        except Exception as e:
            self._log(f"не удалось подготовить просмотр стримера: {e}")
            return None

    def _build_watch_properties(self, channel: Channel, broadcast_id: str) -> dict:
        # Минимальный набор полей minute-watched, как в рабочем DevilXD.
        # Без web-специфичных полей (platform/player/browser), которые
        # ломают консистентность с мобильным токеном.
        game_id = str(channel.game.id) if channel.game else ""
        game_name = channel.game.name if channel.game else ""
        return {
            "broadcast_id": str(broadcast_id),
            "channel_id": str(channel.id),
            "channel": channel.login,
            "client_time": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "game": game_name,
            "game_id": game_id,
            "hidden": False,
            "is_live": True,
            "live": True,
            "logged_in": True,
            "minutes_logged": 1,
            "muted": False,
            "user_id": self.user_id,
        }

    async def _send_watch_progress(
        self, channel: Channel, broadcast_id: str, spade_url: Optional[str]
    ) -> bool:
        from base64 import b64encode

        payload = [
            {
                "event": "minute-watched",
                "properties": self._build_watch_properties(channel, broadcast_id),
            }
        ]
        payload_json = json.dumps(payload, separators=(",", ":"))

        # Основной канал (как в рабочем DevilXD): прямой POST minute-watched
        # на spade_url стримера.
        if spade_url:
            try:
                data_b64 = b64encode(payload_json.encode()).decode()
                async with self.session.post(
                    spade_url,
                    data={"data": data_b64},
                    **self._proxy_kwargs(),
                ) as response:
                    if response.status in (200, 204):
                        return True
                    self._log(
                        f"основной способ передачи просмотра отклонён (HTTP {response.status}), "
                        "использую резервный способ"
                    )
            except Exception as e:
                self._log(f"основной способ передачи просмотра недоступен: {e}")

        # Fallback: та же телеметрия через GraphQL sendSpadeEvents.
        payload_b64 = b64encode(gzip.compress(payload_json.encode())).decode()
        operation = {
            "query": "\n  mutation SendEvents($input: SendSpadeEventsInput!) {\n    sendSpadeEvents(input: $input) {\n      statusCode\n    }\n  }\n",
            "variables": {
                "input": {
                    "data": payload_b64,
                    "repository": "twilight",
                    "encoding": "GZIP_B64",
                }
            },
        }
        try:
            data = await self._gql_request(operation)
            if data and data.get("data", {}).get("sendSpadeEvents"):
                status_code = data["data"]["sendSpadeEvents"].get("statusCode")
                return status_code in (200, 204)
        except Exception as e:
            self._log(f"резервная передача прогресса не удалась: {e}")

        return False

    async def _check_stream_online(self, channel: Channel) -> bool:
        try:
            ch = await self.check_streamer_online(channel.login, log_online=False)
            return ch is not None
        except:
            return False

    async def _init_browser(self):
        if not BROWSER_AVAILABLE:
            return False

        if self._browser_page:
            return True

        try:
            self._playwright = await async_playwright().start()
            launch_kwargs = {
                "headless": BROWSER_HEADLESS,
                # обязательно на Linux-сервере (root/контейнер) и при малом /dev/shm
                "args": ["--no-sandbox", "--disable-dev-shm-usage"],
            }
            if BROWSER_CHANNEL:
                launch_kwargs["channel"] = BROWSER_CHANNEL
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            context_kwargs = {}
            browser_proxy = self._browser_proxy()
            if browser_proxy:
                context_kwargs["proxy"] = browser_proxy
            self._browser_context = await self._browser.new_context(**context_kwargs)

            await self._browser_context.add_cookies([{
                'name': 'auth-token',
                'value': self.access_token,
                'domain': '.twitch.tv',
                'path': '/'
            }])

            self._browser_page = await self._browser_context.new_page()

            async def _route_claim_assets(route):
                resource_type = route.request.resource_type
                if resource_type in {"font", "media"}:
                    await route.abort()
                else:
                    await route.continue_()

            await self._browser_page.route("**/*", _route_claim_assets)
            return True
        except Exception as e:
            self._log(f"не удалось получить награду: {e}")
            return False

    async def _close_browser(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._browser_context = None
        self._browser_page = None

    async def claim_drop(self, drop: Drop) -> bool:
        if drop.is_claimed:
            return True

        if not drop.can_claim:
            return False

        self._log(f"получаю награду: {drop.name}")

        if self.is_mobile:
            return await self._claim_drop_api(drop)

        await self._claim_all_browser([drop])
        return drop.is_claimed

    async def _claim_drop_api(self, drop: Drop) -> bool:
        if not await self._claim_instance_api(drop.claim_id, drop.name):
            return False
        drop.is_claimed = True
        self.active_drops.pop(drop.id, None)
        return True

    async def _claim_instance_api(self, instance_id: str, name: str) -> bool:
        """Клейм через GQL — работает только для мобильных токенов."""
        if not instance_id:
            return False
        operation = {
            "operationName": "DropsPage_ClaimDropRewards",
            "variables": {"input": {"dropInstanceID": instance_id}},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "a455deea71bdc9015b78eb49f4acfbce8baa7ccbedd28e549bb025bd0f751930"
                }
            }
        }

        try:
            result = await self._gql_request_claim_drop(
                operation, self.access_token, self.device_id
            )
            data = result.get("data", {})
            claim_result = data.get("claimDropRewards")
            if not claim_result:
                self._log(f"клейм (API) без результата для {name}: {result}")
                return False

            status = claim_result.get("status")
            if status in ("ELIGIBLE_FOR_ALL", "DROP_INSTANCE_ALREADY_CLAIMED"):
                self._claimed_instances.add(instance_id)
                self._log(f"дроп заклеймлен: {name}")
                return True
            self._log(f"клейм (API) не выполнен для {name}: status={status}")
        except Exception as e:
            self._log(f"клейм (API) ошибка для {name}: {e}")
        return False

    async def check_streamer_online(
        self, login: str, log_online: bool = True
    ) -> Optional[Channel]:
        operation = {
            "operationName": "VideoPlayerStreamInfoOverlayChannel",
            "variables": {"channel": login},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "198492e0857f6aedead9665c81c5a06d67b25b58034649687124083ff288597d"
                }
            }
        }

        try:
            data = await self._gql_request(operation)
            user_data = data["data"]["user"]

            if not user_data:
                self._log(f"стример {login} не найден")
                return None

            stream_data = user_data.get("stream")
            if not stream_data:
                self._log(f"стример {login} офлайн")
                return None
            
            channel = Channel(
                channel_id=int(user_data["id"]),
                login=user_data["login"],
                display_name=user_data["displayName"],
                viewers=stream_data.get("viewersCount", 0),
            )

            game_data = stream_data.get("game")
            if game_data:
                channel.game = Game.from_data(game_data)
            else:
                await self._get_stream_game(channel)

            if log_online:
                game_name = channel.game.name if channel.game else "игра не определена"
                self._log(
                    f"стример {channel.name} онлайн ({channel.viewers} зрителей), "
                    f"игра: {game_name}"
                )
            return channel
        except Exception as e:
            self._log(f"не удалось проверить стримера {login}: {e}")
            return None

    async def _log_unconnected_campaign(self, channel: Channel) -> None:
        """Сообщает, если активная кампания игры требует привязки аккаунта."""
        if not channel.game:
            return

        operation = {
            "operationName": "ViewerDropsDashboard",
            "variables": {"fetchRewardCampaigns": True},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": (
                        "5a4da2ab3d5b47c9f9ce864e727b2cb346af1e3ea8b897fe8f704a97ff017619"
                    ),
                }
            },
        }
        try:
            data = await self._gql_request(operation)
            campaigns = (
                (data.get("data", {}).get("currentUser") or {}).get(
                    "dropCampaigns"
                )
                or []
            )
            for campaign in campaigns:
                game = campaign.get("game") or {}
                state = campaign.get("self") or {}
                if (
                    campaign.get("status") == "ACTIVE"
                    and str(game.get("id")) == str(channel.game.id)
                    and state.get("isAccountConnected") is False
                ):
                    self._log(
                        f"кампания {channel.game.name} требует привязки аккаунта "
                        "к игре — Twitch не засчитает просмотр, пропускаю"
                    )
                    return
        except Exception:
            return

    async def _handle_no_active_drops(self) -> None:
        """Нет фармабельных/клеймабельных дропов.

        Если аккаунт уже видел кампании — значит всё отфармлено и заклеймлено,
        активировать просмотром не нужно. Иначе (пустой аккаунт) — активируем.
        """
        if self._seen_campaigns:
            if not self._all_farmed_logged:
                self._log("все доступные дропы отфармлены и заклеймлены")
                self._all_farmed_logged = True
            return
        await self._activate_campaigns()

    async def _activate_campaigns(self):
        """
        На пустых аккаунтах дропы не появляются в инвентаре,
        пока не отправлен просмотр стрима с дропами.
        Отправляем minute-watched на первого онлайн-стримера из списка.
        """
        self._log("данных о кампаниях нет, пытаюсь активировать их просмотром стрима")
        connection_checked = False

        for login in self.config.streamers:
            if not self.running or not self.session or self.session.closed:
                return False
            channel = await self.check_streamer_online(login)
            if not channel:
                continue

            broadcast_id = await self._get_broadcast_id(channel)
            if not broadcast_id:
                continue

            game_name = channel.game.name if channel.game else "неизвестная игра"
            self._log(f"активирую кампании просмотром {channel.name}: {game_name}")

            spade_url = await self._get_spade_url(channel)
            for i in range(2):
                if not self.running or not self.session or self.session.closed:
                    return False
                accepted = await self._send_watch_progress(channel, broadcast_id, spade_url)
                self._log(
                    "минута просмотра принята"
                    if accepted
                    else "минута просмотра отклонена"
                )
                await asyncio.sleep(60)

            self._log("просмотр отправлен, обновляю данные аккаунта")
            await self.fetch_inventory()

            farmable_count = sum(
                drop.can_earn for drop in self.active_drops.values()
            )
            if self.active_drops:
                if not farmable_count and not connection_checked and channel.game:
                    await self._log_unconnected_campaign(channel)
                    connection_checked = True
                self._log(
                    f"кампании активированы, доступно дропов: {len(self.active_drops)}"
                )
                return True
            if not connection_checked and channel.game:
                await self._log_unconnected_campaign(channel)
                connection_checked = True

        self._log("не удалось активировать кампании: подходящих дропов нет")
        return False

    async def run(self):
        self.running = True

        await self._create_session()

        if not self.running or not await self.validate_token():
            return

        self.websocket = WebsocketClient(self)
        await self.websocket.connect()

        if not self.running:
            return
        await self.fetch_inventory()
        # старт фарма: проверяем инвентарь и забираем всё, что уже готово,
        # включая дропы из завершившихся кампаний
        await self.claim_pending_rewards()

        if not self.active_drops:
            await self._handle_no_active_drops()

        idx = 0

        while self.running:
            drops_to_farm = [d for d in self.active_drops.values() if d.can_earn]
            if not drops_to_farm:
                if self.active_drops:
                    self._log("подходящих дропов нет, жду обновления данных")
                elif self._seen_campaigns:
                    await self._handle_no_active_drops()
                    self._log("фарм завершён — все дропы отфармлены")
                    break
                await asyncio.sleep(self.config.offline_check_interval)
                await self.fetch_inventory()
                await self._claim_completed()
                if not self.active_drops:
                    await self._handle_no_active_drops()
                    if self._seen_campaigns:
                        self._log("фарм завершён — все дропы отфармлены")
                        break
                continue

            self._log(
                f"фармлю {len(drops_to_farm)} дропов, ищу онлайн-стримера"
            )

            try:
                checked = 0
                found = False

                while checked < len(self.config.streamers) and not found:
                    login = self.config.streamers[idx]
                    channel = await self.check_streamer_online(login)

                    if channel:
                        await self.watch_stream(channel)
                        found = True
                        idx = (idx + 1) % len(self.config.streamers)
                    else:
                        idx = (idx + 1) % len(self.config.streamers)
                        checked += 1

                if not found:
                    self._log(
                        f"онлайн-стримеров нет, жду "
                        f"{self.config.offline_check_interval} секунд"
                    )
                    await asyncio.sleep(self.config.offline_check_interval)
                    idx = 0

            except Exception as e:
                self._log(f"ошибка основного цикла фарма: {e}")
                await asyncio.sleep(30)
    async def test(self):
        await self._create_session()
        if not await self.validate_token():
            return
        
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
                        "sha256Hash": "a455deea71bdc9015b78eb49f4acfbce8baa7ccbedd28e549bb025bd0f751930"
                    }
                }
            }
            if drop.claim_id:
                token = input('token: ')
                di = input('device_id: ')
                await self._gql_request_claim_drop(operation, token, di)

    async def shutdown(self):
        self.running = False
        self.current_game = None
        await self._close_browser()

        if self.websocket:
            await self.websocket.disconnect()

        if self.session:
            await self.session.close()
            self.session = None

    def stop(self):
        self.running = False
        self.current_game = None


class AccountManager:

    def __init__(self, config: MinerConfig):
        self.config = config
        self.miners: list[TwitchMiner] = []

    async def run(self):
        if not self.config.all_tokens:
            logger.error("Токены не найдены")
            return

        if not self.config.streamers:
            logger.error("Стримеры не найдены")
            return

        logger.info(f"Запуск {len(self.config.all_tokens)} аккаунтов")

        for i, token in enumerate(self.config.all_tokens, 1):
            miner = TwitchMiner(token, i, self.config)
            self.miners.append(miner)

        tasks = [miner.run() for miner in self.miners]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def shutdown(self):
        logger.info("Остановка...")
        for miner in self.miners:
            miner.stop()

        tasks = [miner.shutdown() for miner in self.miners]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Остановлено")

    def stop(self):
        for miner in self.miners:
            miner.stop()

if __name__ == "__main__":
    '''config = MinerConfig(tokens=['mbavuvwd3x8j2gwsj8llp3ll4lqmpf'])
    manager = AccountManager(config)

    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(manager.run())
    except KeyboardInterrupt:
        loop.run_until_complete(manager.shutdown())
    finally:
        loop.close()'''
    
    config = MinerConfig(tokens=['l5z3qdywk655t1s33flfq3xewrw3be'])
    manager = TwitchMiner('l5z3qdywk655t1s33flfq3xewrw3be', '1', config)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(manager.test())