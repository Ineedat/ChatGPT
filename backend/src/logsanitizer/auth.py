"""Local-only account and server-side session support."""
from __future__ import annotations
import hashlib, hmac, os, secrets, sqlite3, time
from contextlib import contextmanager
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

COOKIE = "logsanitizer_session"
CSRF = "logsanitizer_csrf"
TTL = 28800
ROLES = {"admin", "operator", "reviewer", "approver"}
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
        """)
        db.execute("DELETE FROM sessions WHERE expires_at<=?", (int(time.time()),))
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

@router.post("/login")
def login(payload: Login, response: Response):
    initialize_auth_database()
    with _db() as db:
        user=db.execute("SELECT id,password_hash FROM users WHERE username=? COLLATE NOCASE AND enabled=1",(payload.username.strip(),)).fetchone()
    if user is None or not _verify(payload.password,user["password_hash"]): raise HTTPException(401,"Benutzername oder Passwort ungültig.")
    token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
    with _db() as db:
        db.execute("DELETE FROM sessions WHERE user_id=? OR expires_at<=?",(user["id"],int(time.time())))
        db.execute("INSERT INTO sessions VALUES(?,?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),user["id"],csrf,int(time.time())+TTL))
    secure=os.environ.get("LOGSANITIZER_COOKIE_SECURE","").casefold() in {"1","true","yes"}
    response.set_cookie(COOKIE,token,max_age=TTL,httponly=True,secure=secure,samesite="strict",path="/api")
    response.set_cookie(CSRF,csrf,max_age=TTL,httponly=False,secure=secure,samesite="strict",path="/api")
    return {"authenticated":True}

@router.post("/logout")
def logout(request: Request, response: Response):
    token=request.cookies.get(COOKIE)
    if token:
        with _db() as db: db.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(COOKIE,path="/api",samesite="strict")
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
        if path.startswith("/api/auth/users") and "admin" not in roles: return JSONResponse({"detail":"Unzureichende Berechtigung."},status_code=403)
        if path.startswith("/api/rules/config") and method!="GET" and not roles.intersection({"admin","operator"}): return JSONResponse({"detail":"Unzureichende Berechtigung."},status_code=403)
        if "/sanitize" in path and not roles.intersection({"admin","operator"}): return JSONResponse({"detail":"Unzureichende Berechtigung."},status_code=403)
        if method in {"POST","PUT","PATCH","DELETE"} and path.startswith("/api/projects") and not roles.intersection({"admin","operator"}): return JSONResponse({"detail":"Unzureichende Berechtigung."},status_code=403)
        return await call_next(request)
