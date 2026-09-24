from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Query
from fastapi.responses import RedirectResponse
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument, UpdateOne
from pymongo.errors import DuplicateKeyError
import asyncio
import json
from contextlib import suppress
import os
import logging
import random
import re
import secrets
from collections import deque
from decimal import Decimal
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import List, Literal, Optional, Any
from urllib.parse import urlencode
import uuid
import hashlib
import hmac
from functools import wraps
from deposit_settlement import confirm_deposit, plan_deposit, settle_deposit
from roblox_profile import profile_fields, require_roblox_profile
from deposit_rejections import rejection_reason_text
from chat_texts import REJECTION_REASONS_EN, request_lang, tr
import chat_attachments
import donation_payments as dp
from fastapi import File, UploadFile
from bank_accounting import bank_funds, reserve_historical_commissions, spendable_bank_expr
from rain_settlement import close_rain, resume_rain_returns
from shop_purchase import purchase_skins
from withdrawal_cancellation import cancel_withdrawal, finish_cancellation, resolve_history
from notifications import operation_notifications
import promotions as promos
from promotions import ensure_promotions, promo_fields, record_activation, refresh_user_promo
import xrocket_payments as xp
import cryptobot_payments as cb
import live_chat as chat
import admin_commands
import admin_coins
import economy_guard
import economy_reset
import referrals
import staff_core
import staff_evidence
import staff_routes
import staff_shifts
import staff_telegram
import time
import bcrypt
import httpx
import jwt
from datetime import datetime, timedelta, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

APP_URL = os.environ['PUBLIC_APP_URL'].rstrip('/')
DISCORD_CLIENT_ID = os.environ['DISCORD_CLIENT_ID']
DISCORD_CLIENT_SECRET = os.environ['DISCORD_CLIENT_SECRET']
JWT_SECRET = os.environ['JWT_SECRET']
tg_bot = dp.bot_from_env(JWT_SECRET)
staff_bot = staff_telegram.StaffBot()
ADMIN_SEED_HASH = os.environ['ADMIN_SEED_HASH'].encode()
ADMIN_SEED_WORDS = 10
ADMIN_TOKEN_HOURS = 4
# Сколько админов могут сидеть в панели одновременно (4-й вход гасит самую старую сессию).
MAX_ADMIN_SESSIONS = 3
ADMIN_MAX_FAILS_IP = 5
ADMIN_MAX_FAILS_GLOBAL = 20
ADMIN_LOCK_MINUTES = 15
CORS_ORIGINS = [o.strip() for o in os.environ['CORS_ORIGINS'].split(',') if o.strip()]
DISCORD_REDIRECT_URI = f"{APP_URL}/api/auth/discord/callback"
DISCORD_API = "https://discord.com/api/v10"
xrocket = xp.XrocketGateway(
    token=os.environ.get("XROCKET_API_TOKEN", ""),
    webhook_secret=os.environ.get("XROCKET_WEBHOOK_SECRET", ""),
    base_url=os.environ.get("XROCKET_API_BASE_URL", xp.PRODUCTION_API),
)
cryptobot = cb.CryptoBotGateway(
    token=os.environ.get("CRYPTOBOT_API_TOKEN", ""),
    testnet=os.environ.get("CRYPTOBOT_TESTNET", "false").lower() == "true",
)

app = FastAPI()
api_router = APIRouter(prefix="/api")


@app.middleware("http")
async def guard_economy_operations(request: Request, call_next):
    excluded = {"/api/admin/bank/reset", "/api/admin/login", "/api/admin/logout", "/api/admin/session"}
    if (not getattr(app.state, "economy_guard_ready", False)
            or not request.url.path.startswith("/api/") or request.url.path in excluded):
        return await call_next(request)
    try:
        async with economy_guard.operation(db):
            return await call_next(request)
    except HTTPException as error:
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers=error.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not echo raw NaN/Infinity or arbitrary input objects into JSON responses.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]})


@app.exception_handler(httpx.HTTPError)
async def external_service_error(request: Request, exc: httpx.HTTPError):
    logger.warning("External service unavailable: %s", type(exc).__name__)
    if request.url.path == "/api/auth/discord/callback":
        return RedirectResponse(f"{APP_URL}/?auth_error=unavailable")
    return JSONResponse(status_code=503, content={"detail": "Внешний сервис временно недоступен"})

ONLINE_WINDOW_SECONDS = 120
MIN_CHANCE = 0.01
MAX_CHANCE = 0.75
# Кешбэк при проигрыше: 1 RAP с пула, только для ставок от 10 RAP.
# Порог отсекает ферму мелочи (ставка 0.5 + кешбэк 1 = бесконечные деньги),
# списание из пула держит жёсткий потолок: призы + кешбэки <= RTP × ставки.
CASHBACK_AMOUNT = 1.0
CASHBACK_MIN_BET = 10.0

from catalog import RARITIES, SHOP_ITEMS  # noqa: E402  (data moved out of the app module)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


# ---------- Models ----------
class InputModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True)


class PresenceIn(InputModel):
    session_id: str = Field(min_length=1, max_length=64)


class NotificationsReadIn(InputModel):
    read_through: datetime


class StatsOut(BaseModel):
    online: int
    upgrades: int


class UserOut(BaseModel):
    session_id: str
    balance: float
    nickname: str
    skins: List[dict]
    avatar: Optional[str] = None
    discord_id: Optional[str] = None
    promo_code: Optional[str] = None
    promo_bonus: float = 0.0
    roblox_nick: Optional[str] = None
    roblox_display_name: Optional[str] = None
    roblox_link: Optional[str] = None
    gold_nick: bool = False
    # Instant RAP gift result (rap_fixed only; None for ordinary responses).
    # Kept optional for backwards compatibility: old clients ignore these.
    gift_type: Optional[Literal["deposit_percent", "rap_fixed"]] = None
    gift_amount: Optional[float] = None
    gift_already_received: Optional[bool] = None


class RobloxIn(InputModel):
    roblox_display_name: str = Field(min_length=3, max_length=20)
    roblox_nick: str = Field(min_length=3, max_length=21)
    roblox_link: str = Field(min_length=10, max_length=400)


class PromoIn(InputModel):
    code: str = Field(min_length=1, max_length=32)


class AdminPromoIn(InputModel):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    # Backwards compatible: requests without `type` are deposit_percent.
    type: Literal["deposit_percent", "rap_fixed"] = "deposit_percent"
    percent: Optional[Decimal] = Field(default=None, gt=0, le=50, decimal_places=2)
    amount_rap: Optional[Decimal] = None
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def check_promo_consistency(self):
        kind = self.type or "deposit_percent"
        if kind == "deposit_percent":
            if self.percent is None:
                raise ValueError("Для процентного промокода нужен percent")
            if self.amount_rap is not None:
                raise ValueError("amount_rap допустим только для rap_fixed")
            if self.max_uses is not None:
                raise ValueError("max_uses допустим только для rap_fixed")
            if self.expires_at is not None:
                raise ValueError("expires_at допустим только для rap_fixed")
        else:  # rap_fixed
            if self.percent is not None:
                raise ValueError("percent допустим только для deposit_percent")
            if self.amount_rap is None:
                raise ValueError("Для RAP-промокода нужна сумма amount_rap")
            if self.max_uses is None:
                raise ValueError("Для RAP-промокода нужен конечный лимит max_uses")
            # Decimal-strict validation (positivity, upper bound, max 2 decimals).
            try:
                promos.validate_rap_amount(self.amount_rap)
            except ValueError as e:
                raise ValueError(str(e))
            try:
                promos.validate_max_uses(self.max_uses)
            except ValueError as e:
                raise ValueError(str(e))
        return self


class XrocketInvoiceIn(InputModel):
    request_id: uuid.UUID
    amount_rub: Decimal = Field(ge=35, le=1_000_000, decimal_places=2)
    currency: Literal["GRAM", "USDT", "USDC", "BTC", "ETH", "TRX", "SOL", "BNB"]


class DepositIn(InputModel):
    description: str = Field(min_length=3, max_length=300)
    expected_rap: float = Field(ge=200, le=1_000_000)
    receiver_id: str = Field(min_length=1, max_length=32)


class CryptobotInvoiceIn(InputModel):
    request_id: uuid.UUID
    amount_rub: Decimal = Field(ge=35, le=1_000_000, decimal_places=2)
    currency: Literal["USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC"] = "USDT"


class ChatCreateIn(InputModel):
    kind: Literal["support", "deposit", "withdrawal"] = "support"
    for_topup: bool = False
    text: Optional[str] = Field(default=None, max_length=2000)
    expected_rap: Optional[float] = Field(default=None, ge=200, le=1_000_000)


class ChatMessageIn(InputModel):
    text: str = Field(min_length=1, max_length=2000)


class AdminCommandIn(InputModel):
    command: str = Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_-]*$")
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("command", mode="before")
    @classmethod
    def normalize_command(cls, value):
        return value.strip().lstrip("/").lower() if isinstance(value, str) else value

    @field_validator("text", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class AdminCoinsIn(InputModel):
    request_id: uuid.UUID
    # Retain the old coin field for clients with an in-flight grant saved before
    # the ruble form was deployed. Never reinterpret that amount as rubles.
    amount: Optional[Decimal] = Field(default=None, gt=0, le=admin_coins.MAX_BALANCE, decimal_places=2)
    amount_rub: Optional[Decimal] = Field(default=None, gt=0, le=admin_coins.MAX_BALANCE // admin_coins.COINS_PER_RUB, decimal_places=2)
    note: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def exactly_one_amount(self):
        if (self.amount is None) == (self.amount_rub is None):
            raise ValueError("Укажите одну сумму пополнения")
        return self


class AdminLoginIn(BaseModel):
    phrases: List[str] = Field(min_length=ADMIN_SEED_WORDS, max_length=ADMIN_SEED_WORDS)


class AdminConfirmIn(InputModel):
    rap: float = Field(gt=0, le=1_000_000)
    note: Optional[str] = Field(default=None, max_length=200)
    request_id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9-]{8,64}$")


class AdminRejectIn(InputModel):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class BankSettingsIn(InputModel):
    rtp_target: Optional[float] = Field(default=None, ge=0.75, le=1.0)
    pin: str = Field(min_length=1, max_length=32)


class BankResetIn(InputModel):
    pin: str = Field(min_length=1, max_length=32)
    scope: Literal["full_economy"]
    request_id: uuid.UUID


class RainSettingsIn(InputModel):
    enabled: Optional[bool] = None
    pool_threshold: Optional[float] = Field(default=None, ge=100, le=100000)
    budget_min_pct: Optional[float] = Field(default=None, ge=0.05, le=0.5)
    budget_max_pct: Optional[float] = Field(default=None, ge=0.05, le=0.5)
    max_single_pct: Optional[float] = Field(default=None, ge=0.1, le=0.9)
    timeout_min: Optional[int] = Field(default=None, ge=10, le=360)


class BankAdjustIn(InputModel):
    amount: float = Field(ge=-1_000_000, le=1_000_000)
    note: str = Field(min_length=2, max_length=200)
    pin: str = Field(min_length=1, max_length=32)


class PoolTopUpIn(InputModel):
    amount: float = Field(ge=-1_000_000, le=1_000_000)
    note: str = Field(min_length=2, max_length=200)
    pin: str = Field(min_length=1, max_length=32)


class UidsIn(InputModel):
    uids: List[str] = Field(min_length=1, max_length=200)


class PurchaseLineIn(InputModel):
    id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=100, strict=True)


class PurchaseIn(InputModel):
    request_id: uuid.UUID
    items: List[PurchaseLineIn] = Field(min_length=1, max_length=100)
    expected_total: float = Field(gt=0, le=100_000_000)


class Drop(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    nickname: str
    item_name: str
    item_type: str
    item_price: float
    item_image: Optional[str] = None
    item_rarity: Optional[str] = None
    chance: float
    # Показываемый % (без house edge): bet/price. Реальный шанс победы — `chance`.
    display_chance: Optional[float] = None
    avatar: Optional[str] = None
    discord_id: Optional[str] = None
    gold_nick: bool = False
    created_at: datetime = Field(default_factory=now_utc)


class UpgradeIn(InputModel):
    session_id: str = Field(min_length=1, max_length=64)
    bet_amount: float = Field(ge=0, le=1_000_000)
    bet_items: List[dict] = Field(default_factory=list, max_length=200)
    target_item: Optional[dict] = None
    chance: Optional[float] = None


class UpgradeOut(BaseModel):
    id: str
    win: bool
    roll: float
    chance: float
    # Показываемый % (bet/price без RTP). Дроп/логика победы используют `chance`.
    display_chance: Optional[float] = None
    angle: float
    balance: float
    upgrades_total: int
    # Кешбэк, упавший этим проигрышным спином (0 если не было).
    cashback: float = 0.0


# ---------- Helpers ----------
def to_user_out(user: dict) -> UserOut:
    return UserOut(
        session_id=user["session_id"],
        balance=float(user.get("balance", 0)),
        nickname=user.get("nickname", "Player"),
        skins=user.get("skins", []),
        avatar=user.get("avatar"),
        discord_id=user.get("discord_id"),
        promo_code=user.get("promo_code"),
        promo_bonus=float(user.get("promo_bonus") or 0),
        roblox_nick=user.get("roblox_nick"),
        roblox_display_name=user.get("roblox_display_name"),
        roblox_link=user.get("roblox_link"),
        gold_nick=bool(user.get("gold_nick")),
    )


async def get_or_create_user(session_id: str) -> dict:
    user = await db.users.find_one({"session_id": session_id}, {"_id": 0})
    if not user:
        user = {
            "session_id": session_id,
            "balance": 0.0,
            "nickname": f"Player_{session_id[:4]}",
            "skins": [],
            "created_at": now_utc(),
        }
        await db.users.update_one({"session_id": session_id}, {"$setOnInsert": dict(user)}, upsert=True)
        user = await db.users.find_one({"session_id": session_id}, {"_id": 0})
        user.pop("_id", None)
    skins = user.get("skins", [])
    if any("uid" not in sk for sk in skins):
        for sk in skins:
            sk.setdefault("uid", str(uuid.uuid4()))
        await db.users.update_one({"session_id": session_id}, {"$set": {"skins": skins}})
    return await refresh_user_promo(db, user)


async def count_online() -> int:
    threshold = now_utc() - timedelta(seconds=ONLINE_WINDOW_SECONDS)
    return await db.presence.count_documents({"last_seen": {"$gte": threshold}})


async def count_upgrades() -> int:
    return await economy_reset.upgrade_count(db)


def make_token(session_id: str, role: str = "user", hours: int = 24 * 30, extra: Optional[dict] = None) -> str:
    payload = {"sub": session_id, "role": role, "exp": now_utc() + timedelta(hours=hours), "iat": now_utc(), **(extra or {})}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(request: Request) -> Optional[dict]:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get("bg_token")
    if not token:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def read_token(request: Request) -> Optional[str]:
    data = decode_token(request)
    return data.get("sub") if data and data.get("role") == "user" else None


def session_version_query(sv: int) -> dict:
    return {"$or": [{"session_version": sv}, {"session_version": {"$exists": False}}]} if sv == 0 else {"session_version": sv}


async def token_user(request: Request, projection: Optional[dict] = None) -> Optional[dict]:
    """User of a valid, non-revoked user token (logout bumps session_version)."""
    session_id = read_token(request)
    if not session_id:
        return None
    try:
        sv = int((decode_token(request) or {}).get("sv", 0))
    except (TypeError, ValueError):
        return None
    return await db.users.find_one({"session_id": session_id, **session_version_query(sv)}, projection or {"_id": 0})


def client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()


def ua_hash(request: Request) -> str:
    return hashlib.sha256(request.headers.get("user-agent", "").encode()).hexdigest()[:32]


async def require_admin(request: Request) -> dict:
    data = decode_token(request)
    if not data or data.get("role") != "admin" or data.get("type") != "admin" or not data.get("jti"):
        raise HTTPException(status_code=403, detail="Нет доступа")
    if data.get("seed_version") != hashlib.sha256(ADMIN_SEED_HASH).hexdigest():
        raise HTTPException(status_code=403, detail="Сид-фраза изменена. Войдите заново")
    sess = await db.admin_sessions.find_one({"jti": data["jti"], "revoked": False, "expires_at": {"$gt": now_utc()}}, {"_id": 0})
    if not sess or not hmac.compare_digest(sess.get("ua_hash", ""), ua_hash(request)):
        raise HTTPException(status_code=403, detail="Нет доступа")
    if not sess.get("last_seen") or now_utc() - as_utc(sess["last_seen"]) > timedelta(seconds=60):
        await db.admin_sessions.update_one({"jti": data["jti"]}, {"$set": {"last_seen": now_utc()}})
    return sess


async def check_admin_lock(ip: str) -> None:
    now = now_utc()
    for key, limit in ((f"ip:{ip}", ADMIN_MAX_FAILS_IP), ("global", ADMIN_MAX_FAILS_GLOBAL)):
        doc = await db.login_attempts.find_one({"identifier": key})
        if not doc:
            continue
        locked_until, window_start = as_utc(doc.get("locked_until")), as_utc(doc.get("window_start"))
        if locked_until and locked_until > now:
            raise HTTPException(status_code=429, detail="Доступ временно заблокирован. Попробуйте позже")
        if doc.get("fails", 0) >= limit and window_start and now - window_start < timedelta(minutes=ADMIN_LOCK_MINUTES):
            await db.login_attempts.update_one({"identifier": key}, {"$set": {"locked_until": now + timedelta(minutes=ADMIN_LOCK_MINUTES)}})
            raise HTTPException(status_code=429, detail="Доступ временно заблокирован. Попробуйте позже")


async def record_admin_fail(ip: str) -> None:
    now = now_utc()
    for key in (f"ip:{ip}", "global"):
        doc = await db.login_attempts.find_one({"identifier": key})
        window_start = as_utc(doc.get("window_start")) if doc else None
        if not window_start or now - window_start > timedelta(minutes=ADMIN_LOCK_MINUTES):
            await db.login_attempts.update_one({"identifier": key}, {"$set": {"fails": 1, "window_start": now, "locked_until": None}}, upsert=True)
        else:
            await db.login_attempts.update_one({"identifier": key}, {"$inc": {"fails": 1}})


DEPOSIT_FEE = 0.20
MIN_DEPOSIT_RAP = 200
DEPOSIT_COOLDOWN_SECONDS = 60
ROBLOX_FRIEND_URL = "https://www.roblox.com/share?code=114adf7ac7b01243b752faf7c6c71b28&type=Profile&source=ProfileShare&stamp=1788366461111"
RECEIVERS = [
    {"id": "support", "nickname": "Поддержка", "handle": "", "avatar": None, "friend_url": ROBLOX_FRIEND_URL},
]


async def require_user(request: Request) -> dict:
    user = await token_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return await refresh_user_promo(db, user)


def serialized_user_action(fn):
    """Prevent parallel sale/withdraw/deposit requests bypassing account limits."""
    @wraps(fn)
    async def wrapped(payload, request):
        user = await require_user(request)
        sid, owner = user["session_id"], str(uuid.uuid4())
        try:
            lock = await db.user_locks.find_one_and_update(
                {"session_id": sid, "expires_at": {"$lt": now_utc()}},
                {"$set": {"owner": owner, "expires_at": now_utc() + timedelta(seconds=60)}},
                upsert=True, return_document=ReturnDocument.AFTER, projection={"_id": 0},
            )
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Предыдущая операция ещё выполняется. Подождите")
        try:
            return await fn(payload, request)
        finally:
            await db.user_locks.delete_one({"session_id": sid, "owner": owner})
    return wrapped


async def take_skins(user: dict, uids: List[str], credit: bool = False, op_id: Optional[str] = None) -> List[dict]:
    owned = {sk.get("uid"): sk for sk in user.get("skins", []) if sk.get("uid")}
    if not uids or len(uids) > 200 or len(set(uids)) != len(uids) or any(u not in owned for u in uids):
        raise HTTPException(status_code=400, detail="Выбранных скинов нет в вашем инвентаре")
    taken = [owned[u] for u in uids]
    update: dict = {"$pull": {"skins": {"uid": {"$in": uids}}}}
    if credit:
        update["$inc"] = {"balance": round(sum(float(sk.get("price") or 0) for sk in taken), 2)}
    if op_id:
        # Marker written in the same update as the removal: proves the skins left the inventory.
        update["$addToSet"] = {"withdrawal_ops": op_id}
    res = await db.users.update_one(
        {"session_id": user["session_id"], "skins": {"$all": [{"$elemMatch": {"uid": u}} for u in uids]}}, update
    )
    if not res.matched_count:
        raise HTTPException(status_code=400, detail="Скины уже использованы")
    return taken


# ---------- Casino bank ----------
# Payout model: shown chance = bet/price * RTP (default edge 15%). The roll is honest; the payout is gated by
# the payout pool: every accepted bet refills pool += bet * rtp, a win spends pool -= prize. Hence total paid
# never exceeds rtp * total wagered (hard RTP ceiling) plus explicit admin top-ups. Second guard is solvency:
# a prize the bank cannot cover becomes a silent forced loss (player sees a normal loss, no message).
BANK_DEFAULTS = {"rtp_target": 0.85}
ADMIN_BANK_PIN = os.environ.get("ADMIN_BANK_PIN") or "1001"


def require_pin(pin: str) -> None:
    if not hmac.compare_digest((pin or "").strip(), ADMIN_BANK_PIN):
        raise HTTPException(status_code=403, detail="Неверный PIN-код")


_rng = secrets.SystemRandom()
MAX_PROMO_BONUS = 0.5
_upgrade_lock = asyncio.Lock()
_upgrade_seen: dict = {}


def upgrade_rate_ok(session_id: str) -> bool:
    """One allowed spin per 2s per session. Check+register without await; rejected spins do not extend the window."""
    now = time.monotonic()
    q = _upgrade_seen.get(session_id)
    if q is None:
        q = deque(maxlen=1)
        _upgrade_seen[session_id] = q
    if q and now - q[0] < 2.0:
        return False
    q.append(now)
    if len(_upgrade_seen) > 10000:
        stale = [k for k, v in _upgrade_seen.items() if not v or now - v[0] > 3600]
        for k in stale:
            _upgrade_seen.pop(k, None)
    return True


# Promo apply rate limit: 30 requests per 60s per Discord-account (or session).
# Burst-friendly (12 parallel percent activations in tests must pass), but stops
# brute-force code enumeration. In-memory per worker + account-keyed; concurrent
# correctness itself relies on atomic DB updates, not on this limiter.
_promo_seen: dict = {}
PROMO_RATE_LIMIT = 30
PROMO_RATE_WINDOW = 60.0


def promo_rate_ok(key: str) -> bool:
    now = time.monotonic()
    q = _promo_seen.get(key)
    if q is None:
        q = deque(maxlen=PROMO_RATE_LIMIT)
        _promo_seen[key] = q
    while q and now - q[0] > PROMO_RATE_WINDOW:
        q.popleft()
    if len(q) >= PROMO_RATE_LIMIT:
        return False
    q.append(now)
    if len(_promo_seen) > 10000:
        stale = [k for k, v in _promo_seen.items() if not v or now - v[-1] > 3600]
        for k in stale:
            _promo_seen.pop(k, None)
    return True


def win_chance(total_bet: float, target_price: float, rtp: float) -> float:
    return min(MAX_CHANCE, total_bet / target_price * rtp)


def shown_chance(total_bet: float, target_price: float) -> float:
    """Только для показа: bet/price без house edge (20 на кейс 40 = 50%).
    На победу/дроп не влияет — победа считается по win_chance()."""
    if target_price <= 0:
        return 0.0
    return min(MAX_CHANCE, total_bet / target_price)


def max_bet_ratio(rtp: float) -> float:
    """Stop adding stake when the displayed (pre-RTP) chance reaches its cap."""
    return MAX_CHANCE


# ---------- Luck (секретная полоса удачи по заполнению пула) ----------
# СЕКРЕТНО: игрокам ничего не показывается — ни баннеров, ни бонусов, ни истории.
# Триггер — свободный pool >= threshold. Резервируется случайные 20-30% pool.
# Пока резерв не кончился: прокруты судятся по ПОКАЗЫВАЕМОМУ шансу (bet/price
# без RTP — ровно та цифра, что видит игрок), а призы списываются из резерва,
# а не из общего пула. Один приз — не больше 60% ОСТАТКА резерва (иначе один
# жирный приз съест всю полосу; такой спин идёт по обычным правилам).
# Обычные проверки банка остаются: чем платить нет — победа не выдаётся.
# Непотраченный остаток по таймауту возвращается в pool.
RAIN_DEFAULTS = {
    "enabled": True,
    "pool_threshold": 4000.0,
    "budget_min_pct": 0.20,
    "budget_max_pct": 0.30,
    "max_single_pct": 0.60,
    "timeout_min": 60,
}


async def rain_settings() -> dict:
    doc = await db.rain_settings.find_one({"id": "main"}, {"_id": 0, "id": 0}) or {}
    return {**RAIN_DEFAULTS, **doc}


async def rain_active() -> Optional[dict]:
    return await db.rains.find_one({"status": "active"}, {"_id": 0})


async def rain_maybe_start() -> Optional[dict]:
    """Пытается открыть полосу удачи, если pool полон. Возвращает активную или None.

    Бронь бюджета атомарна (pool -= budget только если pool >= budget),
    поэтому одновременные спины не могут зарезервировать одно и то же дважды.
    """
    cfg = await rain_settings()
    if not cfg.get("enabled"):
        return await rain_active()
    existing = await rain_active()
    if existing:
        return existing
    pool = await payout_pool()
    threshold = float(cfg["pool_threshold"])
    if pool < threshold:
        return None
    pct = _rng.uniform(float(cfg["budget_min_pct"]), float(cfg["budget_max_pct"]))
    budget = round(pool * pct, 2)
    if budget < 1.0:
        return None
    reserved = await db.bank_state.find_one_and_update(
        {"id": "main", "pool": {"$gte": budget}},
        {"$inc": {"pool": -budget}},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    if not reserved:
        return await rain_active()  # гонку выиграл чужой спин/победа — пул уже меньше
    now = now_utc()
    rain = {
        "id": str(uuid.uuid4()),
        "v": 2,
        "status": "active",
        "budget": budget,
        "left": budget,
        "spent": 0.0,
        "wins": [],
        "created_at": now,
        "closes_at": now + timedelta(minutes=int(cfg["timeout_min"])),
        "closed_at": None,
        "returned_amount": 0.0,
    }
    try:
        await db.rains.insert_one(rain)
    except DuplicateKeyError:
        # Крайне редкая гонка: два спина одновременно прошли бронь и создали полосы.
        # Откатываем свою бронь обратно в pool — прибыль не теряем.
        await db.bank_state.update_one({"id": "main"}, {"$inc": {"pool": budget}})
        return await rain_active()
    out = dict(rain)
    out.pop("_id", None)
    return out


async def rain_maybe_close() -> Optional[dict]:
    """Ленивое закрытие: просрочка — возврат остатка в pool; legacy-документы
    старого формата (куски) мигрируются сразу. Только один воркер."""
    await resume_rain_returns(db)
    now = now_utc()
    # Сначала legacy-формат (v1 с кусками): закрываем вне зависимости от таймаута.
    legacy = await close_rain(db, {"slices": {"$exists": True}})
    if legacy is not None:
        return legacy
    return await close_rain(db, {"closes_at": {"$lte": now}})


async def luck_boosted(rain: Optional[dict], target_price: float) -> bool:
    """Можно ли этот спин судить по показываемому шансу (без RTP).

    Да, если полоса активна и приз влезет в 60% остатка резерва.
    Жирный приз сверх лимита идёт по обычным правилам — полосу не жрёт один.
    """
    if not rain or rain.get("status") != "active":
        return False
    if "slices" in rain:  # legacy-документ — не используем
        return False
    try:
        cfg = await rain_settings()
    except Exception:
        return False
    if not cfg.get("enabled"):
        return False
    left = float(rain.get("left") or 0)
    if left <= 0 or target_price <= 0:
        return False
    return target_price <= left * float(cfg.get("max_single_pct", 0.6)) + 1e-9


async def luck_spend(rain_id: str, prize: float, session_id: str, upgrade_id: str) -> bool:
    """Атомарно списывает приз из резерва полосы. True — оплачено из резерва."""
    if prize <= 0:
        return False
    updated = await db.rains.find_one_and_update(
        {"id": rain_id, "status": "active", "left": {"$gte": prize}},
        {"$inc": {"left": -prize, "spent": prize},
         "$push": {"wins": {"session_id": session_id, "upgrade_id": upgrade_id,
                             "prize": prize, "at": now_utc()}}},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "left": 1},
    )
    if not updated:
        return False
    if float(updated.get("left") or 0) <= 0:
        await db.rains.update_one(
            {"id": rain_id, "status": "active"},
            {"$set": {"status": "closed", "closed_at": now_utc()}},
        )
    return True


async def bank_settings() -> dict:
    doc = await db.bank_settings.find_one({"id": "main"}, {"_id": 0, "id": 0}) or {}
    return {**BANK_DEFAULTS, **doc}


async def payout_pool() -> float:
    """Accumulated refill budget: how much prize value is currently allowed to be paid out."""
    doc = await db.bank_state.find_one({"id": "main"}, {"pool": 1, "_id": 0})
    return float((doc or {}).get("pool") or 0)


async def ensure_pool() -> float:
    """Backfill the pool on first use: it equals rtp * wagered - paid (never negative), so historical
    play keeps its allowance and the ceiling applies going forward."""
    doc = await db.bank_state.find_one({"id": "main"}, {"pool": 1, "_id": 0})
    if doc is not None and doc.get("pool") is not None:
        return float(doc["pool"])
    st = await rtp_stats()
    rtp = float((await bank_settings())["rtp_target"])
    start = max(0.0, st["wagered"] * rtp - st["paid"])
    await db.bank_state.update_one(
        {"id": "main", "pool": {"$exists": False}},
        {"$set": {"pool": start}, "$setOnInsert": {"id": "main", "bank": 0.0}},
        upsert=True,
    )
    if st["wagered"] > 0:
        await db.bank_ledger.insert_one({
            "id": str(uuid.uuid4()), "kind": "settings", "amount": 0.0, "bank_after": await bank_balance(),
            "note": f"Инициализация пула выдачи: {start:.2f} RAP (RTP {round(rtp*100)}% × ставки − выдано)",
            "created_at": now_utc(),
        })
    return start


async def bank_balance() -> float:
    doc = await db.bank_state.find_one({"id": "main"}, {"_id": 0})
    return float((doc or {}).get("bank") or 0)


async def bank_add(kind: str, amount: float, note: Optional[str] = None, ref_id: Optional[str] = None, session_id: Optional[str] = None) -> float:
    if kind == "withdrawal":
        receipt_id = f"withdrawal:{ref_id}"
        state = await db.bank_state.find_one_and_update(
            {"id": "main", "withdrawal_receipts.id": {"$ne": receipt_id},
             "$expr": {"$gte": [spendable_bank_expr(), -amount]}},
            [{"$set": {"bank": {"$add": ["$bank", float(amount)]}}},
             {"$set": {"withdrawal_receipts": {"$concatArrays": [
                 {"$ifNull": ["$withdrawal_receipts", []]},
                 {"$map": {"input": {"$literal": [receipt_id]}, "in": {"id": "$$this", "bank_after": "$bank"}}},
             ]}}}],
            return_document=ReturnDocument.AFTER,
        )
        if state is None:
            state = await db.bank_state.find_one({"id": "main", "withdrawal_receipts.id": receipt_id}, {"_id": 0})
        if state is None:
            raise HTTPException(409, "Недостаточно средств для выдачи без использования комиссии 20%")
        receipt = next(r for r in state["withdrawal_receipts"] if r["id"] == receipt_id)
        await db.bank_ledger.update_one({"id": receipt_id}, {"$setOnInsert": {
            "kind": kind, "amount": float(amount), "bank_after": receipt["bank_after"],
            "note": note, "ref_id": ref_id, "session_id": session_id, "created_at": now_utc(),
        }}, upsert=True)
        return float(receipt["bank_after"])
    state = await db.bank_state.find_one_and_update(
        {"id": "main"}, {"$inc": {"bank": float(amount)}}, upsert=True, return_document=ReturnDocument.AFTER, projection={"_id": 0}
    )
    await db.bank_ledger.insert_one({
        "id": str(uuid.uuid4()), "kind": kind, "amount": float(amount), "bank_after": float(state["bank"]),
        "note": note, "ref_id": ref_id, "session_id": session_id, "created_at": now_utc(),
    })
    return float(state["bank"])


async def _sum(collection, match: dict, expr) -> float:
    docs = await collection.aggregate([{"$match": match}, {"$group": {"_id": None, "s": {"$sum": expr}}}]).to_list(1)
    return float(docs[0]["s"]) if docs else 0.0


async def liabilities() -> dict:
    # single pass over users: balances + inventory value
    agg, pending = await asyncio.gather(
        db.users.aggregate([
            {"$project": {"balance": {"$ifNull": ["$balance", 0]}, "inv": {"$sum": {"$ifNull": ["$skins.price", []]}}}},
            {"$group": {"_id": None, "balances": {"$sum": "$balance"}, "inventory": {"$sum": "$inv"}}},
        ]).to_list(1),
        _sum(db.withdrawals, {"status": {"$in": ["pending", "cancelling", "paying"]}}, "$item.price"),
    )
    balances = float(agg[0]["balances"]) if agg else 0.0
    inventory = float(agg[0]["inventory"]) if agg else 0.0
    return {"balances": balances, "inventory": inventory, "pending_withdrawals": pending, "total": balances + inventory + pending}


async def rtp_stats() -> dict:
    wagered = await _sum(db.upgrades, {}, {"$add": [{"$ifNull": ["$bet_amount", 0]}, {"$ifNull": ["$items_total", 0]}]})
    paid = await _sum(db.upgrades, {"win": True}, "$target_item.price")
    return {"wagered": wagered, "paid": paid, "rtp": (paid / wagered) if wagered > 0 else 0.0}


async def solvency_headroom() -> tuple:
    """How much prize value the bank can still cover on top of all player liabilities."""
    funds, li = await asyncio.gather(bank_funds(db), liabilities())
    return funds["available_bank"] - li["total"], {**funds, "liabilities": li["total"]}


def losing_roll(chance: float) -> float:
    if _rng.random() < 0.3:
        angle = chance * 180 + _rng.uniform(2, 10)
        if _rng.random() < 0.5:
            angle = -angle
        return ((angle + 180) / 360) % 1.0

    r = _rng.random() * (1 - chance)
    half = 0.5 - chance / 2
    return r + chance if r >= half else r


POINTER_CLEARANCE_DEG = 1.5


def landing_angle(roll: float, chance: float, win: bool) -> float:
    """Pointer angle in [-180, 180] (zone is centered at 0). Keeps a small visual gap from the zone edge so the result is never ambiguous."""
    angle = roll * 360 - 180
    half = chance * 180
    sign = 1 if angle >= 0 else -1
    if win:
        limit = max(0.0, half - POINTER_CLEARANCE_DEG)
        if abs(angle) > limit:
            angle = sign * limit
    else:
        limit = min(180.0, half + POINTER_CLEARANCE_DEG)
        if abs(angle) < limit:
            angle = sign * limit
    return round(angle, 4)


class bank_lock:
    """Serializes payout decisions: in-process lock + Mongo lease (safe across workers/replicas)."""

    leased = False

    async def __aenter__(self):
        await _upgrade_lock.acquire()
        deadline = time.time() + 8
        try:
            while time.time() < deadline:
                now = now_utc()
                doc = await db.bank_lock.find_one_and_update(
                    {"id": "main", "locked_until": {"$lt": now}},
                    {"$set": {"locked_until": now + timedelta(seconds=5)}},
                )
                if doc:
                    self.leased = True
                    return self
                await asyncio.sleep(0.02)
        except Exception:
            logger.exception("bank lock error")
        logger.error("bank lock not acquired — payout will be denied")
        return self

    async def __aexit__(self, *exc):
        try:
            if self.leased:
                await db.bank_lock.update_one({"id": "main"}, {"$set": {"locked_until": now_utc() - timedelta(seconds=1)}})
        finally:
            _upgrade_lock.release()


# ---------- Routes ----------
@api_router.get("/")
async def root():
    return {"message": "BLOXGRADE API"}


@api_router.get("/rarities")
async def rarities():
    return RARITIES


@api_router.get("/game-config")
async def game_config():
    rtp = float((await bank_settings())["rtp_target"])
    return {"rtp": rtp, "min_chance": MIN_CHANCE, "max_chance": MAX_CHANCE, "max_bet_ratio": max_bet_ratio(rtp)}


@api_router.post("/presence", response_model=StatsOut)
async def presence(payload: PresenceIn):
    await db.presence.update_one(
        {"session_id": payload.session_id},
        {"$set": {"last_seen": now_utc()}},
        upsert=True,
    )
    return StatsOut(online=await count_online(), upgrades=await count_upgrades())


@api_router.get("/stats", response_model=StatsOut)
async def stats():
    return StatsOut(online=await count_online(), upgrades=await count_upgrades())


@api_router.get("/user/{session_id}", response_model=UserOut)
async def get_user(session_id: str, request: Request):
    if session_id.startswith("discord_") and (await token_user(request, {"_id": 0, "session_id": 1}) or {}).get("session_id") != session_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
        raise HTTPException(status_code=400, detail="Некорректная сессия")
    return to_user_out(await get_or_create_user(session_id))


# ---------- Discord auth ----------
@api_router.get("/auth/discord/login")
async def discord_login(ref: Optional[str] = None):
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        return RedirectResponse(f"{APP_URL}/?auth_error=unavailable")
    state = secrets.token_urlsafe(16)
    inviter = await referrals.inviter_for_code(db, ref)
    await db.oauth_states.insert_one({"state": state, "created_at": now_utc(), "referrer_id": inviter})
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }
    resp = RedirectResponse(f"https://discord.com/oauth2/authorize?{urlencode(params)}")
    resp.set_cookie("bg_oauth_state", state, httponly=True, secure=True, samesite="lax", max_age=600, path="/api/auth/discord")
    return resp


@api_router.get("/auth/discord/callback")
async def discord_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error or not code:
        return RedirectResponse(f"{APP_URL}/?auth_error=denied")
    browser_state = request.cookies.get("bg_oauth_state", "")
    if not state or not browser_state or not hmac.compare_digest(state, browser_state):
        return RedirectResponse(f"{APP_URL}/?auth_error=state")
    oauth_state = await db.oauth_states.find_one_and_delete({"state": state, "created_at": {"$gt": now_utc() - timedelta(minutes=10)}})
    if not oauth_state:
        return RedirectResponse(f"{APP_URL}/?auth_error=state")

    async with httpx.AsyncClient(timeout=15) as http:
        token_res = await http.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_res.status_code != 200:
            logger.error("Discord token exchange failed: HTTP %s", token_res.status_code)
            return RedirectResponse(f"{APP_URL}/?auth_error=token")
        access_token = token_res.json().get("access_token")
        if not access_token:
            return RedirectResponse(f"{APP_URL}/?auth_error=token")
        me_res = await http.get(f"{DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {access_token}"})
        if me_res.status_code != 200:
            return RedirectResponse(f"{APP_URL}/?auth_error=profile")
        me = me_res.json()

    discord_id = str(me.get("id", ""))
    if not discord_id.isdigit():
        return RedirectResponse(f"{APP_URL}/?auth_error=profile")
    nickname = me.get("global_name") or me.get("username") or f"User_{discord_id[-4:]}"
    avatar = (
        f"https://cdn.discordapp.com/avatars/{discord_id}/{me['avatar']}.png?size=128"
        if me.get("avatar")
        else f"https://cdn.discordapp.com/embed/avatars/{int(discord_id) % 6}.png"
    )
    session_id = f"discord_{discord_id}"
    referral_fields = await referrals.signup_fields(db, oauth_state.get("referrer_id"), session_id)
    await db.users.update_one(
        {"session_id": session_id},
        {
            "$set": {"nickname": nickname, "avatar": avatar, "discord_id": discord_id, "last_login": now_utc()},
            "$setOnInsert": {"balance": 0.0, "skins": [], "created_at": now_utc(), **referral_fields},
        },
        upsert=True,
    )
    account = await db.users.find_one({"session_id": session_id}, {"_id": 0, "session_version": 1})
    token = make_token(session_id, extra={"sv": int((account or {}).get("session_version") or 0)})
    resp = RedirectResponse(f"{APP_URL}/auth/callback#token={token}")
    resp.set_cookie("bg_token", token, httponly=True, secure=True, samesite="lax", max_age=30 * 24 * 3600, path="/")
    resp.delete_cookie("bg_oauth_state", path="/api/auth/discord", secure=True, httponly=True, samesite="lax")
    return resp


@api_router.get("/auth/me", response_model=UserOut)
async def auth_me(request: Request):
    return to_user_out(await require_user(request))


@api_router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    # Revoke every token of this account, including copies made before logout.
    user = await token_user(request, {"_id": 0, "session_id": 1, "session_version": 1})
    if user:
        sv = int(user.get("session_version") or 0)
        await db.users.update_one({"session_id": user["session_id"], **session_version_query(sv)}, {"$set": {"session_version": sv + 1}})
    response.delete_cookie("bg_token", path="/", secure=True, httponly=True, samesite="lax")
    return {"ok": True}


@api_router.get("/deposit/info")
async def deposit_info():
    return {"friend_url": ROBLOX_FRIEND_URL, "min_rap": MIN_DEPOSIT_RAP, "fee": DEPOSIT_FEE, "receivers": RECEIVERS, "cooldown": DEPOSIT_COOLDOWN_SECONDS}


@api_router.post("/promo/apply", response_model=UserOut)
async def promo_apply(payload: PromoIn, request: Request):
    user = await require_user(request)
    rate_key = promos.account_key(user) or user.get("session_id") or client_ip(request)
    if not promo_rate_ok(rate_key):
        raise HTTPException(status_code=429, detail="Слишком много попыток. Подождите минуту")
    code = payload.code.strip().upper()
    promo = await db.promo_codes.find_one({"code": code, "deleted": False}, {"_id": 0})
    if promo is None:
        raise HTTPException(status_code=400, detail="Промокод не найден")
    if promos.promo_type(promo) == promos.PROMO_TYPE_RAP:
        # Instant RAP gift: recipient ONLY from server auth, one issuance per
        # (promo_id, Discord-account) regardless of session. Amount from DB.
        # Active percent bonus is left untouched. No deposit/bank/referral writes.
        try:
            gift = await promos.apply_rap_gift(db, promo, user)
        except promos.GiftLimitExhausted as e:
            raise HTTPException(status_code=409, detail=str(e) or "Лимит использований исчерпан")
        except promos.GiftNotAvailable as e:
            msg = str(e) or "Промокод недоступен"
            # Disabled/expired/deleted/gone -> 400 except exhausted (409 above).
            # Missing recipient is also a client error, not auth (user IS authed).
            raise HTTPException(status_code=400, detail=msg)
        fresh = await db.users.find_one({"session_id": user["session_id"]}, {"_id": 0})
        if not fresh:
            raise HTTPException(status_code=409, detail="Аккаунт получателя не найден")
        fresh = await refresh_user_promo(db, fresh)
        out = to_user_out(fresh)
        out.gift_type = "rap_fixed"
        out.gift_amount = gift["amount"]
        out.gift_already_received = bool(gift["already"])
        return out
    # Legacy percent path — unchanged semantics (gold nick sticky, frozen deposit terms).
    already = await db.promo_activations.find_one(
        {"promo_id": promo["id"], "account_key": promos.account_key(user)}, {"_id": 1}
    )
    changes = promo_fields(promo)
    if promo.get("gold_nick"):
        changes["gold_nick"] = True
    await db.users.update_one({"session_id": user["session_id"]}, {"$set": changes})
    await record_activation(db, promo["id"], user)
    user.update(changes)
    out = to_user_out(user)
    out.gift_type = "deposit_percent"
    out.gift_amount = None
    out.gift_already_received = bool(already)
    return out


@api_router.post("/profile/roblox", response_model=UserOut)
async def profile_roblox(payload: RobloxIn, request: Request):
    user = await require_user(request)
    fields = profile_fields(payload.roblox_display_name, payload.roblox_nick, payload.roblox_link)
    nick = fields["roblox_nick"]
    pattern = f"^{re.escape(nick)}$"
    taken = await db.users.find_one({"roblox_nick": {"$regex": pattern, "$options": "i"}, "session_id": {"$ne": user["session_id"]}}, {"_id": 1})
    if taken:
        raise HTTPException(status_code=400, detail="Этот Roblox-ник уже привязан к другому аккаунту")
    try:
        await db.users.update_one({"session_id": user["session_id"]}, {"$set": {**fields, "roblox_nick_normalized": nick.lower()}})
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Этот Roblox-ник уже привязан к другому аккаунту")
    user.update(fields)
    return to_user_out(user)


async def player_stats(sid: str) -> dict:
    games, withdrawals = await asyncio.gather(
        db.upgrades.aggregate([
            {"$match": {"session_id": sid}},
            {"$group": {"_id": None, "upgrades": {"$sum": 1}, "wins": {"$sum": {"$cond": ["$win", 1, 0]}}}},
            {"$project": {"_id": 0}},
        ]).to_list(1),
        db.withdrawals.aggregate([
            {"$match": {"session_id": sid, "status": "done"}},
            {"$group": {"_id": None, "withdrawn_count": {"$sum": 1}, "withdrawn_sum": {"$sum": "$item.price"}}},
            {"$project": {"_id": 0}},
        ]).to_list(1),
    )
    return {
        **(games[0] if games else {"upgrades": 0, "wins": 0}),
        **(withdrawals[0] if withdrawals else {"withdrawn_count": 0, "withdrawn_sum": 0.0}),
    }


@api_router.get("/profile")
async def profile(request: Request):
    user = await require_user(request)
    sid = user["session_id"]
    upgrades = await db.upgrades.find({"session_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(100)
    best = await db.drops.find({"session_id": sid}, {"_id": 0}).sort("item_price", -1).to_list(1)
    history = await db.item_history.find({"session_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(100)
    withdrawals = await db.withdrawals.find({"session_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {
        "user": to_user_out(user).model_dump(),
        "stats": await player_stats(sid),
        "best_drop": best[0] if best else None,
        "item_history": history,
        "withdrawals": withdrawals,
        "games": [
            {
                "id": u["id"],
                "created_at": u["created_at"],
                "bet_amount": u.get("bet_amount", 0),
                "items_total": u.get("items_total", 0),
                "chance": u.get("display_chance", u.get("chance")),
                "display_chance": u.get("display_chance", u.get("chance")),
                "cashback": float(u.get("cashback") or 0),
                "win": u.get("win"),
                "target": u.get("target_item"),
            }
            for u in upgrades
        ],
    }


@api_router.get("/referrals")
async def my_referrals(request: Request):
    user = await require_user(request)
    return await referrals.summary(db, user["session_id"], APP_URL)


@api_router.post("/skins/sell", response_model=UserOut)
@serialized_user_action
async def skins_sell(payload: UidsIn, request: Request):
    user = await require_user(request)
    skins = await take_skins(user, payload.uids, credit=True)
    await db.item_history.insert_many(
        [{"id": str(uuid.uuid4()), "session_id": user["session_id"], "kind": "sold", "item": sk, "price": float(sk.get("price") or 0), "created_at": now_utc()} for sk in skins]
    )
    fresh = await db.users.find_one({"session_id": user["session_id"]}, {"_id": 0})
    return to_user_out(fresh)


@api_router.post("/skins/withdraw", response_model=UserOut)
@serialized_user_action
async def skins_withdraw(payload: UidsIn, request: Request):
    user = await require_user(request)
    if not user.get("roblox_nick") or not user.get("roblox_link"):
        raise HTTPException(status_code=400, detail="Сначала привяжите Roblox-профиль для получения скинов")
    uids = payload.uids
    owned = {sk.get("uid"): sk for sk in user.get("skins", []) if sk.get("uid")}
    if not uids or len(uids) > 200 or len(set(uids)) != len(uids) or any(u not in owned for u in uids):
        raise HTTPException(status_code=400, detail="Выбранных скинов нет в вашем инвентаре")
    if any(float((owned[u] or {}).get("price") or 0) < 20 for u in uids):
        raise HTTPException(status_code=400, detail="Минимальная цена скина для вывода — 20 RAP")
    since_24h = now_utc() - timedelta(hours=24)
    recent = await db.withdrawals.count_documents(
        {"session_id": user["session_id"], "status": {"$in": ["pending", "done"]}, "created_at": {"$gte": since_24h}}
    )
    if recent + len(uids) > 10:
        raise HTTPException(status_code=400, detail="Максимум 10 предметов на вывод в сутки")
    now, op_id = now_utc(), str(uuid.uuid4())
    recipient = {k: user.get(k) for k in ("roblox_nick", "roblox_display_name", "roblox_link")}
    # Intent first: if the process stops after the skins are removed, startup recovery finishes these requests.
    withdrawals = [{"id": str(uuid.uuid4()), "session_id": user["session_id"], "item": owned[u], "status": "reserving",
                    "op_id": op_id, "recipient": recipient, "created_at": now} for u in uids]
    await db.withdrawals.insert_many([dict(w) for w in withdrawals])
    try:
        await take_skins(user, uids, op_id=op_id)
    except Exception:
        await db.withdrawals.delete_many({"op_id": op_id, "status": "reserving"})
        raise
    await finish_withdrawal_op(user["session_id"], op_id)
    fresh = await db.users.find_one({"session_id": user["session_id"]}, {"_id": 0})
    return to_user_out(fresh)


async def finish_withdrawal_op(session_id: str, op_id: str) -> None:
    rows = await db.withdrawals.find({"op_id": op_id, "status": {"$in": ["reserving", "pending"]}}, {"_id": 0}).to_list(None)
    for w in rows:
        await db.item_history.update_one({"id": f"withdrawal:{w['id']}"}, {"$setOnInsert": {
            "withdrawal_id": w["id"], "session_id": session_id, "kind": "withdraw_requested",
            "item": w["item"], "price": float(w["item"].get("price") or 0), "created_at": w["created_at"],
        }}, upsert=True)
    await db.withdrawals.update_many({"op_id": op_id, "status": "reserving"}, {"$set": {"status": "pending"}})
    await db.users.update_one({"session_id": session_id}, {"$pull": {"withdrawal_ops": op_id}})


async def resume_withdrawal_ops() -> None:
    stale = now_utc() - timedelta(minutes=5)
    ops = await db.withdrawals.aggregate([
        {"$match": {"status": "reserving", "created_at": {"$lt": stale}}},
        {"$group": {"_id": "$op_id", "session_id": {"$first": "$session_id"}}},
    ]).to_list(None)
    for op in ops:
        if await db.users.find_one({"session_id": op["session_id"], "withdrawal_ops": op["_id"]}, {"_id": 1}):
            await finish_withdrawal_op(op["session_id"], op["_id"])
        else:
            await db.withdrawals.delete_many({"op_id": op["_id"], "status": "reserving"})


# ---------- Notifications ----------
@api_router.get("/notifications")
async def my_notifications(request: Request):
    return await operation_notifications(db, await require_user(request))


@api_router.post("/notifications/read")
async def read_notifications(payload: NotificationsReadIn, request: Request):
    user = await require_user(request)
    read_at = min(as_utc(payload.read_through), now_utc())
    await db.users.update_one({"session_id": user["session_id"]}, {"$max": {"notifications_read_at": read_at}})
    return {"ok": True}


# ---------- Deposits ----------
def deposit_public(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "_id"}


@api_router.post("/deposits")
@serialized_user_action
async def create_deposit(payload: DepositIn, request: Request):
    user = await require_user(request)
    require_roblox_profile(user)
    receiver = next((r for r in RECEIVERS if r["id"] == payload.receiver_id), None)
    if not receiver:
        raise HTTPException(status_code=400, detail="Профиль для трейда не найден")
    last = await db.deposits.find_one({"session_id": user["session_id"]}, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
    if last and (now_utc() - as_utc(last["created_at"])).total_seconds() < DEPOSIT_COOLDOWN_SECONDS:
        wait = int(DEPOSIT_COOLDOWN_SECONDS - (now_utc() - as_utc(last["created_at"])).total_seconds())
        raise HTTPException(status_code=429, detail=f"Не так быстро: следующую заявку можно отправить через {max(1, wait)} сек")
    await require_no_active_skin_deposit(user["session_id"])
    doc = {
        "id": str(uuid.uuid4()),
        "session_id": user["session_id"],
        "nickname": user.get("nickname"),
        "discord_id": user.get("discord_id"),
        "roblox_nick": user.get("roblox_nick"),
        "roblox_link": user.get("roblox_link"),
        "description": payload.description.strip(),
        "expected_rap": round(payload.expected_rap, 2),
        "receiver_id": receiver["id"],
        "receiver_nick": receiver["nickname"],
        "promo_id": user.get("promo_id"),
        "promo_code": user.get("promo_code"),
        "promo_bonus": float(user.get("promo_bonus") or 0),
        "status": "pending",
        "amount": None,
        "created_at": now_utc(),
        "resolved_at": None,
    }
    await db.deposits.insert_one(dict(doc))
    return doc


@api_router.post("/deposits/{deposit_id}/cancel")
async def cancel_deposit(deposit_id: str, request: Request):
    user = await require_user(request)
    # Staff requests can be cancelled only before the skin transfer has started.
    res = await db.deposits.update_one(
        {"id": deposit_id, "session_id": user["session_id"], "status": "pending",
         "transfer_started_at": None, "staff_state": {"$in": [None, "assigned"]}},
        {"$set": {"status": "cancelled", "resolved_at": now_utc(), "staff_state": None}},
    )
    if not res.matched_count:
        if await db.deposits.find_one({"id": deposit_id, "session_id": user["session_id"], "status": "pending"}, {"_id": 1}):
            raise HTTPException(status_code=409, detail="Передача скинов уже началась — отменить заявку нельзя. Напишите в чат")
        raise HTTPException(status_code=404, detail="Заявка не найдена или уже обработана")
    return {"ok": True}


@api_router.get("/deposits/my")
async def my_deposits(request: Request):
    user = await require_user(request)
    active = {"$in": ["pending", "processing", "creating", "awaiting_payment"]}
    pending = await db.deposits.find({"session_id": user["session_id"], "status": active}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    history = await db.deposits.find({"session_id": user["session_id"], "status": {"$nin": active["$in"]}}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return pending + history


# ---------- xRocket payments ----------
@api_router.get("/payments/xrocket/info")
async def xrocket_info():
    return {"enabled": xrocket.enabled, "min_rub": float(xp.MIN_RUB), "max_rub": float(xp.MAX_RUB),
            "rap_rub_rate": float(xp.RAP_RUB_RATE), "site_fee": 0, "fee_paid_by_user": True,
            "currencies": list(xp.CURRENCIES)}


@api_router.post("/payments/xrocket/invoices")
@serialized_user_action
async def xrocket_create_invoice(payload: XrocketInvoiceIn, request: Request):
    user = await require_user(request)
    require_roblox_profile(user)
    return await xp.create_invoice(db, xrocket, user, payload.request_id, payload.amount_rub, payload.currency, APP_URL)


@api_router.get("/payments/xrocket/invoices")
async def xrocket_my_invoices(request: Request):
    user = await require_user(request)
    docs = await db.deposits.find({"session_id": user["session_id"], "payment_method": "xrocket"}, {"_id": 0}).sort("created_at", -1).to_list(20)
    return [xp.public_invoice(doc) for doc in docs]


async def require_xrocket_invoice(invoice_id, request):
    user = await require_user(request)
    doc = await db.deposits.find_one({"id": invoice_id, "session_id": user["session_id"], "payment_method": "xrocket"}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Счёт не найден")
    return doc


@api_router.get("/payments/xrocket/invoices/{invoice_id}")
async def xrocket_invoice_status(invoice_id: str, request: Request):
    return xp.public_invoice(await require_xrocket_invoice(invoice_id, request))


@api_router.post("/payments/xrocket/invoices/{invoice_id}/refresh")
async def xrocket_refresh_invoice(invoice_id: str, request: Request):
    doc = await require_xrocket_invoice(invoice_id, request)
    return xp.public_invoice(await xp.synchronize(db, xrocket, doc))


@api_router.post("/payments/xrocket/webhook")
async def xrocket_webhook(request: Request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65_536:
            raise HTTPException(413, "Слишком большое событие")
    if not xrocket.verify_signature(bytes(raw), request.headers):
        raise HTTPException(401, "Неверная подпись xRocket")
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Некорректное событие xRocket")
    await xp.handle_event(db, xrocket, event)
    return {"ok": True}


# ---------- CryptoBot payments ----------
@api_router.get("/payments/cryptobot/info")
async def cryptobot_info():
    return {"enabled": cryptobot.enabled, "min_rub": float(cb.MIN_RUB), "max_rub": float(cb.MAX_RUB),
            "rap_rub_rate": float(cb.RAP_RUB_RATE), "site_fee": 0, "fee_paid_by_user": False,
            "currencies": list(cb.ASSETS)}


@api_router.post("/payments/cryptobot/invoices")
@serialized_user_action
async def cryptobot_create_invoice(payload: CryptobotInvoiceIn, request: Request):
    user = await require_user(request)
    require_roblox_profile(user)
    return await cb.create_invoice(db, cryptobot, user, payload.request_id, payload.amount_rub, payload.currency, APP_URL)


@api_router.get("/payments/cryptobot/invoices")
async def cryptobot_my_invoices(request: Request):
    user = await require_user(request)
    docs = await db.deposits.find({"session_id": user["session_id"], "payment_method": "cryptobot"}, {"_id": 0}).sort("created_at", -1).to_list(20)
    return [cb.public_invoice(doc) for doc in docs]


async def require_cryptobot_invoice(invoice_id, request):
    user = await require_user(request)
    doc = await db.deposits.find_one({"id": invoice_id, "session_id": user["session_id"], "payment_method": "cryptobot"}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Счёт не найден")
    return doc


@api_router.get("/payments/cryptobot/invoices/{invoice_id}")
async def cryptobot_invoice_status(invoice_id: str, request: Request):
    return cb.public_invoice(await require_cryptobot_invoice(invoice_id, request))


@api_router.post("/payments/cryptobot/invoices/{invoice_id}/refresh")
async def cryptobot_refresh_invoice(invoice_id: str, request: Request):
    doc = await require_cryptobot_invoice(invoice_id, request)
    return cb.public_invoice(await cb.synchronize(db, cryptobot, doc))


@api_router.post("/payments/cryptobot/webhook")
async def cryptobot_webhook(request: Request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65_536:
            raise HTTPException(413, "Слишком большое событие")
    if not cryptobot.verify_signature(bytes(raw), request.headers):
        raise HTTPException(401, "Неверная подпись CryptoBot")
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Некорректное событие CryptoBot")
    await cb.handle_event(db, cryptobot, event)
    return {"ok": True}


# ---------- Live chat ----------
GUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")


async def chat_identity(request: Request) -> tuple:
    """Owner key and display profile: logged-in user, or an anonymous browser session."""
    user = await token_user(request)
    if user:
        return user["session_id"], {**user, "registered": True}
    guest = request.headers.get("x-session-id", "").strip()
    if not GUEST_ID_RE.match(guest):
        raise HTTPException(status_code=401, detail="Не авторизован")
    return f"guest:{guest}", {"nickname": f"Гость {guest[:4]}", "registered": False}


@api_router.get("/chats")
async def chats_mine(request: Request):
    owner, _ = await chat_identity(request)
    return await chat.my_chats(db, owner)


@api_router.post("/chats", status_code=201)
async def chats_create(payload: ChatCreateIn, request: Request):
    if payload.kind == "deposit":
        return await create_deposit_chat(payload, request)
    return await _create_chat(payload, request)


@serialized_user_action
async def create_deposit_chat(payload: ChatCreateIn, request: Request):
    return await _create_chat(payload, request)


async def require_no_active_skin_deposit(owner):
    pending = await db.deposits.count_documents({"session_id": owner, "status": {"$in": ["pending", "processing"]}, "payment_method": {"$nin": ["xrocket", "cryptobot"]}})
    if pending:
        raise HTTPException(409, "У вас уже есть активная заявка на пополнение скинами. Дождитесь её завершения или отмените её в разделе «Заявки»")


async def _create_chat(payload: ChatCreateIn, request: Request):
    owner, profile = await chat_identity(request)
    if payload.for_topup:
        if not profile.get("registered"):
            raise HTTPException(401, "Войдите, чтобы пополнить баланс")
        require_roblox_profile(profile)
    deposit = None
    if payload.kind == "deposit":
        if not profile.get("registered"):
            raise HTTPException(status_code=401, detail="Войдите, чтобы создать заявку на пополнение")
        require_roblox_profile(profile)
        if not payload.expected_rap:
            raise HTTPException(status_code=400, detail="Укажите примерный RAP")
        await require_no_active_skin_deposit(owner)
        receiver = RECEIVERS[0]
        deposit = {
            "id": str(uuid.uuid4()), "session_id": owner, "nickname": profile.get("nickname"), "discord_id": profile.get("discord_id"),
            "roblox_nick": profile.get("roblox_nick"), "roblox_display_name": profile.get("roblox_display_name"), "roblox_link": profile.get("roblox_link"),
            "description": f"Запрос через лайв-чат · ~{payload.expected_rap:.2f} RAP",
            "expected_rap": round(payload.expected_rap, 2), "receiver_id": receiver["id"], "receiver_nick": receiver["nickname"],
            "promo_id": profile.get("promo_id"), "promo_code": profile.get("promo_code"), "promo_bonus": float(profile.get("promo_bonus") or 0),
            "status": "pending", "amount": None, "created_at": now_utc(), "resolved_at": None, "via_chat": True,
        }
    created = await chat.create_chat(db, owner, profile, payload.kind, payload.text, deposit, request_lang(request))
    if payload.kind == "withdrawal":
        if not profile.get("registered"):
            raise HTTPException(status_code=401, detail="Войдите, чтобы получить скины")
        rows = await db.withdrawals.find({"session_id": owner, "status": "pending"}, {"_id": 0, "item": 1}).to_list(100)
        if rows:
            await chat.post_withdrawal_request(db, created, rows)
            created = await db.chats.find_one({"id": created["id"]}, {"_id": 0})
    if deposit:
        deposit["chat_id"] = created["id"]
        await db.deposits.insert_one(dict(deposit))
    return created


@api_router.get("/chats/{chat_id}/messages")
async def chats_messages(chat_id: str, request: Request, after: Optional[str] = None):
    owner, _ = await chat_identity(request)
    found = await chat.get_owned_chat(db, chat_id, owner)
    since = None
    if after:
        try:
            since = datetime.fromisoformat(after.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверная дата")
    rows = await chat.messages(db, chat_id, since)
    await chat.mark_read(db, chat_id, "user")
    return {"chat": {**found, "user_unread": 0}, "messages": rows}


@api_router.post("/chats/{chat_id}/messages", status_code=201)
async def chats_send(chat_id: str, payload: ChatMessageIn, request: Request):
    owner, _ = await chat_identity(request)
    found = await chat.get_owned_chat(db, chat_id, owner)
    if found["status"] == "closed":
        raise HTTPException(status_code=409, detail="Чат завершён — откройте его заново")
    await remember_chat_lang(found, request)
    return await chat.post_message(db, found, "user", payload.text)


@api_router.post("/chats/{chat_id}/attachments", status_code=201)
async def chats_attach(chat_id: str, request: Request, file: UploadFile = File(...)):
    # Screenshots only from Discord accounts; limits and 3-day expiry live in chat_attachments.
    user = await require_user(request)
    found = await chat.get_owned_chat(db, chat_id, user["session_id"])
    if found["status"] == "closed":
        raise HTTPException(status_code=409, detail="Чат завершён — откройте его заново")
    data = await file.read(chat_attachments.MAX_BYTES + 1)
    meta = await chat_attachments.store(db, found, user["session_id"], data, now_utc())
    await remember_chat_lang(found, request)
    return await chat.post_message(db, found, "user", tr("screenshot", chat.lang_of(found)),
                                   {"kind": "image", "attachment_id": meta["id"], "expires_at": meta["expires_at"]})


def attachment_response(doc) -> Response:
    return Response(bytes(doc["data"]), media_type=doc["content_type"], headers={
        "Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})


@api_router.get("/chats/{chat_id}/attachments/{attachment_id}")
async def chats_attachment(chat_id: str, attachment_id: str, request: Request):
    owner, _ = await chat_identity(request)
    await chat.get_owned_chat(db, chat_id, owner)
    return attachment_response(await chat_attachments.load(db, chat_id, attachment_id))


@api_router.get("/admin/chats/{chat_id}/attachments/{attachment_id}")
async def admin_chat_attachment(chat_id: str, attachment_id: str, request: Request):
    await require_admin(request)
    return attachment_response(await chat_attachments.load(db, chat_id, attachment_id))


class DonationRequestIn(InputModel):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: float = Field(gt=0, le=100_000_000)


@api_router.post("/donationalerts/requests", status_code=201)
@serialized_user_action
async def donation_request(payload: DonationRequestIn, request: Request):
    user = await require_user(request)
    require_roblox_profile(user)
    await require_no_active_skin_deposit(user["session_id"])
    return await dp.create_request(db, user, payload.currency, payload.amount, request_lang(request), RECEIVERS[0])


@api_router.post("/donationalerts/requests/{deposit_id}/paid")
async def donation_paid(deposit_id: str, request: Request):
    user = await require_user(request)
    return await dp.claim_paid(db, tg_bot, user, deposit_id)


@api_router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    if not tg_bot.enabled or not hmac.compare_digest(request.headers.get("x-telegram-bot-api-secret-token", ""), tg_bot.secret):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        update = await request.json()
        if staff_bot.shared and staff_bot.enabled and await staff_telegram.owns(db, update):
            await staff_telegram.handle_update(db, staff_bot, update)
        else:
            await dp.handle_update(db, tg_bot, update, notify_deposit_rejected)
    except Exception:
        logger.exception("Telegram update failed")
    return {"ok": True}


@api_router.get("/admin/telegram")
async def admin_telegram_status(request: Request):
    await require_admin(request)
    info = {}
    if tg_bot.enabled:
        with suppress(Exception):
            info = await tg_bot.call("getWebhookInfo")
    expected = f"{APP_URL}/api/telegram/webhook"
    return {"enabled": tg_bot.enabled, "donationalerts_url": dp.da_url(), "webhook_url": info.get("url"), "expected_url": expected,
            "connected": info.get("url") == expected, "last_error": info.get("last_error_message")}


@api_router.post("/admin/telegram/setup")
async def admin_telegram_setup(request: Request):
    await require_admin(request)
    if not tg_bot.enabled:
        raise HTTPException(status_code=409, detail="Не заданы TELEGRAM_BOT_TOKEN / TELEGRAM_ADMIN_ID")
    try:
        url = await dp.setup_webhook(tg_bot, APP_URL)
    except Exception as error:
        raise HTTPException(status_code=409, detail=f"Telegram: {error}") from None
    try:
        await tg_bot.call("sendMessage", {"chat_id": tg_bot.admin_id, "text": f"✅ Бот подключён к сайту {APP_URL}. Сюда будут приходить оплаты DonationAlerts на проверку."})
    except Exception:
        # Telegram lets a bot write only after the owner pressed /start in it.
        return {"ok": True, "webhook_url": url, "warning": "Вебхук подключён, но бот не может написать вам: откройте бота в Telegram и нажмите /start"}
    return {"ok": True, "webhook_url": url}


@api_router.post("/admin/telegram/test")
async def admin_telegram_test(request: Request):
    await require_admin(request)
    if not tg_bot.enabled:
        raise HTTPException(status_code=409, detail="Не заданы TELEGRAM_BOT_TOKEN / TELEGRAM_ADMIN_ID")
    try:
        await dp.send_test(tg_bot)
    except Exception as error:
        raise HTTPException(status_code=409, detail=f"Telegram: {error}. Откройте бота и нажмите /start") from None
    return {"ok": True}


async def remember_chat_lang(found: dict, request: Request) -> None:
    lang = request_lang(request) if request.headers.get("x-lang") else None
    if lang and found.get("lang") != lang:
        found["lang"] = lang
        await db.chats.update_one({"id": found["id"]}, {"$set": {"lang": lang}})


@api_router.post("/chats/{chat_id}/close")
async def chats_close(chat_id: str, request: Request):
    owner, _ = await chat_identity(request)
    found = await chat.get_owned_chat(db, chat_id, owner)
    await remember_chat_lang(found, request)
    return await chat.user_close(db, found)


@api_router.post("/chats/{chat_id}/reopen")
async def chats_reopen(chat_id: str, request: Request):
    owner, _ = await chat_identity(request)
    found = await chat.get_owned_chat(db, chat_id, owner)
    await remember_chat_lang(found, request)
    return await chat.user_reopen(db, found)


@api_router.get("/admin/chats")
async def admin_chats(request: Request, status: str = "open", q: Optional[str] = None,
                      offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
    await require_admin(request)
    return await chat.admin_list(db, status, q, offset, limit)


@api_router.get("/admin/search")
async def admin_search(request: Request, q: str = ""):
    await require_admin(request)
    return await chat.search_users(db, q)


@api_router.get("/admin/chats/summary")
async def admin_chats_summary(request: Request):
    await require_admin(request)
    return await chat.admin_summary(db)


async def _chat_owner_user(found: dict) -> Optional[dict]:
    if found.get("guest") or str(found.get("owner", "")).startswith("guest:"):
        return None
    u = await db.users.find_one({"session_id": found["owner"]}, {"_id": 0, "session_id": 1, "nickname": 1, "discord_id": 1, "roblox_nick": 1, "roblox_display_name": 1, "roblox_link": 1, "balance": 1, "skins.price": 1, "promo_code": 1, "promo_bonus": 1, "created_at": 1})
    if not u:
        return None
    skins = u.pop("skins", []) or []
    return {**u, "balance": float(u.get("balance") or 0), "skins_count": len(skins), "skins_total": round(sum(float(s.get("price") or 0) for s in skins), 2)}


@api_router.get("/admin/chats/{chat_id}/messages")
async def admin_chat_messages(chat_id: str, request: Request):
    await require_admin(request)
    found = await chat.require_chat(db, chat_id)
    rows = await chat.messages(db, chat_id)
    await chat.mark_read(db, chat_id, "admin")
    user = await _chat_owner_user(found)
    found = (await chat.enrich_chats(db, [found]))[0]
    if user:
        user["online"] = found["online"]
    deposits, withdrawals = [], []
    if user:
        deposits = await db.deposits.find({"session_id": found["owner"], "status": {"$in": ["pending", "processing"]}, "payment_method": {"$nin": ["xrocket", "cryptobot"]}}, {"_id": 0}).sort("created_at", 1).to_list(20)
        withdrawals = await db.withdrawals.find({"session_id": found["owner"], "status": {"$in": ["pending", "cancelling", "paying"]}}, {"_id": 0}).sort("created_at", 1).to_list(100)
        for w in withdrawals:
            w["recipient_changed"] = recipient_changed({**w, "user": user})
    return {"chat": {**found, "admin_unread": 0}, "messages": rows, "user": user, "deposits": deposits, "withdrawals": withdrawals,
            "withdrawals_total": round(sum(float((w.get("item") or {}).get("price") or 0) for w in withdrawals), 2)}


@api_router.post("/admin/chats/{chat_id}/deposit/preview")
async def admin_chat_deposit_preview(chat_id: str, payload: AdminConfirmIn, request: Request):
    await require_admin(request)
    found = await chat.require_chat(db, chat_id)
    user = await _chat_owner_user(found)
    if not user:
        raise HTTPException(status_code=400, detail="Гостю пополнить нельзя")
    if payload.rap < MIN_DEPOSIT_RAP:
        raise HTTPException(400, f"Минимальная сумма — {MIN_DEPOSIT_RAP} RAP")
    dep = await db.deposits.find_one({"session_id": found["owner"], "status": "processing", "payment_method": {"$nin": ["xrocket", "cryptobot"]}}, {"_id": 0})
    if dep:
        return {k: dep[k] for k in ("rap", "credited", "issued_skins", "skins_total", "balance_credited")}
    return await plan_deposit(db, {"promo_bonus": float(user.get("promo_bonus") or 0)}, payload.rap)


@api_router.post("/admin/chats/{chat_id}/deposit")
async def admin_chat_deposit(chat_id: str, payload: AdminConfirmIn, request: Request):
    await require_admin(request)
    found = await chat.require_chat(db, chat_id)
    user = await _chat_owner_user(found)
    if not user:
        raise HTTPException(status_code=400, detail="Гостю пополнить нельзя — игрок должен войти через Discord")
    if payload.rap < MIN_DEPOSIT_RAP:
        raise HTTPException(status_code=400, detail=f"Минимальная сумма пополнения — {MIN_DEPOSIT_RAP} RAP")
    request_key = f"chat:{chat_id}:{payload.request_id}" if payload.request_id else None
    dep = await db.deposits.find_one({"admin_request_id": request_key}, {"_id": 0}) if request_key else None
    if dep:
        # Repeated command (lost response): return the first result instead of crediting again.
        if dep["session_id"] != found["owner"]:
            raise HTTPException(status_code=409, detail="Этот идентификатор команды уже использован")
        await require_not_staff_request(dep)
        result = await confirm_deposit(db, dep["id"], payload.rap, payload.note or "через чат")
        return {**result, "deposit_id": dep["id"]}
    dep = await db.deposits.find_one({"session_id": found["owner"], "status": "pending", "payment_method": {"$nin": ["xrocket", "cryptobot"]}}, {"_id": 0}, sort=[("created_at", 1)])
    await require_not_staff_request(dep)
    if dep and request_key:
        claimed = await db.deposits.update_one({"id": dep["id"], "status": "pending", "admin_request_id": {"$exists": False}}, {"$set": {"admin_request_id": request_key}})
        if not claimed.modified_count:
            raise HTTPException(status_code=409, detail="Заявка уже обрабатывается другой командой. Обновите чат")
    if not dep:
        require_roblox_profile(user)
        full = await db.users.find_one({"session_id": found["owner"]}, {"_id": 0})
        receiver = RECEIVERS[0]
        dep = {
            "id": str(uuid.uuid4()), "session_id": found["owner"], "nickname": full.get("nickname"), "discord_id": full.get("discord_id"),
            "roblox_nick": full.get("roblox_nick"), "roblox_display_name": full.get("roblox_display_name"), "roblox_link": full.get("roblox_link"),
            "description": f"Пополнение оператором через чат · {payload.rap:.2f} RAP",
            "expected_rap": round(payload.rap, 2), "receiver_id": receiver["id"], "receiver_nick": receiver["nickname"],
            "promo_id": full.get("promo_id"), "promo_code": full.get("promo_code"), "promo_bonus": float(full.get("promo_bonus") or 0),
            "status": "pending", "amount": None, "created_at": now_utc(), "resolved_at": None, "via_chat": True, "chat_id": chat_id,
            **({"admin_request_id": request_key} if request_key else {}),
        }
        try:
            await db.deposits.insert_one(dict(dep))
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Команда уже выполняется. Обновите чат") from None
    result = await confirm_deposit(db, dep["id"], payload.rap, payload.note or "через чат")
    if not result.get("already_confirmed"):
        await chat.post_message(db, found, "system", tr("deposit_confirmed", chat.lang_of(found), credited=float(result.get("credited") or 0)))
    return {**result, "deposit_id": dep["id"]}


@api_router.post("/admin/chats/{chat_id}/withdrawals/done")
async def admin_chat_withdrawals_done(chat_id: str, request: Request):
    await require_admin(request)
    found = await chat.require_chat(db, chat_id)
    rows = await db.withdrawals.find({"session_id": found["owner"], "status": "pending"}, {"_id": 0, "id": 1}).to_list(100)
    done, total = 0, 0.0
    for row in rows:
        w = await _withdrawal_done(row["id"])
        if w:
            done += 1
            total += float((w.get("item") or {}).get("price") or 0)
    if done:
        await chat.post_message(db, found, "system", tr("skins_issued", chat.lang_of(found), done=done, total=total))
    return {"ok": True, "done": done, "total": round(total, 2)}


@api_router.post("/admin/chats/{chat_id}/accept")
async def admin_chat_accept(chat_id: str, request: Request):
    sess = await require_admin(request)
    return await chat.accept(db, chat_id, sess["jti"][:8])


@api_router.post("/admin/chats/{chat_id}/messages", status_code=201)
async def admin_chat_send(chat_id: str, payload: ChatMessageIn, request: Request):
    await require_admin(request)
    found = await chat.require_chat(db, chat_id)
    text = await admin_commands.expand(db, payload.text)
    if found["status"] != "active":
        found = await chat.accept(db, chat_id, "operator")
    return await chat.post_message(db, found, "admin", text)


@api_router.post("/admin/chats/{chat_id}/close")
async def admin_chat_close(chat_id: str, request: Request):
    await require_admin(request)
    return await chat.close(db, chat_id)


# ---------- Admin ----------
@api_router.get("/admin/commands")
async def admin_command_list(request: Request):
    await require_admin(request)
    return await admin_commands.list_commands(db)


@api_router.post("/admin/commands", status_code=201)
async def admin_command_create(payload: AdminCommandIn, request: Request):
    admin = await require_admin(request)
    return await admin_commands.save_command(db, payload.command, payload.text, admin["jti"])


@api_router.put("/admin/commands/{command_id}")
async def admin_command_update(command_id: str, payload: AdminCommandIn, request: Request):
    admin = await require_admin(request)
    return await admin_commands.save_command(db, payload.command, payload.text, admin["jti"], command_id)


@api_router.delete("/admin/commands/{command_id}")
async def admin_command_delete(command_id: str, request: Request):
    admin = await require_admin(request)
    return await admin_commands.delete_command(db, command_id, admin["jti"])


@api_router.post("/admin/players/{session_id}/coins")
async def admin_player_coins(session_id: str, payload: AdminCoinsIn, request: Request):
    admin = await require_admin(request)
    amount = payload.amount_rub * admin_coins.COINS_PER_RUB if payload.amount_rub is not None else payload.amount
    return await admin_coins.credit(db, session_id, str(payload.request_id), amount, payload.note.strip(), admin["jti"], amount_rub=payload.amount_rub)


@api_router.get("/admin/players/{session_id}/coins")
async def admin_player_coin_history(session_id: str, request: Request):
    await require_admin(request)
    return [admin_coins.public(row) for row in await db.admin_coin_grants.find({"session_id": session_id, "status": {"$ne": "reset"}}).sort("created_at", -1).to_list(10)]


def _promo_public(row: dict, unique_users: int) -> dict:
    out = {**row, "unique_users": unique_users}
    kind = promos.promo_type(row)
    out["type"] = kind
    # Never expose the booking key list (size + privacy); counts are enough.
    out.pop("reserved_keys", None)
    if kind == promos.PROMO_TYPE_RAP:
        out.pop("percent", None)
        out["amount_rap"] = float(row.get("amount_rap") or 0)
        out["max_uses"] = row.get("max_uses")
        out["reserved_count"] = int(row.get("reserved_count") or 0)
        out["used_count"] = unique_users
    else:
        out.pop("amount_rap", None)
        out.pop("max_uses", None)
        out.pop("expires_at", None)
        out.pop("reserved_count", None)
    return out


async def _rap_usage_counts(promo_ids):
    if not promo_ids:
        return {}
    counts = {}
    try:
        async for row in db.promo_gift_ops.aggregate([
            {"$match": {"promo_id": {"$in": promo_ids}, "status": {"$in": ["reserved", "redeemed"]}}},
            {"$group": {"_id": "$promo_id", "count": {"$sum": 1}}},
        ]):
            counts[row["_id"]] = row["count"]
    except Exception:
        # mongomock fallback: count per promo.
        for pid in promo_ids:
            counts[pid] = await db.promo_gift_ops.count_documents(
                {"promo_id": pid, "status": {"$in": ["reserved", "redeemed"]}})
    return counts


@api_router.get("/admin/promos")
async def admin_promos(request: Request):
    await require_admin(request)
    rows = await db.promo_codes.find({"deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(None)
    ids = [p["id"] for p in rows]
    counts = {row["_id"]: row["count"] async for row in db.promo_activations.aggregate([
        {"$match": {"promo_id": {"$in": ids}}},
        {"$group": {"_id": "$promo_id", "count": {"$sum": 1}}},
    ])} if ids else {}
    rap_counts = await _rap_usage_counts(
        [p["id"] for p in rows if promos.promo_type(p) == promos.PROMO_TYPE_RAP])
    out = []
    for p in rows:
        if promos.promo_type(p) == promos.PROMO_TYPE_RAP:
            out.append(_promo_public(p, rap_counts.get(p["id"], 0)))
        else:
            out.append(_promo_public(p, counts.get(p["id"], 0)))
    return out


@api_router.get("/admin/promo-gifts")
async def admin_promo_gifts(request: Request, promo_id: Optional[str] = None, limit: int = 100):
    """Separate gift journal (audit only): who received how much and when.

    Never a deposit, never bank/pool, never a deposit referral reward.
    """
    await require_admin(request)
    limit = max(1, min(limit or 100, 500))
    query = {"promo_id": promo_id} if promo_id else {}
    try:
        docs = await db.promo_gifts.find(query, {"_id": 0}).sort("redeemed_at", -1).to_list(limit)
    except Exception:
        docs = await db.promo_gift_ops.find(
            {**query, "status": "redeemed"}, {"_id": 0}).sort("redeemed_at", -1).to_list(limit)
    return docs


@api_router.post("/admin/promos", status_code=201)
async def admin_create_promo(payload: AdminPromoIn, request: Request):
    admin = await require_admin(request)
    code = payload.code.strip().upper()
    kind = payload.type or promos.PROMO_TYPE_DEPOSIT
    if kind == promos.PROMO_TYPE_RAP and not promos.rap_fixed_enabled():
        raise HTTPException(status_code=400, detail=promos.RAP_DISABLED_MESSAGE)
    if kind == promos.PROMO_TYPE_DEPOSIT:
        promo = {
            "id": str(uuid.uuid4()), "code": code, "type": promos.PROMO_TYPE_DEPOSIT,
            "percent": float(payload.percent),
            "gold_nick": False, "deleted": False, "created_at": now_utc(),
        }
    else:
        amount = promos.validate_rap_amount(payload.amount_rap)
        max_uses = promos.validate_max_uses(payload.max_uses)
        promo = {
            "id": str(uuid.uuid4()), "code": code, "type": promos.PROMO_TYPE_RAP,
            "amount_rap": amount, "max_uses": max_uses,
            "expires_at": as_utc(payload.expires_at) if payload.expires_at else None,
            "reserved_count": 0, "reserved_keys": [],
            "gold_nick": False, "deleted": False, "created_at": now_utc(),
        }
    try:
        await db.promo_codes.insert_one(dict(promo))
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Промокод с таким названием уже существует")
    await db.admin_audit.insert_one({"action": "promo_create", "jti": admin["jti"], "promo": promo, "created_at": now_utc()})
    # Recreation of a deleted code is a NEW promo (new id, zero stats) — warn explicitly.
    warning = None
    try:
        prev = await db.promo_codes.find_one(
            {"code": code, "id": {"$ne": promo["id"]}}, {"_id": 0, "id": 1, "deleted": 1})
        if prev is not None:
            warning = ("Код ранее использовался: это новая акция с чистым счётчиком. "
                       "Старые выдачи сохранены за прежней акцией и не переносятся.")
    except Exception:
        pass
    body = _promo_public(promo, 0)
    if warning:
        body["warning"] = warning
    return body


@api_router.put("/admin/promos/{promo_id}")
async def admin_update_promo(promo_id: str, payload: AdminPromoIn, request: Request):
    admin = await require_admin(request)
    existing = await db.promo_codes.find_one({"id": promo_id}, {"_id": 0})
    if existing is None or existing.get("deleted"):
        raise HTTPException(status_code=404, detail="Промокод не найден")
    old_kind = promos.promo_type(existing)
    new_kind = payload.type or promos.PROMO_TYPE_DEPOSIT
    if new_kind != old_kind:
        raise HTTPException(status_code=400, detail="Смена типа промокода запрещена: создайте новый код")
    code = payload.code.strip().upper()
    if old_kind == promos.PROMO_TYPE_DEPOSIT:
        try:
            promo = await db.promo_codes.find_one_and_update(
                {"id": promo_id, "deleted": False},
                {"$set": {"code": code, "percent": float(payload.percent), "updated_at": now_utc()}},
                projection={"_id": 0}, return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Промокод с таким названием уже существует")
        if promo is None:
            raise HTTPException(status_code=404, detail="Промокод не найден")
        await db.users.update_many({"promo_id": promo_id}, {"$set": promo_fields(promo)})
        await db.admin_audit.insert_one({"action": "promo_update", "jti": admin["jti"], "promo": promo, "created_at": now_utc()})
        return _promo_public(
            promo, await db.promo_activations.count_documents({"promo_id": promo_id}))
    # rap_fixed edit: amount is frozen after the first booking; max_uses may only grow
    # above the already-booked count; rename keeps stats; code clash -> 409.
    used = await db.promo_gift_ops.count_documents(
        {"promo_id": promo_id, "status": {"$in": ["pending", "reserved", "redeemed"]}})
    new_amount = promos.validate_rap_amount(payload.amount_rap)
    new_max = promos.validate_max_uses(payload.max_uses)
    old_amount = round(float(existing.get("amount_rap") or 0), 2)
    if used > 0 and abs(new_amount - old_amount) > 1e-9:
        raise HTTPException(status_code=400, detail="Сумма RAP заморожена после первой брони и не может меняться")
    if new_max < used:
        raise HTTPException(
            status_code=400,
            detail=f"Лимит нельзя опускать ниже уже выданных ({used})")
    new_expires = as_utc(payload.expires_at) if payload.expires_at else None
    try:
        promo = await db.promo_codes.find_one_and_update(
            {"id": promo_id, "deleted": False, "type": promos.PROMO_TYPE_RAP},
            {"$set": {"code": code, "amount_rap": new_amount, "max_uses": new_max,
                      "expires_at": new_expires, "updated_at": now_utc()}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Промокод с таким названием уже существует")
    if promo is None:
        raise HTTPException(status_code=404, detail="Промокод не найден")
    # RAP gifts never own the active percent bonus — no users update here.
    await db.admin_audit.insert_one({"action": "promo_update", "jti": admin["jti"], "promo": promo, "created_at": now_utc()})
    rap_counts = await _rap_usage_counts([promo_id])
    return _promo_public(promo, rap_counts.get(promo_id, 0))


@api_router.delete("/admin/promos/{promo_id}")
async def admin_delete_promo(promo_id: str, request: Request):
    admin = await require_admin(request)
    existing = await db.promo_codes.find_one({"id": promo_id}, {"_id": 0})
    if existing is None or existing.get("deleted"):
        raise HTTPException(status_code=404, detail="Промокод не найден")
    result = await db.promo_codes.update_one({"id": promo_id, "deleted": False}, {"$set": {"deleted": True, "updated_at": now_utc()}})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Промокод не найден")
    if promos.promo_type(existing) == promos.PROMO_TYPE_DEPOSIT:
        await db.users.update_many({"promo_id": promo_id}, {"$set": promo_fields(None)})
    # rap_fixed: deletion revokes nothing already issued; new activations are blocked
    # by the deleted flag; already-reserved ops still settle per saved conditions.
    await db.admin_audit.insert_one({"action": "promo_delete", "jti": admin["jti"], "promo_id": promo_id, "created_at": now_utc()})
    return {"ok": True}


@api_router.post("/admin/login")
async def admin_login(payload: AdminLoginIn, request: Request):
    ip = client_ip(request)
    await check_admin_lock(ip)
    words = [p.strip().lower() for p in payload.phrases]
    if any(not w or len(w) > 64 or " " in w for w in words):
        await record_admin_fail(ip)
        raise HTTPException(status_code=403, detail="Неверная сид-фраза")
    phrase = " ".join(words).encode()
    stored_hash = ADMIN_SEED_HASH
    if stored_hash.startswith(b"sha256$"):
        phrase = hashlib.sha256(phrase).hexdigest().encode()
        stored_hash = stored_hash[len(b"sha256$"):]
    ok = await asyncio.to_thread(bcrypt.checkpw, phrase, stored_hash)
    await db.admin_audit.insert_one({"id": str(uuid.uuid4()), "event": "login_ok" if ok else "login_fail", "ip": ip, "ua": ua_hash(request), "created_at": now_utc()})
    if not ok:
        await record_admin_fail(ip)
        raise HTTPException(status_code=403, detail="Неверная сид-фраза")
    await db.login_attempts.delete_one({"identifier": f"ip:{ip}"})
    # Не гасим всех: держим до MAX_ADMIN_SESSIONS живых сессий, старейшие сверх лимита — отзываем.
    now = now_utc()
    alive = await db.admin_sessions.find(
        {"revoked": False, "expires_at": {"$gt": now}}, {"_id": 0, "jti": 1},
    ).sort("created_at", -1).to_list(MAX_ADMIN_SESSIONS + 10)
    for old in alive[MAX_ADMIN_SESSIONS - 1:]:
        await db.admin_sessions.update_one({"jti": old["jti"]}, {"$set": {"revoked": True}})
    jti = secrets.token_urlsafe(24)
    expires = now_utc() + timedelta(hours=ADMIN_TOKEN_HOURS)
    await db.admin_sessions.insert_one({"jti": jti, "ip": ip, "ua_hash": ua_hash(request), "created_at": now_utc(), "expires_at": expires, "revoked": False})
    return {"token": make_token("admin", role="admin", hours=ADMIN_TOKEN_HOURS, extra={"type": "admin", "jti": jti, "seed_version": hashlib.sha256(ADMIN_SEED_HASH).hexdigest()}), "expires_at": expires}


@api_router.post("/admin/logout")
async def admin_logout(request: Request):
    sess = await require_admin(request)
    await db.admin_sessions.update_one({"jti": sess["jti"]}, {"$set": {"revoked": True}})
    return {"ok": True}


@api_router.get("/admin/session")
async def admin_session(request: Request):
    sess = await require_admin(request)
    return {"ok": True, "expires_at": sess["expires_at"]}


@api_router.get("/admin/deposits")
async def admin_deposits(request: Request, status: str = "pending"):
    await require_admin(request)
    if status not in ("pending", "confirmed", "rejected", "cancelled", "xrocket", "cryptobot"):
        raise HTTPException(status_code=400, detail="Неверный статус")
    order = 1 if status == "pending" else -1
    query = {"status": {"$in": ["pending", "processing"]}, "payment_method": {"$nin": ["xrocket", "cryptobot"]}} if status == "pending" else {"status": status}
    if status in ("xrocket", "cryptobot"):
        query = {"payment_method": status}
    docs = await db.deposits.find(query, {"_id": 0}).sort("created_at", order).to_list(200)
    return docs


@api_router.post("/admin/deposits/{deposit_id}/confirm")
async def admin_confirm_deposit(deposit_id: str, payload: AdminConfirmIn, request: Request):
    await require_admin(request)
    if payload.rap < MIN_DEPOSIT_RAP:
        raise HTTPException(status_code=400, detail=f"Скины дешевле {MIN_DEPOSIT_RAP} RAP не зачисляются — отклоните заявку")
    await require_not_staff_request(await db.deposits.find_one({"id": deposit_id}, {"_id": 0, "staff_flow": 1}))
    result = await confirm_deposit(db, deposit_id, payload.rap, payload.note)
    if not result.get("already_confirmed"):
        dep = await db.deposits.find_one({"id": deposit_id}, {"_id": 0, "chat_id": 1})
        await chat.notify_deposit(db, dep, ("deposit_confirmed", {"credited": float(result.get("credited") or 0)}))
    return result


@api_router.post("/admin/deposits/{deposit_id}/preview")
async def admin_deposit_preview(deposit_id: str, payload: AdminConfirmIn, request: Request):
    await require_admin(request)
    dep = await db.deposits.find_one({"id": deposit_id}, {"_id": 0})
    if not dep:
        raise HTTPException(404, "Заявка не найдена")
    if payload.rap < MIN_DEPOSIT_RAP:
        raise HTTPException(400, f"Минимальная сумма — {MIN_DEPOSIT_RAP} RAP")
    if dep["status"] == "processing":
        return {k: dep[k] for k in ("rap", "credited", "issued_skins", "skins_total", "balance_credited")}
    return await plan_deposit(db, dep, payload.rap)


@api_router.post("/admin/deposits/{deposit_id}/reject")
async def admin_reject_deposit(deposit_id: str, payload: AdminRejectIn, request: Request):
    await require_admin(request)
    res = await db.deposits.update_one(
        {"id": deposit_id, "status": "pending", "staff_flow": {"$ne": True}},
        {"$set": {"status": "rejected", "rejection_reason": payload.reason, "resolved_at": now_utc()}},
    )
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Заявка не найдена или уже обработана")
    dep = await db.deposits.find_one({"id": deposit_id}, {"_id": 0, "chat_id": 1})
    await notify_deposit_rejected(dep, payload.reason)
    return {"ok": True}


async def require_not_staff_request(dep: Optional[dict]) -> None:
    if dep and dep.get("staff_flow"):
        raise HTTPException(409, "Заявка сотрудника: решение принимается только по проверенному отчёту (Админка → Сотрудники или Telegram)")


async def notify_deposit_rejected(dep: Optional[dict], reason: str) -> None:
    found = await db.chats.find_one({"id": (dep or {}).get("chat_id")}, {"_id": 0, "lang": 1}) if (dep or {}).get("chat_id") else None
    text = REJECTION_REASONS_EN.get(reason, reason) if chat.lang_of(found) == "en" else rejection_reason_text(reason)
    await chat.notify_deposit(db, dep, ("deposit_rejected", {"reason": text}))


@api_router.get("/admin/withdrawals")
async def admin_withdrawals(request: Request, status: str = "pending"):
    await require_admin(request)
    if status not in ("pending", "done", "cancelled"):
        raise HTTPException(status_code=400, detail="Неверный статус")
    query = {"status": {"$in": ["pending", "cancelling", "paying"]}} if status == "pending" else {"status": status}
    docs = await db.withdrawals.find(query, {"_id": 0}).sort("created_at", 1 if status == "pending" else -1).to_list(200)
    users = {u["session_id"]: u for u in await db.users.find({"session_id": {"$in": list({d["session_id"] for d in docs})}}, {"_id": 0, "session_id": 1, "nickname": 1, "roblox_nick": 1, "roblox_display_name": 1, "roblox_link": 1, "discord_id": 1}).to_list(500)}
    for d in docs:
        d["user"] = users.get(d["session_id"])
        d["recipient_changed"] = recipient_changed(d)
    return docs


def recipient_changed(withdrawal: dict) -> bool:
    snap, cur = withdrawal.get("recipient"), withdrawal.get("user") or {}
    return bool(snap) and any((snap.get(k) or "") != (cur.get(k) or "") for k in ("roblox_nick", "roblox_link"))


async def _withdrawal_done(withdrawal_id: str, resume: bool = False) -> Optional[dict]:
    claimed = await db.withdrawals.update_one(
        {"id": withdrawal_id, "status": "pending"}, {"$set": {"status": "paying"}},
    )
    if not claimed.matched_count and not resume:
        # Only one request may attempt the debit. A duplicate may finish an
        # interrupted operation once the bank receipt proves it already paid.
        paid = await db.bank_state.find_one(
            {"id": "main", "withdrawal_receipts.id": f"withdrawal:{withdrawal_id}"}, {"_id": 1},
        )
        if not paid:
            return None
    w = await db.withdrawals.find_one({"id": withdrawal_id, "status": "paying"}, {"_id": 0})
    if not w:
        return None
    price = float((w.get("item") or {}).get("price") or 0)
    try:
        w["bank"] = await bank_add("withdrawal", -price, note=f"Выдан {(w.get('item') or {}).get('name')}", ref_id=withdrawal_id, session_id=w.get("session_id"))
    except HTTPException:
        await db.withdrawals.update_one({"id": withdrawal_id, "status": "paying"}, {"$set": {"status": "pending"}})
        raise
    resolved_at = now_utc()
    await resolve_history(db, w, "withdrawn", resolved_at=resolved_at)
    await db.withdrawals.update_one({"id": withdrawal_id, "status": "paying"}, {"$set": {"status": "done", "resolved_at": resolved_at}})
    return w


@api_router.post("/admin/withdrawals/{withdrawal_id}/done")
async def admin_withdrawal_done(withdrawal_id: str, request: Request):
    await require_admin(request)
    w = await _withdrawal_done(withdrawal_id)
    if not w:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return {"ok": True, "bank": w["bank"]}


@api_router.post("/admin/withdrawals/{withdrawal_id}/cancel")
async def admin_withdrawal_cancel(withdrawal_id: str, payload: AdminRejectIn, request: Request):
    await require_admin(request)
    w = await db.withdrawals.find_one({"id": withdrawal_id}, {"_id": 0, "session_id": 1, "item": 1})
    result = await cancel_withdrawal(db, withdrawal_id, payload.reason)
    if w:
        await chat.notify_owner(db, w["session_id"], ("withdrawal_cancelled", {"name": (w.get("item") or {}).get("name"), "reason": payload.reason}))
    return result


@api_router.get("/admin/bank")
async def admin_bank(request: Request):
    await require_admin(request)
    funds = await bank_funds(db)
    li = await liabilities()
    st = await rtp_stats()
    deposits_total = await _sum(db.bank_ledger, {"kind": "deposit"}, "$amount")
    withdrawals_total = -await _sum(db.bank_ledger, {"kind": "withdrawal"}, "$amount") + 0.0
    adjustments_total = await _sum(db.bank_ledger, {"kind": "adjust"}, "$amount")
    forced = await db.upgrades.count_documents({"forced_loss": True})
    forced_by = {d["_id"]: d["n"] for d in await db.upgrades.aggregate([{"$match": {"forced_loss": True}}, {"$group": {"_id": "$forced_reason", "n": {"$sum": 1}}}]).to_list(20)}
    wins = await db.upgrades.count_documents({"win": True})
    total = await db.upgrades.count_documents({})
    ledger = await db.bank_ledger.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    since_24h = now_utc() - timedelta(hours=24)
    wagered_24h = await _sum(db.upgrades, {"created_at": {"$gte": since_24h}}, {"$add": [{"$ifNull": ["$bet_amount", 0]}, {"$ifNull": ["$items_total", 0]}]})
    paid_24h = await _sum(db.upgrades, {"created_at": {"$gte": since_24h}, "win": True}, "$target_item.price")
    rtp_24h = {"wagered": wagered_24h, "paid": paid_24h, "rtp": (paid_24h / wagered_24h) if wagered_24h > 0 else 0.0}
    forced_rows = await db.upgrades.aggregate([
        {"$match": {"forced_loss": True}},
        {"$group": {"_id": "$session_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": 1}},
        {"$limit": 5},
    ]).to_list(5)
    forced_sids = [r["_id"] for r in forced_rows]
    forced_users = (
        {u["session_id"]: u for u in await db.users.find({"session_id": {"$in": forced_sids}}, {"_id": 0, "session_id": 1, "nickname": 1}).to_list(10)}
        if forced_sids else {}
    )
    forced_top = [
        {"session_id": r["_id"], "nickname": (forced_users.get(r["_id"], {}) or {}).get("nickname") or "?", "count": r["count"]}
        for r in forced_rows
    ]
    gifts = await promos.gift_stats(db)
    return {
        **funds,
        "pool": await payout_pool(),
        "settings": await bank_settings(),
        "liabilities": li,
        "net": funds["available_bank"] - li["total"],
        "deposits_total": deposits_total,
        "withdrawals_total": withdrawals_total,
        "adjustments_total": adjustments_total,
        "gifts_total": gifts["total"],
        "gifts_count": gifts["count"],
        "rtp": st,
        "rtp_24h": rtp_24h,
        "forced_top": forced_top,
        "games": {"total": total, "wins": wins, "forced_losses": forced, "forced_by": forced_by},
        "ledger": ledger,
    }


@api_router.put("/admin/bank/settings")
async def admin_bank_settings(payload: BankSettingsIn, request: Request):
    await require_admin(request)
    require_pin(payload.pin)
    changes = {k: v for k, v in payload.model_dump(exclude={"pin"}).items() if v is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="Нет изменений")
    await db.bank_settings.update_one({"id": "main"}, {"$set": {**changes, "updated_at": now_utc()}}, upsert=True)
    note = ", ".join(f"RTP → {round(v * 100)}% (комиссия {round((1 - v) * 100)}%)" for k, v in changes.items())
    await db.bank_ledger.insert_one({"id": str(uuid.uuid4()), "kind": "settings", "amount": 0.0, "bank_after": await bank_balance(), "note": note, "created_at": now_utc()})
    return await bank_settings()


@api_router.get("/admin/players")
async def admin_players(request: Request):
    await require_admin(request)
    pipeline = [
        {"$group": {
            "_id": "$session_id",
            "games": {"$sum": 1},
            "wagered": {"$sum": {"$add": [{"$ifNull": ["$bet_amount", 0]}, {"$ifNull": ["$items_total", 0]}]}},
            "paid": {"$sum": {"$cond": ["$win", {"$ifNull": ["$target_item.price", 0]}, 0]}},
            "wins": {"$sum": {"$cond": ["$win", 1, 0]}},
            "forced": {"$sum": {"$cond": [{"$eq": ["$forced_loss", True]}, 1, 0]}},
            "last_game": {"$max": "$created_at"},
        }},
        {"$sort": {"wagered": -1}},
        {"$limit": 200},
    ]
    rows = await db.upgrades.aggregate(pipeline).to_list(200)
    # Accounts remain visible with zero statistics after clearing game history.
    missing = await db.users.find({"session_id": {"$nin": [r["_id"] for r in rows]}}, {"session_id": 1}).sort("created_at", -1).to_list(200 - len(rows)) if len(rows) < 200 else []
    rows.extend({"_id": u["session_id"], "games": 0, "wagered": 0, "paid": 0, "wins": 0, "forced": 0, "last_game": None} for u in missing)
    sids = [r["_id"] for r in rows]
    users = {u["session_id"]: u for u in await db.users.find({"session_id": {"$in": sids}}, {"_id": 0, "session_id": 1, "nickname": 1, "balance": 1, "skins.price": 1, "roblox_nick": 1}).to_list(500)}
    deps = {d["_id"]: d for d in await db.deposits.aggregate([{"$match": {"session_id": {"$in": sids}, "status": "confirmed"}}, {"$group": {"_id": "$session_id", "credited": {"$sum": {"$ifNull": ["$credited", 0]}}, "rap": {"$sum": {"$ifNull": ["$rap", 0]}}}}]).to_list(500)}
    withdrawn = {w["_id"]: w["v"] for w in await db.withdrawals.aggregate([{"$match": {"session_id": {"$in": sids}, "status": "done"}}, {"$group": {"_id": "$session_id", "v": {"$sum": {"$ifNull": ["$item.price", 0]}}}}]).to_list(500)}
    out = []
    for r in rows:
        u = users.get(r["_id"], {})
        inv = sum(float(s.get("price") or 0) for s in u.get("skins", []))
        out.append({
            "session_id": r["_id"], "nickname": u.get("nickname", "?"), "roblox_nick": u.get("roblox_nick"),
            "deposits": float(deps.get(r["_id"], {}).get("credited", 0)), "deposits_rap": float(deps.get(r["_id"], {}).get("rap", 0)),
            "games": r["games"], "wins": r["wins"], "forced": r["forced"], "wagered": float(r["wagered"]), "paid": float(r["paid"]),
            "rtp": (float(r["paid"]) / float(r["wagered"])) if r["wagered"] else 0.0,
            "balance": float(u.get("balance") or 0), "inventory": inv, "withdrawn": float(withdrawn.get(r["_id"], 0)),
            "net": float(u.get("balance") or 0) + inv + float(withdrawn.get(r["_id"], 0)) - float(deps.get(r["_id"], {}).get("credited", 0)),
            "last_game": r["last_game"],
        })
    return out


@api_router.post("/admin/bank/adjust")
async def admin_bank_adjust(payload: BankAdjustIn, request: Request):
    await require_admin(request)
    require_pin(payload.pin)
    if abs(payload.amount) < 0.01:
        raise HTTPException(status_code=400, detail="Сумма должна быть не нулевой")
    amount = round(payload.amount, 2)
    if amount < 0:
        state = await db.bank_state.find_one_and_update(
            {"id": "main", "$expr": {"$gte": [spendable_bank_expr(), -amount]}}, {"$inc": {"bank": amount}},
            return_document=ReturnDocument.AFTER,
        )
        if not state:
            raise HTTPException(status_code=400, detail="Недостаточно средств в банке без использования комиссии 20%")
        bank = float(state["bank"])
        await db.bank_ledger.insert_one({"id": str(uuid.uuid4()), "kind": "adjust", "amount": amount, "bank_after": bank, "note": payload.note.strip(), "created_at": now_utc()})
    else:
        bank = await bank_add("adjust", amount, note=payload.note.strip())
    return {"ok": True, "bank": bank}


@api_router.post("/admin/bank/pool")
async def admin_bank_pool(payload: PoolTopUpIn, request: Request):
    await require_admin(request)
    require_pin(payload.pin)
    amount = round(payload.amount, 2)
    if amount == 0:
        raise HTTPException(400, "Сумма должна быть не нулевой")
    await ensure_pool()
    query = {"id": "main"}
    if amount < 0:
        query["pool"] = {"$gte": -amount}
    state = await db.bank_state.find_one_and_update(
        query, {"$inc": {"pool": amount}},
        upsert=amount > 0, return_document=ReturnDocument.AFTER,
    )
    if state is None:
        raise HTTPException(400, "В свободном пуле недостаточно средств для уменьшения")
    pool_after = float(state["pool"])
    await db.bank_ledger.insert_one({"id": str(uuid.uuid4()), "kind": "pool", "amount": amount, "bank_after": await bank_balance(), "note": payload.note.strip(), "created_at": now_utc()})
    return {"ok": True, "pool": pool_after}


@api_router.post("/admin/bank/reset")
async def admin_bank_reset(payload: BankResetIn, request: Request):
    """Reset the whole economy; preserve accounts, game settings and public upgrade count."""
    admin = await require_admin(request)
    require_pin(payload.pin)
    result = await economy_reset.reset(db, str(payload.request_id), admin["jti"])
    _upgrade_seen.clear()
    _promo_seen.clear()
    return result


BEST_DROP_WINDOW = timedelta(hours=24)


LIVE_DROPS_TTL = 2.0
_live_drops_cache: dict = {}


@api_router.get("/live-drops")
async def live_drops(limit: int = 30, include_best: bool = False):
    # Same public feed for every client: build it at most once per TTL per variant.
    limit = max(1, min(limit, 100))
    key = (limit, include_best)
    cached = _live_drops_cache.get(key)
    if cached and time.monotonic() - cached[0] < LIVE_DROPS_TTL:
        return cached[1]
    result = await _build_live_drops(limit, include_best)
    _live_drops_cache[key] = (time.monotonic(), result)
    return result


async def _build_live_drops(limit: int, include_best: bool):
    now = now_utc()
    docs = await db.drops.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    best = []
    if include_best:
        best = await db.drops.find({"created_at": {"$gte": now - BEST_DROP_WINDOW, "$lte": now}}, {"_id": 0}).sort([("item_price", -1), ("created_at", -1), ("id", 1)]).to_list(1)
    sids = list({d["session_id"] for d in docs + best})
    users = {u["session_id"]: u async for u in db.users.find({"session_id": {"$in": sids}}, {"_id": 0, "session_id": 1, "nickname": 1, "avatar": 1, "discord_id": 1, "gold_nick": 1})}
    out = []
    for d in docs + best:
        u = users.get(d["session_id"])
        if u:
            d.update({"nickname": u.get("nickname") or d.get("nickname"), "avatar": u.get("avatar"), "discord_id": u.get("discord_id"), "gold_nick": bool(u.get("gold_nick"))})
        out.append(Drop(**d).model_dump(exclude={"session_id"}))
    if include_best:
        return {"drops": out[:len(docs)], "best_drop": out[-1] if best else None,
                "best_drop_expires_at": as_utc(best[0]["created_at"]) + BEST_DROP_WINDOW if best else None, "server_time": now}
    return out


# ---------- Luck: админка (игрокам ничего не видно) ----------
@api_router.get("/admin/rains")
async def admin_rains(request: Request, limit: int = 20):
    await require_admin(request)
    limit = max(1, min(limit, 100))
    docs = await db.rains.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"settings": await rain_settings(), "pool": await payout_pool(), "rains": docs}


@api_router.get("/admin/rain/settings")
async def admin_rain_settings_get(request: Request):
    await require_admin(request)
    return await rain_settings()


@api_router.put("/admin/rain/settings")
async def admin_rain_settings_put(payload: RainSettingsIn, request: Request):
    await require_admin(request)
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="Нет изменений")
    if "budget_min_pct" in changes or "budget_max_pct" in changes:
        cfg = await rain_settings()
        lo = float(changes.get("budget_min_pct", cfg["budget_min_pct"]))
        hi = float(changes.get("budget_max_pct", cfg["budget_max_pct"]))
        if lo > hi:
            raise HTTPException(status_code=400, detail="budget_min_pct не может быть больше budget_max_pct")
    await db.rain_settings.update_one({"id": "main"}, {"$set": {**changes, "updated_at": now_utc()}}, upsert=True)
    await db.bank_ledger.insert_one({
        "id": str(uuid.uuid4()), "kind": "settings", "amount": 0.0,
        "bank_after": await bank_balance(),
        "note": f"Rain: {', '.join(f'{k} → {v}' for k, v in changes.items())}",
        "created_at": now_utc(),
    })
    return await rain_settings()


@api_router.post("/admin/rain/close")
async def admin_rain_close(request: Request):
    """Принудительно закрыть активную раздачу: невостребованное вернуть в pool."""
    await require_admin(request)
    await resume_rain_returns(db)
    doc = await close_rain(db)
    if not doc:
        return {"ok": False, "reason": "no_active_rain"}
    return {"ok": True, "rain_id": doc["id"], "returned": doc["returned_amount"]}


@api_router.get("/users/{discord_id}")
async def public_profile(discord_id: str):
    user = await db.users.find_one({"discord_id": discord_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Игрок не найден")
    sid = user["session_id"]
    drops = await db.drops.find({"session_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(24)
    best = await db.drops.find({"session_id": sid}, {"_id": 0}).sort("item_price", -1).to_list(1)
    skins = user.get("skins", [])
    return {
        "nickname": user.get("nickname", "Player"),
        "avatar": user.get("avatar"),
        "discord_id": discord_id,
        "gold_nick": bool(user.get("gold_nick")),
        "created_at": user.get("created_at"),
        "stats": {
            **(await player_stats(sid)),
            "inventory_count": len(skins),
            "inventory_value": sum(float(s.get("price") or 0) for s in skins),
        },
        "best_drop": Drop(**best[0]).model_dump(exclude={"session_id"}) if best else None,
        "drops": [Drop(**d).model_dump(exclude={"session_id"}) for d in drops],
    }


@api_router.get("/shop")
async def shop(
    sort: str = "price_desc",
    min_price: Optional[float] = Query(default=None, ge=0, allow_inf_nan=False),
    max_price: Optional[float] = Query(default=None, ge=0, allow_inf_nan=False),
    q: Optional[str] = Query(default=None, max_length=100),
    rarity: Optional[str] = None,
    limit: int = 60,
    page: int = Query(default=1, ge=1),
):
    query: dict = {}
    if min_price is not None or max_price is not None:
        price_q: dict = {}
        if min_price is not None:
            price_q["$gte"] = min_price
        if max_price is not None:
            price_q["$lte"] = max_price
        query["price"] = price_q
    if q:
        query["$or"] = [{field: {"$regex": re.escape(q.strip()), "$options": "i"}} for field in ("name", "type")]
    if rarity:
        query["rarity"] = rarity
    direction = 1 if sort == "price_asc" else -1
    page_size = max(1, min(limit, 200))
    total = await db.shop_items.count_documents(query)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    docs = await db.shop_items.find(query, {"_id": 0}).sort([("price", direction), ("id", 1)]).skip((page - 1) * page_size).to_list(page_size)
    return {"items": docs, "total": total, "page": page, "pages": pages}


@api_router.post("/shop/buy")
async def buy_skins(payload: PurchaseIn, request: Request):
    user = await require_user(request)
    result = await purchase_skins(db, user, payload.request_id, [line.model_dump() for line in payload.items], payload.expected_total)
    result["user"] = to_user_out(result["user"]).model_dump()
    return result


@api_router.post("/upgrade", response_model=UpgradeOut)
async def upgrade(payload: UpgradeIn, request: Request):
    if (await token_user(request, {"_id": 0, "session_id": 1}) or {}).get("session_id") != payload.session_id:
        raise HTTPException(status_code=401, detail="Войдите через Discord, чтобы играть")
    if not upgrade_rate_ok(payload.session_id):
        raise HTTPException(status_code=429, detail="Слишком быстро: подождите пару секунд")
    if payload.target_item is None or not payload.target_item.get("id"):
        raise HTTPException(status_code=400, detail="Выберите скин для апгрейда")
    user, shop_item, settings = await asyncio.gather(
        get_or_create_user(payload.session_id),
        db.shop_items.find_one({"id": str(payload.target_item["id"])}, {"_id": 0}),
        bank_settings(),
    )
    balance = float(user.get("balance", 0))

    if payload.bet_amount <= 0 and not payload.bet_items:
        raise HTTPException(status_code=400, detail="Выберите скины или баланс для апгрейда")
    if not shop_item:
        raise HTTPException(status_code=400, detail="Скин для апгрейда не найден")
    if payload.bet_amount > balance + 1e-9:
        raise HTTPException(status_code=400, detail="Недостаточно баланса")

    owned = {sk.get("uid"): sk for sk in user.get("skins", []) if sk.get("uid")}
    bet_uids = [str(it.get("uid")) for it in payload.bet_items]
    if len(set(bet_uids)) != len(bet_uids) or any(u not in owned for u in bet_uids):
        raise HTTPException(status_code=400, detail="Выбранных скинов нет в вашем инвентаре")
    bet_skins = [owned[u] for u in bet_uids]
    items_total = sum(float(sk.get("price") or 0) for sk in bet_skins)
    total_bet = payload.bet_amount + items_total
    if total_bet <= 0:
        raise HTTPException(status_code=400, detail="Выберите скины или баланс для апгрейда")

    target_price = float(shop_item.get("price") or 0)
    if target_price <= 0:
        raise HTTPException(status_code=400, detail="Скин для апгрейда недоступен")
    rtp = float(settings["rtp_target"])
    max_ratio = max_bet_ratio(rtp)
    max_total_bet = int(Decimal(str(target_price)) * Decimal(str(max_ratio)) * 100) / 100
    if total_bet > max_total_bet + 1e-6:
        raise HTTPException(status_code=400, detail=f"Ставка не может превышать {round(max_ratio * 100)}% стоимости скина")
    # chance is always derived server-side: bet/price minus the house edge; the client value is ignored
    chance = win_chance(total_bet, target_price, rtp)
    if chance < MIN_CHANCE - 1e-9:
        raise HTTPException(status_code=400, detail="Минимальный шанс — 1%: увеличьте ставку")

    # atomic debit: balance and skins are checked and taken in one update (no double spend)
    debit_filter: dict = {"session_id": payload.session_id, "balance": {"$gte": payload.bet_amount - 1e-9}}
    if bet_uids:
        debit_filter["skins"] = {"$all": [{"$elemMatch": {"uid": u}} for u in bet_uids]}
    user_update: dict = {"$inc": {"balance": -payload.bet_amount}}
    if bet_uids:
        user_update["$pull"] = {"skins": {"uid": {"$in": bet_uids}}}
    fresh = await db.users.find_one_and_update(debit_filter, user_update, projection={"_id": 0, "balance": 1}, return_document=ReturnDocument.AFTER)
    if not fresh:
        raise HTTPException(status_code=400, detail="Недостаточно баланса или скин уже использован")
    new_balance = float(fresh.get("balance", 0))

    # payout pool: every accepted bet refills the pool by bet * rtp; a win may only spend what the pool holds.
    # Together with the atomic spend below this guarantees total paid <= rtp * total wagered (hard ceiling).
    await ensure_pool()
    await db.bank_state.update_one({"id": "main"}, {"$inc": {"pool": total_bet * rtp}}, upsert=True)

    # the roll itself is honest and independent of the bank; only the payout decision is serialized
    # `chance` — реальный шанс победы (с RTP), `shown` — цифра для UI (без RTP).
    shown = shown_chance(total_bet, target_price)
    # Luck (секретно): если полоса удачи активна и приз влезает в 60% её остатка —
    # судим спин по показываемому шансу (без RTP): игрок видит 50% и реально имеет 50%.
    luck_rain = None
    luck = False
    try:
        await rain_maybe_close()
        luck_rain = await rain_maybe_start()
        if luck_rain is None:
            luck_rain = await rain_active()
        luck = await luck_boosted(luck_rain, target_price)
    except Exception:
        logger.exception("luck check error (spin continues normal)")
        luck_rain, luck = None, False
    roll = _rng.random()
    win = abs(roll * 360 - 180) < (shown if luck else chance) * 180
    forced_loss = False
    forced_reason = None
    protection: dict = {"rtp": rtp}
    target = None
    upgrade_id = str(uuid.uuid4())
    luck_used = False
    if win:
        async with bank_lock() as lock:
            # solvency: the bank must cover every player liability plus this prize — otherwise the spin is a loss
            headroom, solvency = await solvency_headroom()
            bank_can_pay = headroom + 1e-9 >= target_price
            protection.update({**solvency, "bank_can_pay": bank_can_pay})
            if not lock.leased or not bank_can_pay:
                win, forced_loss, forced_reason = False, True, ("lock" if not lock.leased else "bank")
                roll = losing_roll(shown)
            else:
                if luck and luck_rain is not None:
                    # Приз оплачивается из резерва полосы (уже выведен из pool при старте).
                    try:
                        luck_used = await luck_spend(luck_rain["id"], target_price, payload.session_id, upgrade_id)
                    except Exception:
                        logger.exception("luck spend error (fallback to pool)")
                        luck_used = False
                if luck_used:
                    protection["luck"] = True
                    target = {**shop_item, "uid": str(uuid.uuid4())}
                    await db.users.update_one({"session_id": payload.session_id}, {"$push": {"skins": target}})
                else:
                    # обычный путь: приз платится из общего пула при наличии бюджета
                    paid_state = await db.bank_state.find_one_and_update(
                        {"id": "main", "pool": {"$gte": target_price}},
                        {"$inc": {"pool": -target_price}},
                        return_document=ReturnDocument.AFTER,
                    )
                    if not paid_state:
                        win, forced_loss, forced_reason = False, True, "pool"
                        roll = losing_roll(shown)
                    else:
                        protection["pool"] = float(paid_state["pool"])
                        target = {**shop_item, "uid": str(uuid.uuid4())}
                        await db.users.update_one({"session_id": payload.session_id}, {"$push": {"skins": target}})
    # Угол: победа — всегда внутри РЕАЛЬНОЙ зоны (тесты и честность стрелки),
    # проигрыш — всегда снаружи ПОКАЗЫВАЕМОЙ. Подкрученная победа (ролл между
    # реальной и показываемой зонами) подтягивается к краю реальной зоны —
    # визуально всё равно внутри зелёного, игрок ничего не замечает.
    angle = landing_angle(roll, chance, True) if win else landing_angle(roll, shown, False)

    # Кешбэк при проигрыше: 1 RAP. Списывается из пула атомарно (pool >= 1),
    # поэтому суммарные выплаты никогда не превышают RTP × ставки. Пуст пул —
    # тихо нет кешбэка, прокрут от этого не ломается.
    cashback = 0.0
    if not win and total_bet >= CASHBACK_MIN_BET - 1e-9:
        try:
            cb_state = await db.bank_state.find_one_and_update(
                {"id": "main", "pool": {"$gte": CASHBACK_AMOUNT}},
                {"$inc": {"pool": -CASHBACK_AMOUNT}},
                return_document=ReturnDocument.AFTER,
            )
            if cb_state is not None:
                cashback = CASHBACK_AMOUNT
                new_balance = round(new_balance + cashback, 2)
                await db.users.update_one({"session_id": payload.session_id}, {"$inc": {"balance": cashback}})
        except Exception:
            logger.exception("cashback error (spin continues without cashback)")
            cashback = 0.0

    writes = [db.upgrades.insert_one({
        "id": upgrade_id,
        "session_id": payload.session_id,
        "bet_amount": payload.bet_amount,
        "bet_items": bet_skins,
        "items_total": items_total,
        "target_item": shop_item,
        "chance": chance,
        "display_chance": shown,
        "roll": roll,
        "win": win,
        "forced_loss": forced_loss,
        "forced_reason": forced_reason if forced_loss else None,
        "protection": protection,
        "luck": bool(luck_used),
        "cashback": cashback,
        "created_at": now_utc(),
        **({"referral_pending": True} if user.get("referred_by") else {}),
    })]
    if win:
        drop = Drop(
            session_id=payload.session_id,
            nickname=user.get("nickname", "Player"),
            item_name=str(target.get("name", "Item")),
            item_type=str(target.get("type", "")),
            item_price=float(target.get("price", 0)),
            item_image=target.get("image"),
            item_rarity=target.get("rarity"),
            chance=chance,
            display_chance=shown,
            avatar=user.get("avatar"),
            discord_id=user.get("discord_id"),
            gold_nick=bool(user.get("gold_nick")),
        )
        writes.append(db.drops.insert_one(drop.model_dump()))
        writes.append(db.item_history.insert_one(
            {"id": str(uuid.uuid4()), "session_id": payload.session_id, "kind": "won", "item": target, "price": float(shop_item.get("price") or 0), "created_at": now_utc()}
        ))
    await asyncio.gather(*writes)
    if user.get("referred_by"):
        try:
            await referrals.reward_wager(db, {"id": upgrade_id, "session_id": payload.session_id})
        except Exception:
            logger.exception("Referral qualification deferred for upgrade %s", upgrade_id)
    upgrades_total = await count_upgrades()

    return UpgradeOut(
        id=upgrade_id,
        win=win,
        roll=roll,
        chance=chance,
        display_chance=shown,
        angle=angle,
        balance=new_balance,
        upgrades_total=upgrades_total,
        cashback=cashback,
    )


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

STATIC_DIR = ROOT_DIR / "static"


def safe_static_file(root: Path, full_path: str) -> Optional[Path]:
    """File inside root only: '..' segments and symlinks pointing outside are rejected."""
    if not full_path:
        return None
    file = (root / full_path).resolve()
    return file if file.is_relative_to(root) and file.is_file() else None

@api_router.get("/health")
async def health():
    return {"ok": True}


app.include_router(api_router)
app.include_router(staff_routes.build_router(db, require_admin, token_user, staff_bot, APP_URL, notify_deposit_rejected))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR / "static"), name="assets")

    # Hashed bundles and mirrored item images never change under the same URL: let browsers cache them for a year.
    LONG_CACHE_DIRS = ("items/", "payments/", "sounds/", "receivers/")
    LONG_CACHE = "public, max-age=31536000, immutable"
    STATIC_ROOT = STATIC_DIR.resolve()

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        file = safe_static_file(STATIC_ROOT, full_path)
        if file:
            headers = {"Cache-Control": LONG_CACHE} if full_path.startswith(LONG_CACHE_DIRS) else {"Cache-Control": "public, max-age=86400"}
            return FileResponse(file, headers=headers)
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.middleware("http")
    async def static_cache_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = LONG_CACHE
        return response

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# httpx logs full request URLs at INFO, and Telegram URLs contain the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)


@app.on_event("startup")
async def ensure_indexes():
    await economy_guard.ensure(db)
    await economy_reset.resume(db)
    async with economy_guard.operation(db):
        await _ensure_indexes()
    app.state.economy_guard_ready = True


async def _ensure_indexes():
    await ensure_promotions(db)
    await xp.ensure_indexes(db)
    await cb.ensure_indexes(db)
    await chat.ensure_indexes(db)
    await chat_attachments.ensure_indexes(db)
    await dp.ensure_indexes(db)
    await staff_core.ensure_indexes(db)
    await staff_evidence.ensure_indexes(db)
    await staff_shifts.ensure_indexes(db)
    await staff_telegram.ensure_indexes(db)
    await admin_commands.ensure_commands(db)
    await admin_coins.ensure_indexes(db)
    await referrals.ensure_indexes(db)
    await db.presence.create_index("session_id", unique=True)
    await ensure_presence_ttl()
    await db.drops.create_index("created_at")
    await db.drops.create_index([("created_at", -1), ("item_price", -1)])
    await db.users.create_index("session_id", unique=True)
    await db.users.create_index("roblox_nick_normalized", unique=True, partialFilterExpression={"roblox_nick_normalized": {"$type": "string"}})
    await db.user_locks.create_index("session_id", unique=True)
    await db.item_history.create_index([("session_id", 1), ("created_at", -1)])
    await db.deposits.create_index([("status", 1), ("created_at", 1)])
    for collection in (db.deposits, db.withdrawals):
        await collection.create_index([("session_id", 1), ("created_at", -1), ("id", -1)])
        await collection.create_index([("session_id", 1), ("resolved_at", -1), ("id", -1)])
    await db.withdrawals.create_index([("status", 1), ("created_at", 1)])
    await db.withdrawals.create_index("id", unique=True)
    await db.withdrawals.create_index([("status", 1), ("op_id", 1)])
    await db.deposits.create_index("admin_request_id", unique=True, partialFilterExpression={"admin_request_id": {"$type": "string"}})
    await db.bank_ledger.create_index("created_at")
    await db.bank_ledger.create_index("id", unique=True)
    await db.bank_state.create_index("id", unique=True)
    await reserve_historical_commissions(db)
    await resume_rain_returns(db)
    await db.item_history.create_index("id", unique=True)
    await db.upgrades.create_index([("win", 1), ("forced_loss", 1)])
    await db.upgrades.create_index([("session_id", 1), ("created_at", -1)])
    await db.drops.create_index([("session_id", 1), ("created_at", -1)])
    await db.drops.create_index([("session_id", 1), ("item_price", -1)])
    await db.users.create_index("discord_id")
    await db.withdrawals.create_index([("session_id", 1), ("status", 1)])
    await db.shop_items.create_index("id")
    await db.oauth_states.create_index("created_at", expireAfterSeconds=600)
    await db.admin_sessions.create_index("jti", unique=True)
    await db.admin_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("identifier", unique=True)
    await db.admin_audit.create_index("created_at")
    await db.bank_lock.update_one({"id": "main"}, {"$setOnInsert": {"locked_until": now_utc() - timedelta(seconds=1)}}, upsert=True)
    await db.rains.create_index("id", unique=True)
    # Только одна активная раздача: второй одновременный старт упрётся в этот
    # индекс, откатит свою бронь пула и подхватит чужую раздачу (без двойной траты).
    await db.rains.create_index("status", unique=True, partialFilterExpression={"status": "active"})
    await db.rains.create_index([("status", 1), ("closes_at", 1)])
    await db.rain_settings.create_index("id", unique=True)
    await sync_shop_catalog()
    # Crash recovery for instant RAP gifts: already-booked (reserved) ops settle per
    # SAVED amount even if the promo was deleted/expired; pending (never booked)
    # ops resume on the next user retry (atomic booking is idempotent).
    try:
        resumed = await promos.resume_incomplete_gifts(db)
        if resumed:
            logger.info("Resumed %s interrupted RAP gifts", resumed)
    except Exception:
        logger.exception("Could not resume interrupted RAP gifts")
    # Never delete user inventory or historical drops as a side effect of restarting.
    await admin_coins.resume_pending(db)
    for dep in await db.deposits.find({"status": "processing", "settlement_version": 1}, {"_id": 0}).to_list(None):
        try:
            await settle_deposit(db, dep)
        except Exception:
            logger.exception("Could not resume deposit %s; administrator may retry", dep["id"])
    for withdrawal in await db.withdrawals.find({"status": "paying"}, {"_id": 0}).to_list(None):
        try:
            await _withdrawal_done(withdrawal["id"], resume=True)
        except Exception:
            logger.exception("Could not resume withdrawal payment %s; administrator may retry", withdrawal["id"])
    try:
        await resume_withdrawal_ops()
    except Exception:
        logger.exception("Could not resume interrupted withdrawal requests; will retry on next start")
    await staff_core.resume(db)
    if staff_bot.enabled:
        app.state.staff_telegram = asyncio.create_task(staff_telegram.retry_loop(db, staff_bot))
    for withdrawal in await db.withdrawals.find({"status": "cancelling"}, {"_id": 0}).to_list(None):
        try:
            await finish_cancellation(db, withdrawal)
        except Exception:
            logger.exception("Could not resume withdrawal cancellation %s; administrator may retry", withdrawal["id"])
    app.state.referral_reconciliation = asyncio.create_task(referrals.reconcile_loop(db))
    if xrocket.enabled:
        app.state.xrocket_reconciliation = asyncio.create_task(xp.reconcile_loop(db, xrocket))
    if cryptobot.enabled:
        app.state.cryptobot_reconciliation = asyncio.create_task(cb.reconcile_loop(db, cryptobot))
    if tg_bot.enabled:
        app.state.telegram_retry = asyncio.create_task(dp.retry_loop(db, tg_bot))
        if os.environ.get("TELEGRAM_WEBHOOK_AUTO") == "true":
            try:
                await dp.setup_webhook(tg_bot, APP_URL)
            except Exception:
                logger.exception("Could not register the Telegram webhook; use /admin -> Telegram")


PRESENCE_TTL_SECONDS = 24 * 3600


async def ensure_presence_ttl():
    # Presence only matters for the last few minutes; old guest rows expire automatically.
    info = await db.presence.index_information()
    current = info.get("last_seen_1")
    if current and current.get("expireAfterSeconds") != PRESENCE_TTL_SECONDS:
        await db.presence.drop_index("last_seen_1")
    await db.presence.create_index("last_seen", expireAfterSeconds=PRESENCE_TTL_SECONDS)


async def sync_shop_catalog():
    # One bulk write, skipped entirely when the built-in catalog did not change since the last start.
    digest = hashlib.sha256(json.dumps(SHOP_ITEMS, sort_keys=True).encode()).hexdigest()
    ids = [item["id"] for item in SHOP_ITEMS]
    if await db.app_meta.find_one({"_id": "shop_catalog", "digest": digest}) and await db.shop_items.count_documents({"id": {"$in": ids}}) == len(ids):
        return
    await db.shop_items.bulk_write([UpdateOne({"id": item["id"]}, {"$set": item}, upsert=True) for item in SHOP_ITEMS], ordered=False)
    # Убранные из каталога позиции исчезают из магазина (инвентари игроков и историю не трогаем).
    await db.shop_items.delete_many({"id": {"$nin": ids}})
    await db.app_meta.update_one({"_id": "shop_catalog"}, {"$set": {"digest": digest}}, upsert=True)


@app.on_event("shutdown")
async def shutdown_db_client():
    for name in ("referral_reconciliation", "xrocket_reconciliation", "cryptobot_reconciliation", "telegram_retry", "staff_telegram"):
        task = getattr(app.state, name, None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    client.close()
