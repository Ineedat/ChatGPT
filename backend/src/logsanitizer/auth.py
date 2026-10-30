"""Local-only account and server-side session support."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from logsanitizer.deployment import load_settings
from logsanitizer.ldap_auth import LDAPAuthenticationError, authenticate_ldap

COOKIE = "logsanitizer_session"
CSRF = "logsanitizer_csrf"
TTL = 28800
ROLES = {"admin", "rule_owner", "operator", "reviewer", "approver"}
LOGIN_FAILURE_LIMIT = 5
LOGIN_WINDOW_SECONDS = 300
LOGIN_LOCK_SECONDS = 300
router = APIRouter(prefix="/api/auth", tags=["authentication"])

def _path():
    base = Path(os.environ.get("LOGSANITIZER_DATA_DIR", str(Path.home()/".logsanitizer"))).expanduser()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    try: os.chmod(base, 0o700)
    except OSError: pass
    return base/"auth.sqlite3"

@contextmanager
def _db():
    db = sqlite3.connect(_path(), timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def initialize_auth_database():
    with _db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS user_roles(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, role TEXT NOT NULL, PRIMARY KEY(user_id,role));
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
        CREATE TABLE IF NOT EXISTS login_attempts(
            attempt_key TEXT PRIMARY KEY,
            window_started INTEGER NOT NULL,
            failures INTEGER NOT NULL DEFAULT 0,
            locked_until INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS external_identities(
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            external_username TEXT NOT NULL UNIQUE COLLATE NOCASE
        );
        """)
        now = int(time.time())
        db.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
        db.execute(
            "DELETE FROM login_attempts WHERE window_started<=?",
            (now - 2 * LOGIN_WINDOW_SECONDS,),
        )
    try: os.chmod(_path(), 0o600)
    except OSError: pass

def _hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return "scrypt$" + salt.hex() + "$" + value.hex()

def _verify(password, encoded):
    try:
        scheme, salt, expected = encoded.split("$", 2)
        return scheme == "scrypt" and hmac.compare_digest(hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1), bytes.fromhex(expected))
    except (ValueError, TypeError): return False

def create_user(username: str, password: str, roles: list[str]) -> int:
    initialize_auth_database()
    username = username.strip()
    if not username or len(username)>80 or any(ord(c)<32 for c in username): raise ValueError("Username must contain 1–80 printable characters.")
    if len(password)<12: raise ValueError("Password must contain at least 12 characters.")
    if not roles or len(set(roles))!=len(roles) or not set(roles)<=ROLES: raise ValueError("At least one valid role is required.")
    with _db() as db:
        cur=db.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",(username,_hash(password),int(time.time())))
        uid=int(cur.lastrowid)
        db.executemany("INSERT INTO user_roles(user_id,role) VALUES(?,?)",[(uid,r) for r in roles])
    return uid

def upsert_external_user(username: str, roles: list[str]) -> int:
    """Synchronize an LDAP identity without overwriting local accounts or disabled users."""
    username = username.strip()
    if not username or len(username) > 80 or not roles or not set(roles) <= ROLES:
        raise ValueError("Invalid external identity or role mapping.")
    initialize_auth_database()
    with _db() as db:
        row = db.execute(
            "SELECT id, enabled FROM users WHERE username=? COLLATE NOCASE",
            (username,),
        ).fetchone()
        if row is None:
            cursor = db.execute(
                "INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
                (username, _hash(secrets.token_urlsafe(48)), int(time.time())),
            )
            user_id = int(cursor.lastrowid)
            db.execute(
                "INSERT INTO external_identities(user_id,provider,external_username) VALUES(?,?,?)",
                (user_id, "ldap", username),
            )
        else:
            user_id = int(row["id"])
            identity = db.execute(
                "SELECT provider,external_username FROM external_identities WHERE user_id=?",
                (user_id,),
            ).fetchone()
            if identity is None or identity["provider"] != "ldap":
                raise ValueError("LDAP identity collides with a local account.")
            if not bool(row["enabled"]):
                raise ValueError("LDAP account is disabled locally.")
            if str(identity["external_username"]).casefold() != username.casefold():
                raise ValueError("LDAP identity mismatch.")
            db.execute("DELETE FROM user_roles WHERE user_id=?", (user_id,))
        db.executemany(
            "INSERT INTO user_roles(user_id,role) VALUES(?,?)",
            [(user_id, role) for role in sorted(set(roles))],
        )
    return user_id


def _user(token):
    initialize_auth_database()
    with _db() as db:
        row=db.execute("SELECT u.id,u.username,s.csrf_token FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=1",(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
        if row is None: return None
        roles=[x["role"] for x in db.execute("SELECT role FROM user_roles WHERE user_id=?",(row["id"],))]
    return {"id":row["id"],"username":row["username"],"csrf_token":row["csrf_token"],"roles":roles}

class Login(BaseModel):
    username: str = Field(min_length=1,max_length=80)
    password: str = Field(min_length=1,max_length=1024)
class NewUser(BaseModel):
    username: str = Field(min_length=1,max_length=80)
    password: str = Field(min_length=12,max_length=1024)
    roles: list[str] = Field(min_length=1)

def _login_attempt_key(username: str, client_host: str) -> str:
    material = f"{username.strip().casefold()}|{client_host}".encode()
    return hashlib.sha256(material).hexdigest()


def _login_is_locked(attempt_key: str, now: int) -> bool:
    with _db() as db:
        row = db.execute(
            "SELECT locked_until FROM login_attempts WHERE attempt_key=?",
            (attempt_key,),
        ).fetchone()
    return row is not None and int(row["locked_until"]) > now


def _record_login_failure(attempt_key: str, now: int) -> None:
    with _db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT window_started, failures FROM login_attempts WHERE attempt_key=?",
            (attempt_key,),
        ).fetchone()
        if row is None or now - int(row["window_started"]) >= LOGIN_WINDOW_SECONDS:
            started, failures = now, 1
        else:
            started, failures = int(row["window_started"]), int(row["failures"]) + 1
        locked_until = now + LOGIN_LOCK_SECONDS if failures >= LOGIN_FAILURE_LIMIT else 0
        db.execute(
            """INSERT INTO login_attempts(attempt_key, window_started, failures, locked_until)
               VALUES(?,?,?,?) ON CONFLICT(attempt_key) DO UPDATE SET
               window_started=excluded.window_started, failures=excluded.failures,
               locked_until=excluded.locked_until""",
            (attempt_key, started, failures, locked_until),
        )


@router.post("/login")
def login(payload: Login, request: Request, response: Response):
    settings = load_settings()
    initialize_auth_database()
    client_host = request.client.host if request.client else "unknown"
    attempt_key = _login_attempt_key(payload.username, client_host)
    now = int(time.time())
    if _login_is_locked(attempt_key, now):
        raise HTTPException(429, "Zu viele fehlgeschlagene Anmeldeversuche.")

    if settings["auth"]["provider"] == "ldap":
        try:
            identity = authenticate_ldap(payload.username, payload.password, settings)
            user_id = upsert_external_user(identity["username"], identity["roles"])
        except (LDAPAuthenticationError, ValueError):
            _record_login_failure(attempt_key, now)
            raise HTTPException(401, "Benutzername oder Passwort ungültig.") from None
        user = {"id": user_id}
    else:
        with _db() as db:
            user = db.execute(
                "SELECT id,password_hash FROM users WHERE username=? COLLATE NOCASE AND enabled=1",
                (payload.username.strip(),),
            ).fetchone()
        if user is None or not _verify(payload.password, user["password_hash"]):
            _record_login_failure(attempt_key, now)
            raise HTTPException(401, "Benutzername oder Passwort ungültig.")
        user = {"id": int(user["id"])}

    with _db() as db:
        db.execute("DELETE FROM login_attempts WHERE attempt_key=?", (attempt_key,))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with _db() as db:
        db.execute(
            "DELETE FROM sessions WHERE user_id=? OR expires_at<=?",
            (user["id"], int(time.time())),
        )
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), user["id"], csrf, int(time.time()) + TTL),
        )
    secure = (
        settings["profile"] == "network"
        or os.environ.get("LOGSANITIZER_COOKIE_SECURE", "").casefold() in {"1", "true", "yes"}
    )
    response.set_cookie(
        COOKIE, token, max_age=TTL, httponly=True, secure=secure, samesite="strict", path="/api"
    )
    # The frontend runs at "/" and must be able to read this non-HttpOnly
    # token via document.cookie. Keep the session cookie restricted to /api.
    # Remove the legacy /api-scoped CSRF cookie to avoid duplicate cookie names.
    response.delete_cookie(CSRF, path="/api", samesite="strict")
    response.set_cookie(
        CSRF, csrf, max_age=TTL, httponly=False, secure=secure, samesite="strict", path="/"
    )
    return {"authenticated": True}

@router.post("/logout")
def logout(request: Request, response: Response):
    token=request.cookies.get(COOKIE)
    if token:
        with _db() as db: db.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(COOKIE,path="/api",samesite="strict")
    response.delete_cookie(CSRF,path="/",samesite="strict")
    response.delete_cookie(CSRF,path="/api",samesite="strict")
    return {"authenticated":False}

@router.get("/me")
def me(request: Request):
    user=getattr(request.state,"user",None)
    if user is None: raise HTTPException(401,"Anmeldung erforderlich.")
    return {k:user[k] for k in ("id","username","roles")}

@router.get("/users")
def users():
    initialize_auth_database()
    with _db() as db:
        rows=db.execute("SELECT id,username,enabled,created_at FROM users ORDER BY username").fetchall()
        return [{**dict(row),"roles":[r["role"] for r in db.execute("SELECT role FROM user_roles WHERE user_id=?",(row["id"],))]} for row in rows]

@router.post("/users",status_code=201)
def add_user(payload: NewUser):
    try: uid=create_user(payload.username,payload.password,payload.roles)
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    except sqlite3.IntegrityError as exc: raise HTTPException(409,"Benutzername ist bereits vergeben.") from exc
    return {"id":uid,"username":payload.username.strip(),"roles":payload.roles}

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path,method=request.url.path,request.method.upper()
        if not path.startswith("/api/") or path in {"/api/health","/api/auth/login"}: return await call_next(request)
        token=request.cookies.get(COOKIE)
        user=_user(token) if token else None
        if user is None: return JSONResponse({"detail":"Anmeldung erforderlich."},status_code=401)
        request.state.user=user
        if method not in {"GET","HEAD","OPTIONS"}:
            a,b=request.cookies.get(CSRF,""),request.headers.get("x-csrf-token","")
            if not a or not b or not hmac.compare_digest(a,b) or not hmac.compare_digest(a,user["csrf_token"]):
                return JSONResponse({"detail":"CSRF-Prüfung fehlgeschlagen."},status_code=403)
        roles=set(user["roles"])
        if path.startswith("/api/auth/users") and "admin" not in roles:
            return JSONResponse({"detail":"Unzureichende Berechtigung."},status_code=403)
        if path.startswith("/api/rules/config") and method!="GET" and not roles.intersection({"admin","rule_owner"}):
            return JSONResponse({"detail":"Unzureichende Berechtigung."},status_code=403)
        if path == "/api/rules/preview" and not roles.intersection({"admin","rule_owner"}):
            return JSONResponse({"detail":"Unzureichende Berechtigung."},status_code=403)
        if "/sanitize" in path and not roles.intersection({"admin","operator"}):
            return JSONResponse({"detail":"Unzureichende Berechtigung."},status_code=403)
        if method in {"POST","PUT","PATCH","DELETE"} and path.startswith("/api/projects") and not roles.intersection({"admin","operator"}):
            return JSONResponse({"detail":"Unzureichende Berechtigung."},status_code=403)
        if path.startswith("/api/reviews"):
            review_reader = path == "/api/reviews/runs" and method == "GET"
            if not review_reader and not roles.intersection({"admin","reviewer","approver"}):
                return JSONResponse({"detail":"Unzureichende Berechtigung."},status_code=403)
        return await call_next(request)
