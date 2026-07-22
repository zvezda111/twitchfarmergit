# Twitch Farmer (FastAPI + HTML/CSS)

Локальный веб-аналог исходного PyQt6-приложения.
**Полностью офлайн** — никакого CDN, шрифтов или внешних зависимостей в HTML/CSS/JS.

## Структура

```
twitch-farmer-web/
├── main.py           # FastAPI бэкенд (REST + WebSocket для фарма)
├── client.py         # Python-майнер (движок фарма, TwitchMiner)
├── requirements.txt
├── static/
│   ├── index.html    # вёрстка
│   ├── style.css     # стили (light/dark поддержка через CSS-переменные)
│   └── app.js        # вся логика (vanilla JS, без библиотек)
└── data/             # автосоздаётся: users/<uid>/accounts.json, panel.db, …
```

## Установка и запуск

```bash
pip install -r requirements.txt
python main.py
# или
python -m uvicorn main:app
```

Открой <http://127.0.0.1:8000/>.

## Развёртывание на Ubuntu/Debian сервере (headless)

Одной командой:

```bash
bash setup_ubuntu.sh
source venv/bin/activate
python main.py
```

Скрипт ставит python-зависимости, браузер для клейма веб-токенов
(`patchright install-deps` + `patchright install chrome`) и опционально Xvfb.

**Про клейм и браузер.** Мобильные (Android) токены клеймятся через API — браузер
не нужен. Веб-токены Twitch требует клеймить через реальный браузер (integrity),
через Playwright/Patchright:

- **ВАЖНО:** для веб-токенов чистый headless Twitch (Kasada) отклоняет клейм
  (`IntegrityCheckFailed`). Клейм веб-токена проходит только в **headful-режиме под
  Xvfb**. На сервере обязательно: `BROWSER_HEADLESS=false` + запуск под виртуальным
  дисплеем: `xvfb-run -a python main.py` (в systemd — `ExecStart=/usr/bin/xvfb-run
  -a .../python main.py` и `Environment=BROWSER_HEADLESS=false`);
- флаги `--no-sandbox`, `--disable-dev-shm-usage` (root/контейнер, малый /dev/shm);
- одновременных браузеров ограничено семафором (`BROWSER_CLAIM_CONCURRENCY`,
  по умолчанию 3), чтобы сервер не перегружался по RAM;
- браузерный клейм идёт через тот же прокси аккаунта.

Переменные окружения:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `BROWSER_CLAIM_CONCURRENCY` | `3` | сколько браузеров клеймят одновременно |
| `BROWSER_HEADLESS` | `true` | `false` — с окном (нужен дисплей/Xvfb) |
| `BROWSER_CHANNEL` | `chrome` | пусто → bundled chromium |
| `CAMPAIGN_REFRESH_SECONDS` | `7200` | период обновления каталога кампаний |

## Что внутри

- **Аккаунты** — таблица с фильтрами (логин, токен, роль, кампания, прогресс, сезон),
  detail-панель справа, мульти-выбор, импорт по шаблону `{login}:{password}:{token}` и др.,
  экспорт в текст по пользовательскому шаблону, массовое назначение роли,
  редактирование/удаление, попап со всеми кампаниями.
- **Стримеры** — несколько именованных конфигов (как «пилюли»),
  активный конфиг автоматически синхронизируется в `data/streamers.txt`
  (как и в оригинале).
- **Фарм** — старт/стоп, лог в реальном времени через WebSocket,
  карточка на каждый аккаунт с прогрессом и таймером.
  Реальный фарм выполняет Python-майнер `TwitchMiner` (`client.py`):
  валидация токена, инвентарь дропов, `minute-watched` на spade_url/GQL,
  авто-клейм завершённых дропов. См. раздел «Движок фарма».

## API

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/api/accounts` | все аккаунты |
| POST | `/api/accounts` | создать |
| PUT | `/api/accounts/{login}` | обновить |
| DELETE | `/api/accounts/{login}` | удалить |
| POST | `/api/accounts/import` | импорт по шаблону |
| POST | `/api/accounts/export` | экспорт по шаблону |
| POST | `/api/accounts/bulk-role` | массовая роль |
| GET | `/api/streamers/configs` | конфиги стримеров |
| POST | `/api/streamers/configs` | создать конфиг |
| PUT | `/api/streamers/configs/{name}` | заменить ники |
| POST | `/api/streamers/configs/{name}/rename` | переименовать |
| DELETE | `/api/streamers/configs/{name}` | удалить |
| POST | `/api/streamers/configs/{name}/activate` | сделать активным |
| GET | `/api/farm/state` | текущее состояние |
| POST | `/api/farm/start` | старт |
| POST | `/api/farm/stop` | стоп |
| WS | `/ws/farm` | live-обновления |

WebSocket-сообщения: `init`, `running`, `card`, `log`, `snapshot`.

## Админ-панель и пользователи (auth)

Вся панель теперь закрыта авторизацией. Пользователи, подписки, лимиты потоков,
сессии и аудит хранятся в SQLite `data/panel.db` (единое хранилище).

### Изоляция пользователей (важно)

Каждый пользователь работает в собственном пространстве — данные и фарм **не
пересекаются** между пользователями:

- **Данные** хранятся отдельно в `data/users/<user_id>/`:
  `accounts.json`, `proxies.json`, `streamer_configs.json`, `streamers.txt`.
  Все `/api/accounts`, `/api/proxies`, `/api/streamers/*` работают только с
  каталогом текущего пользователя — чужие аккаунты не видны и не изменяемы.
- **Фарм** — отдельный движок (`FarmEngine`) на каждого пользователя. Запуск,
  остановка, статус (`running`), карточки и логи относятся только к нему.
- **WebSocket** `/ws/farm` привязан к движку пользователя: события `running`,
  `snapshot`, `card`, `log` получает только владелец. Второй браузер/пользователь
  больше **не видит** чужой фарм (был баг — исправлено).
- **Логи майнеров** маршрутизируются владельцу через `logger.bind(owner, login)`
  и единый глобальный sink; в UI/логи попадает **логин аккаунта, не токен**.
- **Миграция:** старое единое хранилище (`data/accounts.json` и т.п. из прежних
  версий) при первом запуске автоматически переносится в каталог админа
  (`data/users/<admin_id>/`).

### Движок фарма: Python (`client.py`)

Реальный фарм выполняет **Python-майнер** `TwitchMiner` (`client.py`): один
asyncio-таск на аккаунт внутри процесса панели (без браузера, лёгкая модель).
Панель на Python — это одновременно и control plane (auth, пользователи,
подписки, лимиты, хранение данных), и data plane (сам фарм).

- При старте фарма панель создаёт по одному `TwitchMiner` на аккаунт
  пользователя и гоняет их через `asyncio` (со стартовым разбросом `stagger`).
- **Токены** используются только внутри процесса и **не пишутся в логи** — в
  UI/логи идёт логин аккаунта, а не токен (`logger.bind(owner, login)`).
- **Прогресс** пишется в `data/users/<uid>/accounts.json` (апсерт по кампании) —
  вкладка «Аккаунты» и карточки фарма читают его одинаково.
- **Изоляция**: у каждого пользователя свой `FarmEngine`, свои майнеры, свой
  `/ws/farm`. Стоп одного пользователя не трогает других.

Тюнинг раннера (из `config.py`): `watch_interval`, `inventory_check_minutes`,
`offline_check_interval`, `connection_timeout`.

### Исправление «зависаний» дропов

Раньше `broadcast_id` и `spade_url` брались один раз на весь просмотр. За часы
стрим мог перезапуститься (новый `broadcast_id`) — тогда `minute-watched`
отвечал 200, но прогресс молча не начислялся, и дроп «не дофармливался» до
полного перезапуска. Исправлено в обоих движках:
- периодическое обновление `broadcast_id` (по умолчанию каждые 15 мин);
- сторож прогресса: если инвентарь не растёт заданное время (по умолчанию
  20 мин wall-clock) — стрим переизбирается (свежая сессия);
- завершённые дропы теперь **авто-клеймятся** (раньше висели на 100%).

### Первый вход (bootstrap админа)
При первом запуске, если пользователей нет, создаётся администратор:
- логин/пароль из env `PANEL_ADMIN_USER` / `PANEL_ADMIN_PASSWORD`, **или**
- если пароль не задан — генерируется случайный и пишется в
  `data/INITIAL_ADMIN.txt` (смените его после входа).

### Роли и лимиты
Админка — **отдельная страница** `/admin` (не вкладка). В основной панели у
каждого пользователя в шапке показывается его лимит потоков и статус подписки
(«Потоки: N · Подписка: до … (X дн.)»). Кнопка **Admin** в шапке видна только
администраторам и ведёт на `/admin`; обычный пользователь при заходе на `/admin`
перенаправляется в панель, а все `/api/admin/*` закрыты на сервере.
- `admin` — доступ к странице **/admin**: создание/редактирование/удаление
  пользователей, лимит потоков, роль, включён/выключен, **длительность подписки**
  (установить N дней или продлить), сброс пароля, ручной бэкап, журнал безопасности.
- `user` — обычный доступ к панели; ограничен своим `thread_limit` (кол-во
  одновременно фармящихся аккаунтов) и сроком подписки (по истечении — вход/работа
  блокируются).

### Защита входа
PBKDF2-HMAC-SHA256 (200k) + соль; сравнение в постоянном времени; параметризованный
SQL; строгая валидация ввода; серверные сессии (HttpOnly/SameSite=Strict cookie,
хранится только хэш токена); регенерация сессии при логине (anti-fixation);
CSRF (double-submit + серверная проверка `X-CSRF-Token`); rate-limit по IP и логину
с экспоненциальной блокировкой; generic-ошибки + выровненный тайминг (anti-enumeration);
опциональная 2FA (TOTP); security-заголовки (CSP, X-Frame-Options: DENY и т.д.);
аудит всех попыток входа.

### Переменные окружения
```
PANEL_ADMIN_USER, PANEL_ADMIN_PASSWORD   # bootstrap первого админа
PANEL_SESSION_TTL=43200                   # срок сессии, сек (12ч)
PANEL_COOKIE_SECURE=1                     # ставить Secure на cookie (для HTTPS)
PANEL_LOGIN_MAX_ATTEMPTS=5, PANEL_LOGIN_WINDOW=300
PANEL_LOCK_BASE=30, PANEL_LOCK_MAX=3600   # блокировка при брутфорсе
# бэкапы в Telegram:
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
PANEL_BACKUP_INTERVAL_HOURS=6             # 0 = выключить авто-бэкап
PANEL_BACKUP_INCLUDE_ACCOUNTS=0          # 1 = прикладывать и data/accounts.json
```

### Бэкапы в Telegram
`backup.py` шлёт JSON с пользователями и подписками в Telegram-бота
(`sendDocument`): автоматически по расписанию, при изменении пользователей и по
кнопке **«Backup now»**. Настраивается через `TELEGRAM_BOT_TOKEN` /
`TELEGRAM_CHAT_ID` (создайте бота у @BotFather, узнайте chat_id). Без этих
переменных бэкапы просто отключены.

### Новые эндпоинты
| Метод | Путь | Назначение |
|-------|------|------------|
| POST | `/api/auth/login` | вход (username, password, totp?) |
| POST | `/api/auth/logout` | выход |
| GET | `/api/auth/me` | текущий пользователь + csrf |
| GET | `/api/admin/users` | список пользователей |
| POST | `/api/admin/users` | создать пользователя |
| PUT | `/api/admin/users/{id}` | обновить (роль/лимит/подписка/enabled) |
| POST | `/api/admin/users/{id}/password` | сброс пароля |
| DELETE | `/api/admin/users/{id}` | удалить |
| GET | `/api/admin/audit` | журнал безопасности |
| GET | `/api/admin/backup/status` | статус Telegram-бэкапов |
| POST | `/api/admin/backup` | ручной бэкап сейчас |

## Чтобы подключить реальный фармер

В `main.py` найди класс `FarmEngine` и метод `_loop`. Замени имитацию реальными
вызовами и шли изменения через `self.broadcast({"type":"card", ...})`
и `self._log(login, "info", "...")`.
