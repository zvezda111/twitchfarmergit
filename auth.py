"""Authentication, panel users, sessions and login hardening.

Всё хранится в SQLite (``data/panel.db``) — единое хранилище для всех
пользователей панели, их подписок, лимитов потоков и сессий.

Защита входа в панель:
  * PBKDF2-HMAC-SHA256 (200k итераций) + индивидуальная соль на пользователя;
  * сравнение хэшей в постоянном времени (``hmac.compare_digest``) — против
    timing-атак;
  * все SQL-запросы параметризованы (плейсхолдеры sqlite3) — против SQL-инъекций;
  * строгая типизация/валидация ввода (pydantic + regex, лимиты длины) — против
    type-juggling / NoSQL-инъекций / переполнения;
  * серверные сессии со случайным токеном (``secrets``), хранится только SHA-256
    от токена; регенерация сессии при логине — против session fixation;
  * rate-limit по IP и по логину + экспоненциальная блокировка — против брутфорса;
  * одинаковые (generic) ошибки и выровненный тайминг (dummy-hash) — против
    перечисления пользователей (user enumeration);
  * опциональная 2FA (TOTP, RFC 6238) без внешних зависимостей;
  * проверки ``enabled`` и срока подписки при каждом запросе;
  * аудит-лог всех попыток входа.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import struct
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ───────── конфигурация (через env, без хардкода секретов) ──────────────────
PBKDF2_ITERATIONS = 200_000
SESSION_TTL_SECONDS = int(os.getenv("PANEL_SESSION_TTL", str(12 * 3600)))
COOKIE_SECURE = os.getenv("PANEL_COOKIE_SECURE", "0") in ("1", "true", "True")
SESSION_COOKIE = "sid"
CSRF_COOKIE = "csrf"

# rate-limit параметры
LOGIN_MAX_ATTEMPTS = int(os.getenv("PANEL_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(os.getenv("PANEL_LOGIN_WINDOW", "300"))
LOCK_BASE_SECONDS = int(os.getenv("PANEL_LOCK_BASE", "30"))
LOCK_MAX_SECONDS = int(os.getenv("PANEL_LOCK_MAX", "3600"))

MAX_FIELD_LEN = 256
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")

# фиктивный хэш для выравнивания тайминга при несуществующем пользователе
_DUMMY_HASH = hashlib.pbkdf2_hmac(
    "sha256", b"dummy-password", b"dummy-salt-16byt", PBKDF2_ITERATIONS
)


@dataclass
class User:
    id: int
    username: str
    role: str
    thread_limit: int
    subscription_until: Optional[float]
    enabled: bool
    totp_enabled: bool
    created_at: float
    last_login: Optional[float]
    proxy_mode: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def subscription_active(self) -> bool:
        if self.is_admin:
            return True
        if self.subscription_until is None:
            return False
        return self.subscription_until > time.time()

    def public(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "thread_limit": self.thread_limit,
            "subscription_until": self.subscription_until,
            "subscription_active": self.subscription_active,
            "enabled": self.enabled,
            "totp_enabled": self.totp_enabled,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "proxy_mode": self.proxy_mode,
        }


class AuthError(Exception):
    """Ошибка аутентификации/авторизации с http-статусом."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ───────── хранилище ────────────────────────────────────────────────────────
class AuthStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    pass_hash BLOB NOT NULL,
                    salt BLOB NOT NULL,
                    iterations INTEGER NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    thread_limit INTEGER NOT NULL DEFAULT 1,
                    subscription_until REAL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    totp_secret TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_login REAL,
                    proxy_mode TEXT NOT NULL DEFAULT 'own'
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    ip TEXT,
                    user_agent TEXT
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    event TEXT NOT NULL,
                    username TEXT,
                    ip TEXT,
                    detail TEXT
                );
                """
            )
            columns = {
                row["name"]
                for row in self._conn.execute("PRAGMA table_info(users)").fetchall()
            }
            if "proxy_mode" not in columns:
                self._conn.execute(
                    "ALTER TABLE users ADD COLUMN proxy_mode TEXT NOT NULL DEFAULT 'own'"
                )

    # ── хэши паролей ────────────────────────────────────────────────────
    @staticmethod
    def _hash_password(password: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )

    # ── пользователи ────────────────────────────────────────────────────
    def _row_to_user(self, row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            thread_limit=row["thread_limit"],
            subscription_until=row["subscription_until"],
            enabled=bool(row["enabled"]),
            totp_enabled=bool(row["totp_secret"]),
            created_at=row["created_at"],
            last_login=row["last_login"],
            proxy_mode=row["proxy_mode"] if row["proxy_mode"] in ("own", "pool") else "own",
        )

    def create_user(
        self,
        username: str,
        password: str,
        role: str = "user",
        thread_limit: int = 1,
        subscription_days: Optional[float] = None,
        enabled: bool = True,
        proxy_mode: str = "own",
    ) -> User:
        username = validate_username(username)
        validate_password(password)
        if role not in ("admin", "user"):
            raise AuthError(400, "invalid role")
        if proxy_mode not in ("own", "pool"):
            raise AuthError(400, "invalid proxy_mode")
        thread_limit = clamp_thread_limit(thread_limit)
        sub_until = None
        if subscription_days is not None and subscription_days > 0:
            sub_until = time.time() + float(subscription_days) * 86400
        salt = secrets.token_bytes(16)
        pass_hash = self._hash_password(password, salt, PBKDF2_ITERATIONS)
        now = time.time()
        with self._lock:
            try:
                cur = self._conn.execute(
                    """INSERT INTO users
                       (username, pass_hash, salt, iterations, role, thread_limit,
                       subscription_until, enabled, created_at, updated_at, proxy_mode)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        username, pass_hash, salt, PBKDF2_ITERATIONS, role,
                        thread_limit, sub_until, int(enabled), now, now, proxy_mode,
                    ),
                )
            except sqlite3.IntegrityError as e:
                raise AuthError(409, "username already exists") from e
            return self.get_user(cur.lastrowid)  # type: ignore[arg-type]

    def get_user(self, user_id: int) -> Optional[User]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE id=?", (user_id,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_name(self, username: str) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM users WHERE username=?", (username,)
            ).fetchone()

    def list_users(self) -> list[User]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM users ORDER BY id"
            ).fetchall()
        return [self._row_to_user(r) for r in rows]

    def count_users(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def count_admins(self, exclude_id: Optional[int] = None) -> int:
        with self._lock:
            if exclude_id is None:
                return self._conn.execute(
                    "SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1"
                ).fetchone()[0]
            return self._conn.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1 AND id!=?",
                (exclude_id,),
            ).fetchone()[0]

    def update_user(
        self,
        user_id: int,
        *,
        role: Optional[str] = None,
        thread_limit: Optional[int] = None,
        enabled: Optional[bool] = None,
        subscription_until: Optional[float] = None,
        add_subscription_days: Optional[float] = None,
        proxy_mode: Optional[str] = None,
    ) -> User:
        user = self.get_user(user_id)
        if not user:
            raise AuthError(404, "user not found")
        sets: list[str] = []
        args: list = []
        if role is not None:
            if role not in ("admin", "user"):
                raise AuthError(400, "invalid role")
            sets.append("role=?")
            args.append(role)
        if proxy_mode is not None:
            if proxy_mode not in ("own", "pool"):
                raise AuthError(400, "invalid proxy_mode")
            sets.append("proxy_mode=?")
            args.append(proxy_mode)
        if thread_limit is not None:
            sets.append("thread_limit=?")
            args.append(clamp_thread_limit(thread_limit))
        if enabled is not None:
            sets.append("enabled=?")
            args.append(int(bool(enabled)))
        if subscription_until is not None:
            sets.append("subscription_until=?")
            args.append(subscription_until if subscription_until > 0 else None)
        if add_subscription_days is not None:
            base = max(user.subscription_until or 0, time.time())
            sets.append("subscription_until=?")
            args.append(base + float(add_subscription_days) * 86400)
        if not sets:
            return user
        sets.append("updated_at=?")
        args.append(time.time())
        args.append(user_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE users SET {', '.join(sets)} WHERE id=?", tuple(args)
            )
        return self.get_user(user_id)  # type: ignore[return-value]

    def set_password(self, user_id: int, password: str) -> None:
        validate_password(password)
        salt = secrets.token_bytes(16)
        pass_hash = self._hash_password(password, salt, PBKDF2_ITERATIONS)
        with self._lock:
            self._conn.execute(
                "UPDATE users SET pass_hash=?, salt=?, iterations=?, updated_at=? WHERE id=?",
                (pass_hash, salt, PBKDF2_ITERATIONS, time.time(), user_id),
            )
        # разлогинить все сессии пользователя после смены пароля
        self.delete_user_sessions(user_id)

    def set_totp_secret(self, user_id: int, secret: Optional[str]) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET totp_secret=?, updated_at=? WHERE id=?",
                (secret, time.time(), user_id),
            )

    def get_totp_secret(self, user_id: int) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT totp_secret FROM users WHERE id=?", (user_id,)
            ).fetchone()
        return row["totp_secret"] if row else None

    def delete_user(self, user_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM users WHERE id=?", (user_id,))

    def touch_login(self, user_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET last_login=? WHERE id=?", (time.time(), user_id)
            )

    # ── проверка пароля (постоянное время + анти-enumeration) ────────────
    def verify_credentials(self, username: str, password: str) -> Optional[sqlite3.Row]:
        row = self.get_user_by_name(username)
        if row is None:
            # выравниваем тайминг, чтобы нельзя было различить
            # «нет пользователя» и «неверный пароль»
            hmac.compare_digest(
                _DUMMY_HASH,
                self._hash_password(password, b"dummy-salt-16byt", PBKDF2_ITERATIONS),
            )
            return None
        candidate = self._hash_password(password, row["salt"], row["iterations"])
        if hmac.compare_digest(candidate, row["pass_hash"]):
            return row
        return None

    # ── сессии ──────────────────────────────────────────────────────────
    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_session(
        self, user_id: int, ip: str, user_agent: str
    ) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO sessions
                   (token_hash, user_id, csrf, created_at, expires_at, ip, user_agent)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    self._token_hash(token), user_id, csrf, now,
                    now + SESSION_TTL_SECONDS, ip, user_agent[:MAX_FIELD_LEN],
                ),
            )
        return token, csrf

    def get_session(self, token: str) -> Optional[sqlite3.Row]:
        if not token:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE token_hash=?",
                (self._token_hash(token),),
            ).fetchone()
        if not row:
            return None
        if row["expires_at"] < time.time():
            self.delete_session(token)
            return None
        return row

    def delete_session(self, token: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM sessions WHERE token_hash=?", (self._token_hash(token),)
            )

    def delete_user_sessions(self, user_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))

    def purge_expired_sessions(self) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM sessions WHERE expires_at < ?", (time.time(),)
            )

    # ── аудит ───────────────────────────────────────────────────────────
    def audit(
        self, event: str, username: str, ip: str, detail: str = ""
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit_log (ts, event, username, ip, detail) VALUES (?,?,?,?,?)",
                (time.time(), event, username[:MAX_FIELD_LEN], ip, detail[:MAX_FIELD_LEN]),
            )

    def recent_audit(self, limit: int = 100) -> list[dict]:
        limit = max(1, min(500, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, event, username, ip, detail FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── экспорт для бэкапа ──────────────────────────────────────────────
    def export_backup(self) -> dict:
        """Полный дамп пользователей и подписок (хэши включены — бэкап
        восстановим, пароли не в открытом виде)."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        users = []
        for r in rows:
            users.append(
                {
                    "id": r["id"],
                    "username": r["username"],
                    "pass_hash": base64.b64encode(r["pass_hash"]).decode(),
                    "salt": base64.b64encode(r["salt"]).decode(),
                    "iterations": r["iterations"],
                    "role": r["role"],
                    "thread_limit": r["thread_limit"],
                    "subscription_until": r["subscription_until"],
                    "enabled": bool(r["enabled"]),
                    "totp_enabled": bool(r["totp_secret"]),
                    "created_at": r["created_at"],
                    "last_login": r["last_login"],
                }
            )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "user_count": len(users),
            "users": users,
        }


# ───────── rate limiter (in-memory, по IP и по логину) ──────────────────────
class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (attempts:list[float], locked_until:float)
        self._buckets: dict[str, tuple[list[float], float]] = {}

    def _key_state(self, key: str) -> tuple[list[float], float]:
        return self._buckets.get(key, ([], 0.0))

    def check(self, key: str) -> float:
        """Вернёт 0.0 если можно, иначе сколько секунд ждать (>0)."""
        now = time.time()
        with self._lock:
            attempts, locked_until = self._key_state(key)
            if locked_until > now:
                return locked_until - now
        return 0.0

    def record_failure(self, key: str) -> float:
        now = time.time()
        with self._lock:
            attempts, locked_until = self._key_state(key)
            attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
            attempts.append(now)
            if len(attempts) >= LOGIN_MAX_ATTEMPTS:
                over = len(attempts) - LOGIN_MAX_ATTEMPTS
                lock = min(LOCK_BASE_SECONDS * (2 ** over), LOCK_MAX_SECONDS)
                locked_until = now + lock
                attempts = []
            self._buckets[key] = (attempts, locked_until)
            return max(0.0, locked_until - now)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def record_cooldown(self, key: str, seconds: float) -> None:
        now = time.time()
        with self._lock:
            attempts, locked_until = self._key_state(key)
            self._buckets[key] = (attempts, max(locked_until, now + seconds))


# ───────── валидаторы ввода ──────────────────────────────────────────────────
def validate_username(username: str) -> str:
    if not isinstance(username, str):
        raise AuthError(400, "invalid username")
    username = username.strip()
    if len(username) > MAX_FIELD_LEN or not USERNAME_RE.match(username):
        raise AuthError(
            400, "username must be 3-32 chars: letters, digits, . _ -"
        )
    return username


def validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise AuthError(400, "invalid password")
    if not (8 <= len(password) <= MAX_FIELD_LEN):
        raise AuthError(400, "password must be 8-256 chars")


def clamp_thread_limit(value: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise AuthError(400, "invalid thread_limit") from None
    return max(0, min(10_000, value))


# ───────── TOTP (RFC 6238, без зависимостей) ────────────────────────────────
def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8").rstrip("=")


def _totp_at(secret: str, counter: int) -> str:
    padding = "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(secret.upper() + padding)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    if not code or not code.isdigit():
        return False
    counter = int(time.time() // 30)
    for delta in range(-window, window + 1):
        if hmac.compare_digest(_totp_at(secret, counter + delta), code.zfill(6)):
            return True
    return False


def totp_uri(secret: str, username: str, issuer: str = "TwitchFarmerPanel") -> str:
    return (
        f"otpauth://totp/{issuer}:{username}?secret={secret}"
        f"&issuer={issuer}&period=30&digits=6"
    )
