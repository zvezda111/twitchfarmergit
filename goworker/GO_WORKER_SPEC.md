# Go farm worker — golden behavior spec

Goal: replace only the **mobile-token farm worker** (`farm_worker.py` + `client.py` mobile
path) with a Go binary. Everything else stays Python:

- authentication, DB, API, user isolation, UI — **Python**;
- web→mobile conversion (browser/Playwright) — **Python** (`convert_worker.py`);
- web-token drop claiming via browser — **Python** (stays in `client.py`);
- streamer resolution before farm start (`resolve_streamers`) — **Python** (done in
  `FarmEngine.start` before the worker is launched).

By the time the worker runs, **all accounts handed to it are mobile tokens** (web tokens are
either converted first or skipped). So the Go worker only needs the **Android/mobile HTTP path**
— no browser, no Kasada, no integrity.

---

## 1. Process contract (how Python launches the worker today)

`FarmEngine.start` (main.py) currently spawns a Python process:

```
run_worker(owner_id, accounts, proxies, streamers, config_values, event_queue, stagger)
```

- `accounts`: `[{"login": str, "token": str}, ...]` — mobile tokens only.
- `proxies`: `[{scheme,host,port,username,password,raw}, ...]` (farm proxies; may be empty).
- `streamers`: `["login1","login2",...]` already resolved for the selected campaigns.
- `config_values`: dict below.
- `event_queue`: `multiprocessing.Queue`; worker `.put()`s event dicts, parent drains them.
- `stagger`: float seconds between miner starts.

`config_values` (exact keys):
```json
{
  "connection_timeout": 30,
  "retry_delay": 5,
  "max_retries": 3,
  "watch_interval": 60,
  "inventory_refresh": 300,
  "inventory_check_minutes": 1,
  "offline_check_interval": 120,
  "data_dir": "<abs path data/users/<uid>>"
}
```

### Transport for Go
Go cannot use a Python `multiprocessing.Queue`. Use **NDJSON over stdout**:
launch the Go binary as a subprocess; pass the full job as **one JSON object on stdin**;
the Go worker writes **one JSON event per line to stdout**. Parent reads stdout line by line
and feeds the existing event handling. stderr is for internal diagnostics only and must never
contain tokens/proxy creds.

Job JSON on stdin (new, Go-only):
```json
{
  "owner_id": 7,
  "accounts": [{"login":"...","token":"..."}],
  "proxies": [{"scheme":"http","host":"...","port":1080,"username":"...","password":"..."}],
  "streamers": ["a","b"],
  "config": { ...config_values... },
  "stagger": 5.0
}
```

Process group / stop: worker must call `setsid` equivalent (start new process group) so the
parent can `SIGTERM`/`SIGKILL` the whole group — identical to `os.setsid()` in Python workers.
On SIGTERM, stop all miners gracefully, close sessions, exit 0.

---

## 2. Events emitted

The parent consumes `log`, `card`, and `progress` events. Tokens/proxy creds must NEVER
appear in any event.

### `log`
```json
{"type":"log","login":"<account login | 'system'>","level":"info|warn|error","message":"..."}
```
- Parent truncates message to 500 chars.
- `login:"system"` for worker-level lifecycle logs.
- Per-account logs use the account **login**, never the token.

System logs the parent expects at least once (order matters for the UI):
- `"starting miner for <login> (<i>/<n>)"` per account as it starts.

### `card`
```json
{"type":"card","login":"<login>","current_game":"<str|null>","watch_minutes":<int>}
```
- Emitted for every miner ~once per second (steady cadence). Parent throttles/repaints itself.
- `current_game` = currently-watched stream's game name, or null when not watching.
- `watch_minutes` = accumulated watched minutes for the current stream (resets when a new
  stream starts — see watch_stream).

The parent recomputes card campaign data from the DB using `current_game`, while the worker
supplies live inventory progress through the event below.

### `progress`
```json
{
  "type": "progress",
  "login": "<login>",
  "progress": [
    {
      "campaign": "<campaign name>",
      "drop": "<drop name>",
      "game_id": "<game id>",
      "game_name": "<game name>",
      "current": 34,
      "required": 120,
      "status": "in_progress|ready|claimed"
    }
  ]
}
```
- Emitted after an Inventory refresh only when the account's reported inventory
  progress changes.
- `current`/`required` are Twitch's `currentMinutesWatched` and
  `requiredMinutesWatched` values.
- `status` is `claimed`, `ready`, or `in_progress`.
- `campaign` and `drop` identify the stored campaign/drop; `game_id` and `game_name`
  disambiguate campaigns with repeated drop names.

---

## 3. HTTP identity (per miner) — Android app

Constants:
```
GQL_URL      = https://gql.twitch.tv/gql
VALIDATE_URL = https://id.twitch.tv/oauth2/validate
CLIENT_ID    = kd1unb4b3q4t58fwlpcbzcbnm76a8fp
USER_AGENT   = Dalvik/2.1.0 (Linux; U; Android 13; SM-G991B Build/TP1A.220624.014) tv.twitch.android.app/29.9.1/2909016
```

Per miner random IDs (generate once at construction):
- `device_id`: 32 lowercase hex chars (overwrite with `unique_id` cookie if the initial
  `GET https://www.twitch.tv` returns one).
- `session_id`: 16 lowercase hex chars.
- (`play_session_id`/`app_session_id` exist in Python but are unused by the mobile path; skip.)

Integrity/Kasada: **NOT required** for the Android path. Do not implement.

### Session bootstrap (`_create_session`)
- Base headers on the session: `Client-Id`, `User-Agent`, `Accept-Language: en-US`.
- `GET https://www.twitch.tv` (through proxy) to pick up `unique_id` cookie → `device_id`.
  Failure is non-fatal.

### GQL request (`_gql_request`)
`POST https://gql.twitch.tv/gql` with body `[operation]` (single-element array) and headers:
```
Accept: */*
Accept-Language: en-US
Authorization: OAuth <token>
Client-Id: kd1unb4b3q4t58fwlpcbzcbnm76a8fp
Client-Session-Id: <session_id>
User-Agent: <USER_AGENT>
X-Device-Id: <device_id>
Origin: https://www.twitch.tv
Referer: https://www.twitch.tv/
```
- Response is an array → take `[0]`.
- If `"errors"` present → raise with `errors[0].message`.

### Proxy
- HTTP request proxy URL: `scheme://[user:pass@]host:port` (URL-encode user/pass).
- Round-robin: `proxy = proxies[index % len(proxies)]` per miner; none if list empty.

---

## 4. Persisted GQL operations (exact hashes — do not change)

| purpose | operationName | sha256Hash |
|---|---|---|
| inventory | `Inventory` (`variables:{fetchRewardCampaigns:false}`) | `d86775d0ef16a63a33ad52e80eaff963b2d5b72fada7c991504a57496e1d8e4b` |
| stream info / online | `VideoPlayerStreamInfoOverlayChannel` (`variables:{channel:<login>}`) | `198492e0857f6aedead9665c81c5a06d67b25b58034649687124083ff288597d` |
| claim (API) | `DropsPage_ClaimDropRewards` (`variables:{input:{dropInstanceID:<id>}}`) | `a455deea71bdc9015b78eb49f4acfbce8baa7ccbedd28e549bb025bd0f751930` |

Stream game fallback uses a raw query string:
`{ user(login: "<login>") { stream { id game { id name } } } }`.

---

## 5. Model semantics (from models.py — reimplement in Go)

Drop:
- `progress = required==0 ? 100 : min(100, current/required*100)`
- `can_earn = !is_claimed && current < required`
- `can_claim = !is_claimed && current >= required && claim_id != null`

Campaign filtering at inventory time (fetch_inventory):
- skip `status=="EXPIRED"`; skip `ends_at < now`; skip `starts_at > now+24h`.
- for each drop with `can_earn||can_claim`, look up `dropInstanceID` from `timeBasedDrops[].self`
  and set `claim_id`; skip drops whose `claim_id` is already in the session `_claimed_instances`
  set; else add to `active_drops` keyed by drop id.

Timestamps: parse `%Y-%m-%dT%H:%M:%S.%fZ` and fallback `%Y-%m-%dT%H:%M:%SZ` (UTC).

---

## 6. Miner lifecycle (`run`) — reproduce exactly

1. `_create_session()`.
2. `validate_token()`: `GET VALIDATE_URL` with `Authorization: OAuth <token>`.
   - 401 → log "аккаунт невалиден: токен отклонён", stop this miner.
   - else read `user_id`, `login`; `is_mobile = client_id == CLIENT_ID`.
   - For Go worker, all tokens are mobile; if somehow not mobile, still farm via API (claims
     would fail, but that's the web path we don't handle here — log and continue).
3. Connect PubSub WebSocket (see §8). Non-fatal on failure.
4. `fetch_inventory()`; `_claim_completed()`.
5. If no active drops → `_handle_no_active_drops()` (activation, §7).
6. Main loop while running:
   - `drops_to_farm = active_drops where can_earn`.
   - if empty: if there are active_drops log "подходящих дропов нет, жду обновления данных";
     sleep `offline_check_interval`; `fetch_inventory`; `_claim_completed`; if still no active
     drops → `_handle_no_active_drops`; continue.
   - else log `фармлю N дропов, ищу онлайн-стримера`; iterate `streamers` round-robin from
     index `idx`, calling `check_streamer_online`; on first online channel → `watch_stream`;
     advance idx. If none of the streamers online after a full pass → log "онлайн-стримеров нет,
     жду <offline_check_interval> секунд", sleep, reset idx=0.
   - on exception: log "ошибка основного цикла фарма: <e>", sleep 30.

### check_streamer_online
`VideoPlayerStreamInfoOverlayChannel`; null user → "не найден"; null stream → "офлайн";
else build Channel (id, login, displayName, viewersCount) + game (from `stream.game` or
`_get_stream_game` fallback). Logs "стример X онлайн (V зрителей), игра: G" when `log_online`.

---

## 7. watch_stream (the heart of farming)

On entry set `watching_channel`, `current_game=null`, `watch_minutes=0`.
- `broadcast_id = _get_broadcast_id(channel)`; if none → log "недоступен, просмотр не начат",
  return.
- `spade_url = _get_spade_url(channel)` (may be null → fallback path).
- set `current_game`; log "смотрю X: играет G".
- Loop while running and still watching same channel:
  - `drops_to_farm = active where can_earn`; if empty → log "все доступные дропы нафармлены",
    break.
  - every `refresh_broadcast_minutes=15` watched minutes: re-fetch broadcast_id; if changed,
    drop cached spade_url and refetch (handles stream restart → silent no-progress bug).
  - `_send_watch_progress(channel, broadcast_id, spade_url)`; on success `watch_minutes++` and
    log "смотрю X: N мин (прогресс claimable/total)".
  - every `inventory_check_minutes` (=1) watched minutes: `fetch_inventory` + `_claim_completed`;
    then progress-stall watchdog: keep a snapshot of `{drop_id: current_minutes}` for can_earn
    drops; if progress advanced (any grew, or a drop left the set) reset `last_advance`; else if
    `now - last_advance >= stall_window_min(20)*60` → log "прогресс не меняется 20 минут,
    выбираю другого стримера", break.
  - `_check_stream_online(channel)`; if offline → log "офлайн, просмотр остановлен", break.
  - sleep `watch_interval` (=60).
- On exit: log "просмотр X завершён, всего N мин"; clear watching_channel/current_game.

### _get_broadcast_id
`VideoPlayerStreamInfoOverlayChannel`; return `user.stream.id` or null; also refresh game.

### _get_spade_url (cached per channel)
- GET `https://www.twitch.tv/<login>`; regex `"spade_?url": ?"(https://...)"`.
- if not found, regex settings JS `src="(https://.../config/settings.<32hex>.js)"`, GET it,
  regex spade again. Cache by channel id.

### _send_watch_progress
Build minute-watched properties (exact keys):
```
broadcast_id, channel_id, channel(login), client_time(ISO ms, Z), game(name), game_id,
hidden:false, is_live:true, live:true, logged_in:true, minutes_logged:1, muted:false, user_id
```
Payload = `[{"event":"minute-watched","properties":{...}}]`.
- Primary: `POST spade_url` form field `data = base64(json)`; success on 200/204.
- Fallback (or if no spade_url): GQL `sendSpadeEvents` mutation with
  `input.data = base64(gzip(json))`, `repository:"twilight"`, `encoding:"GZIP_B64"`; success if
  `sendSpadeEvents.statusCode ∈ (200,204)`. (Full mutation query string is in client.py.)

---

## 8. PubSub WebSocket (ws.py)

- `wss://pubsub-edge.twitch.tv/v1`.
- On connect: LISTEN topics `user-drop-events.<user_id>`, `onsite-notifications.<user_id>` with
  `auth_token = <token>`.
- Ping `{"type":"PING"}` every 180s.
- On `RECONNECT` → disconnect, sleep 1, reconnect.
- On MESSAGE `user-drop-events`:
  - `drop-progress` → update `active_drops[drop_id].current_minutes = current_progress_min`.
  - `drop-claim` → set `claim_id = drop_instance_id`; mobile → `_claim_drop_api(drop)`.
- All failures swallowed (best-effort); WS is an optimization, polling still covers progress.

---

## 9. Claiming (mobile only in Go)

`_claim_completed`: claimable = active where can_claim and claim_id not already claimed.
Mobile → per drop `_claim_drop_api`.

`_claim_drop_api`: `DropsPage_ClaimDropRewards` with `dropInstanceID`. Success statuses:
`ELIGIBLE_FOR_ALL`, `DROP_INSTANCE_ALREADY_CLAIMED` → mark claimed, add claim_id to
`_claimed_instances`, remove from active_drops, log "дроп заклеймлен: <name>".
Other/no result → log accordingly, return false.

(Web-token browser claim `_claim_all_browser` stays in Python and is NOT part of the Go worker.)

---

## 10. Cards publisher

Separate ticker per worker: every 1s emit a `card` event for each miner with its current
`current_game` and `watch_minutes`. Runs for the life of the worker.

---

## 11. Startup / stagger

For each miner in order: emit system log "starting miner for <login> (i/n)"; start miner
goroutine; if `stagger>0` and not last, sleep `stagger` seconds between starts.

---

## 12. Verification plan (one account, before any scale)

1. Build Go worker; run standalone with a job JSON for **one** mobile account + selected
   campaign streamers; capture stdout NDJSON.
2. Run the Python worker on the **same** account; capture its events.
3. Compare: same log milestones, `current_game` matches when watching, `watch_minutes`
   increments once/min, inventory/claim behavior equivalent, drop actually progresses on Twitch.
4. Integrate behind a flag (`FARM_ENGINE=go|python`, default **python**). Only flip default
   after the one-account comparison passes and a human review of the diff.
5. Keep Python worker as fallback indefinitely.

## 13. Security invariants (unchanged)
- Never emit tokens, proxy creds, passwords, device/user codes in stdout events, stderr, or logs.
- Per-account routing keyed by **login**, never token. No cross-account/user leakage.
