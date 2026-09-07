from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Query
from fastapi.responses import RedirectResponse
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
import asyncio
import os
import logging
import random
import re
import secrets
from collections import deque
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from urllib.parse import urlencode
import uuid
import hashlib
import hmac
from functools import wraps
from deposit_settlement import confirm_deposit, plan_deposit, settle_deposit
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
ADMIN_SEED_HASH = os.environ['ADMIN_SEED_HASH'].encode()
ADMIN_SEED_WORDS = 10
ADMIN_TOKEN_HOURS = 4
ADMIN_MAX_FAILS_IP = 5
ADMIN_MAX_FAILS_GLOBAL = 20
ADMIN_LOCK_MINUTES = 15
CORS_ORIGINS = [o.strip() for o in os.environ['CORS_ORIGINS'].split(',') if o.strip()]
DISCORD_REDIRECT_URI = f"{APP_URL}/api/auth/discord/callback"
DISCORD_API = "https://discord.com/api/v10"

app = FastAPI()
api_router = APIRouter(prefix="/api")


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

ONLINE_WINDOW_SECONDS = 45
MIN_CHANCE = 0.01
MAX_CHANCE = 0.75

RARITIES = [
    {"key": "stock", "label": "Stock", "color": "#b8bcc9"},
    {"key": "blue", "label": "Blue", "color": "#4b9dff"},
    {"key": "purple", "label": "Purple", "color": "#a35cff"},
    {"key": "pink", "label": "Pink", "color": "#ff4fd8"},
    {"key": "red", "label": "Red", "color": "#ff3b3b"},
    {"key": "gold", "label": "Gold", "color": "#ffc634"},
    {"key": "special", "label": "Special", "color": "#ffe27a"},
    {"key": "forbidden", "label": "Forbidden", "color": "#ff7a1a"},
]



IMG = "https://bloxstrike.net/items/bloxstrike-live"
SHOP_ITEMS = [
    {"id": "case-glove-case", "type": "Case", "name": "Glove Case", "price": 43.0, "rarity": "red", "image": f"{IMG}/123594181073716.png"},
    {"id": "case-chrysalis", "type": "Case", "name": "Chrysalis", "price": 44.0, "rarity": "red", "image": f"{IMG}/134467311250667.png"},
    {"id": "case-glove-case-2", "type": "Case", "name": "Glove Case 2", "price": 50.0, "rarity": "red", "image": f"{IMG}/75374128985311.png"},
    {"id": "case-1", "type": "Case", "name": "Case #1", "price": 88.0, "rarity": "red", "image": f"{IMG}/103053431273169.png"},
    {"id": "package-glock-midas", "type": "Package | Glock-18", "name": "Midas", "price": 396.0, "rarity": "red", "image": f"{IMG}/126726654780672.png"},
    {"id": "package-tec9-medal", "type": "Package | Tec-9", "name": "Medal.tv", "price": 832.0, "rarity": "red", "image": f"{IMG}/71231444746781.png"},
    {"id": "awp-bird-hunt", "type": "AWP", "name": "Bird Hunt", "price": 1125.0, "rarity": "red", "image": f"{IMG}/91355488643704.png"},
    {"id": "m4a1s-anodized-red", "type": "M4A1-S", "name": "Anodized Red", "price": 1580.0, "rarity": "red", "image": f"{IMG}/87908365282079.png"},
    {"id": "case-lionheart", "type": "Case", "name": "Lionheart", "price": 40.0, "rarity": "red", "image": f"{IMG}/73482740280871.png"},
    {"id": "case-finishline", "type": "Case", "name": "Finishline Case", "price": 39.0, "rarity": "red", "image": f"{IMG}/114958333422119.png"},
    {"id": "sports-gloves-imperial", "type": "Sports Gloves", "name": "Imperial", "price": 11299.0, "rarity": "gold", "image": f"{IMG}/75665163318076.png"},
    {"id": "hand-wraps-aztec", "type": "Hand Wraps", "name": "Aztec", "price": 4250.0, "rarity": "gold", "image": f"{IMG}/90350865435356.png"},
    {"id": "operator-gloves-reinforced", "type": "Operator Gloves", "name": "Reinforced", "price": 3600.0, "rarity": "gold", "image": f"{IMG}/123073579676420.png"},
    {"id": "sports-gloves-bumblebee", "type": "Sports Gloves", "name": "Bumblebee", "price": 3050.0, "rarity": "gold", "image": f"{IMG}/116732891350636.png"},
    {"id": "driver-gloves-gator", "type": "Driver Gloves", "name": "Gator", "price": 1699.0, "rarity": "gold", "image": f"{IMG}/100906379437261.png"},
    {"id": "karambit-safari", "type": "Karambit", "name": "Safari", "price": 3500.0, "rarity": "gold", "image": f"{IMG}/93690634411905.png"},
    {"id": "butterfly-safari", "type": "Butterfly", "name": "Safari", "price": 3000.0, "rarity": "gold", "image": f"{IMG}/135033903539257.png"},
    {"id": "skeleton-safari", "type": "Skeleton", "name": "Safari", "price": 2200.0, "rarity": "gold", "image": f"{IMG}/88859869862052.png"},
    {"id": "flip-rusted", "type": "Flip", "name": "Rusted", "price": 2000.0, "rarity": "gold", "image": f"{IMG}/127398374106324.png"},
    {"id": "gut-rusted", "type": "Gut", "name": "Rusted", "price": 1773.0, "rarity": "gold", "image": f"{IMG}/85270959203020.png"},
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


# ---------- Models ----------
class InputModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True)


class PresenceIn(InputModel):
    session_id: str = Field(min_length=1, max_length=64)


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
    roblox_link: Optional[str] = None
    gold_nick: bool = False


class RobloxIn(InputModel):
    roblox_nick: str = Field(min_length=3, max_length=20)
    roblox_link: str = Field(min_length=10, max_length=400)


class PromoIn(InputModel):
    code: str = Field(min_length=1, max_length=32)


class DepositIn(InputModel):
    description: str = Field(min_length=3, max_length=300)
    expected_rap: float = Field(ge=20, le=1_000_000)
    receiver_id: str = Field(min_length=1, max_length=32)


class AdminLoginIn(BaseModel):
    phrases: List[str] = Field(min_length=ADMIN_SEED_WORDS, max_length=ADMIN_SEED_WORDS)


class AdminConfirmIn(InputModel):
    rap: float = Field(gt=0, le=1_000_000)
    note: Optional[str] = Field(default=None, max_length=200)


class BankSettingsIn(InputModel):
    rtp_target: Optional[float] = Field(default=None, ge=0.75, le=1.0)


class BankAdjustIn(InputModel):
    amount: float = Field(ge=-1_000_000, le=1_000_000)
    note: str = Field(min_length=2, max_length=200)


class UidsIn(InputModel):
    uids: List[str] = Field(min_length=1, max_length=200)


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
    angle: float
    balance: float
    upgrades_total: int


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
    return user


async def count_online() -> int:
    threshold = now_utc() - timedelta(seconds=ONLINE_WINDOW_SECONDS)
    return await db.presence.count_documents({"last_seen": {"$gte": threshold}})


async def count_upgrades() -> int:
    return await db.upgrades.estimated_document_count()


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


PROMO_CODES = {"SINZUKU": 0.10, "XYIPACHOSIK": 0.067}
GOLD_PROMOS = {"XYIPACHOSIK"}
DEPOSIT_FEE = 0.20
MIN_DEPOSIT_RAP = 20
DEPOSIT_COOLDOWN_SECONDS = 60
ROBLOX_FRIEND_URL = "https://www.roblox.com/share?code=114adf7ac7b01243b752faf7c6c71b28&type=Profile&source=ProfileShare&stamp=1788366461111"
RECEIVERS = [
    {"id": "ysrent1", "nickname": "YSrent1", "handle": "@YSrent1", "avatar": "/receivers/ysrent1.png", "friend_url": ROBLOX_FRIEND_URL},
]


async def require_user(request: Request) -> dict:
    session_id = read_token(request)
    user = await db.users.find_one({"session_id": session_id}, {"_id": 0}) if session_id else None
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return user


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


async def take_skins(user: dict, uids: List[str], credit: bool = False) -> List[dict]:
    owned = {sk.get("uid"): sk for sk in user.get("skins", []) if sk.get("uid")}
    if not uids or len(uids) > 200 or len(set(uids)) != len(uids) or any(u not in owned for u in uids):
        raise HTTPException(status_code=400, detail="Выбранных скинов нет в вашем инвентаре")
    taken = [owned[u] for u in uids]
    update: dict = {"$pull": {"skins": {"uid": {"$in": uids}}}}
    if credit:
        update["$inc"] = {"balance": round(sum(float(sk.get("price") or 0) for sk in taken), 2)}
    res = await db.users.update_one(
        {"session_id": user["session_id"], "skins": {"$all": [{"$elemMatch": {"uid": u}} for u in uids]}}, update
    )
    if not res.matched_count:
        raise HTTPException(status_code=400, detail="Скины уже использованы")
    return taken


# ---------- Casino bank ----------
# House edge model (classic upgraders): shown chance = bet/price * RTP (default edge 15%). The roll is honest, nothing is cancelled.
# The only guard is solvency: a LARGE prize the bank cannot cover becomes a silent forced loss (player sees a normal loss, no refund, no message);
# small prizes (<= 2% of the bank) are always paid even into negative headroom.
BANK_DEFAULTS = {"rtp_target": 0.85}
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


def win_chance(total_bet: float, target_price: float, rtp: float) -> float:
    return min(MAX_CHANCE, total_bet / target_price * rtp)


def max_bet_ratio(rtp: float) -> float:
    """Bet may never exceed the skin price, and never give more than MAX_CHANCE."""
    return min(1.0, MAX_CHANCE / rtp)


async def bank_settings() -> dict:
    doc = await db.bank_settings.find_one({"id": "main"}, {"_id": 0, "id": 0}) or {}
    return {**BANK_DEFAULTS, **doc}


async def bank_balance() -> float:
    doc = await db.bank_state.find_one({"id": "main"}, {"_id": 0})
    return float((doc or {}).get("bank") or 0)


async def bank_add(kind: str, amount: float, note: Optional[str] = None, ref_id: Optional[str] = None, session_id: Optional[str] = None) -> float:
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
        _sum(db.withdrawals, {"status": "pending"}, "$item.price"),
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
    bank, li = await asyncio.gather(bank_balance(), liabilities())
    return bank - li["total"], {"bank": bank, "liabilities": li["total"]}


def losing_roll(chance: float) -> float:
    if random.random() < 0.3:
        angle = chance * 180 + random.uniform(2, 10)
        if random.random() < 0.5:
            angle = -angle
        return ((angle + 180) / 360) % 1.0

    r = random.random() * (1 - chance)
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
    if session_id.startswith("discord_") and read_token(request) != session_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
        raise HTTPException(status_code=400, detail="Некорректная сессия")
    return to_user_out(await get_or_create_user(session_id))


# ---------- Discord auth ----------
@api_router.get("/auth/discord/login")
async def discord_login():
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        return RedirectResponse(f"{APP_URL}/?auth_error=unavailable")
    state = secrets.token_urlsafe(16)
    await db.oauth_states.insert_one({"state": state, "created_at": now_utc()})
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
    if not await db.oauth_states.find_one_and_delete({"state": state, "created_at": {"$gt": now_utc() - timedelta(minutes=10)}}):
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
    await db.users.update_one(
        {"session_id": session_id},
        {
            "$set": {"nickname": nickname, "avatar": avatar, "discord_id": discord_id, "last_login": now_utc()},
            "$setOnInsert": {"balance": 0.0, "skins": [], "created_at": now_utc()},
        },
        upsert=True,
    )
    token = make_token(session_id)
    resp = RedirectResponse(f"{APP_URL}/auth/callback#token={token}")
    resp.set_cookie("bg_token", token, httponly=True, secure=True, samesite="lax", max_age=30 * 24 * 3600, path="/")
    resp.delete_cookie("bg_oauth_state", path="/api/auth/discord", secure=True, httponly=True, samesite="lax")
    return resp


@api_router.get("/auth/me", response_model=UserOut)
async def auth_me(request: Request):
    session_id = read_token(request)
    if not session_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    user = await db.users.find_one({"session_id": session_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return to_user_out(user)


@api_router.post("/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie("bg_token", path="/", secure=True, httponly=True, samesite="lax")
    return {"ok": True}


@api_router.get("/deposit/info")
async def deposit_info():
    return {"friend_url": ROBLOX_FRIEND_URL, "min_rap": MIN_DEPOSIT_RAP, "fee": DEPOSIT_FEE, "receivers": RECEIVERS, "cooldown": DEPOSIT_COOLDOWN_SECONDS}


@api_router.post("/promo/apply", response_model=UserOut)
async def promo_apply(payload: PromoIn, request: Request):
    user = await require_user(request)
    code = payload.code.strip().upper()
    bonus = PROMO_CODES.get(code)
    if bonus is None:
        raise HTTPException(status_code=400, detail="Промокод не найден")
    changes = {"promo_code": code, "promo_bonus": bonus}
    if code in GOLD_PROMOS:
        changes["gold_nick"] = True
    await db.users.update_one({"session_id": user["session_id"]}, {"$set": changes})
    user.update(changes)
    return to_user_out(user)


@api_router.post("/profile/roblox", response_model=UserOut)
async def profile_roblox(payload: RobloxIn, request: Request):
    user = await require_user(request)
    nick = payload.roblox_nick.strip()
    link = payload.roblox_link.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", nick):
        raise HTTPException(status_code=400, detail="Ник Roblox: 3–20 латинских букв, цифр или символов подчёркивания")
    if not link.startswith("https://www.roblox.com/") and not link.startswith("https://roblox.com/"):
        raise HTTPException(status_code=400, detail="Ссылка должна вести на roblox.com")
    pattern = f"^{re.escape(nick)}$"
    taken = await db.users.find_one({"roblox_nick": {"$regex": pattern, "$options": "i"}, "session_id": {"$ne": user["session_id"]}}, {"_id": 1})
    if taken:
        raise HTTPException(status_code=400, detail="Этот Roblox-ник уже привязан к другому аккаунту")
    try:
        await db.users.update_one({"session_id": user["session_id"]}, {"$set": {"roblox_nick": nick, "roblox_nick_normalized": nick.lower(), "roblox_link": link}})
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Этот Roblox-ник уже привязан к другому аккаунту")
    user.update({"roblox_nick": nick, "roblox_link": link})
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
    return {
        "user": to_user_out(user).model_dump(),
        "stats": await player_stats(sid),
        "best_drop": best[0] if best else None,
        "item_history": history,
        "games": [
            {
                "id": u["id"],
                "created_at": u["created_at"],
                "bet_amount": u.get("bet_amount", 0),
                "items_total": u.get("items_total", 0),
                "chance": u.get("chance"),
                "win": u.get("win"),
                "target": u.get("target_item"),
            }
            for u in upgrades
        ],
    }


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
    skins = await take_skins(user, uids)
    now = now_utc()
    await db.withdrawals.insert_many(
        [{"id": str(uuid.uuid4()), "session_id": user["session_id"], "item": sk, "status": "pending", "created_at": now} for sk in skins]
    )
    await db.item_history.insert_many(
        [{"id": str(uuid.uuid4()), "session_id": user["session_id"], "kind": "withdraw_requested", "item": sk, "price": float(sk.get("price") or 0), "created_at": now} for sk in skins]
    )
    fresh = await db.users.find_one({"session_id": user["session_id"]}, {"_id": 0})
    return to_user_out(fresh)


# ---------- Deposits ----------
def deposit_public(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "_id"}


@api_router.post("/deposits")
@serialized_user_action
async def create_deposit(payload: DepositIn, request: Request):
    user = await require_user(request)
    if not user.get("roblox_nick") or not user.get("roblox_link"):
        raise HTTPException(status_code=400, detail="Сначала привяжите Roblox-профиль (ник и ссылка) в профиле")
    receiver = next((r for r in RECEIVERS if r["id"] == payload.receiver_id), None)
    if not receiver:
        raise HTTPException(status_code=400, detail="Профиль для трейда не найден")
    last = await db.deposits.find_one({"session_id": user["session_id"]}, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
    if last and (now_utc() - as_utc(last["created_at"])).total_seconds() < DEPOSIT_COOLDOWN_SECONDS:
        wait = int(DEPOSIT_COOLDOWN_SECONDS - (now_utc() - as_utc(last["created_at"])).total_seconds())
        raise HTTPException(status_code=429, detail=f"Не так быстро: следующую заявку можно отправить через {max(1, wait)} сек")
    pending = await db.deposits.count_documents({"session_id": user["session_id"], "status": {"$in": ["pending", "processing"]}})
    if pending >= 5:
        raise HTTPException(status_code=400, detail="У вас уже 5 заявок в ожидании")
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
    res = await db.deposits.update_one(
        {"id": deposit_id, "session_id": user["session_id"], "status": "pending"},
        {"$set": {"status": "cancelled", "resolved_at": now_utc()}},
    )
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Заявка не найдена или уже обработана")
    return {"ok": True}


@api_router.get("/deposits/my")
async def my_deposits(request: Request):
    user = await require_user(request)
    docs = await db.deposits.find({"session_id": user["session_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return docs


# ---------- Admin ----------
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
    await db.admin_sessions.update_many({"revoked": False}, {"$set": {"revoked": True}})
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
    if status not in ("pending", "confirmed", "rejected", "cancelled"):
        raise HTTPException(status_code=400, detail="Неверный статус")
    order = 1 if status == "pending" else -1
    query = {"status": {"$in": ["pending", "processing"]}} if status == "pending" else {"status": status}
    docs = await db.deposits.find(query, {"_id": 0}).sort("created_at", order).to_list(200)
    return docs


@api_router.post("/admin/deposits/{deposit_id}/confirm")
async def admin_confirm_deposit(deposit_id: str, payload: AdminConfirmIn, request: Request):
    await require_admin(request)
    if payload.rap < MIN_DEPOSIT_RAP:
        raise HTTPException(status_code=400, detail=f"Скины дешевле {MIN_DEPOSIT_RAP} RAP не зачисляются — отклоните заявку")
    return await confirm_deposit(db, deposit_id, payload.rap, payload.note)


@api_router.post("/admin/deposits/{deposit_id}/preview")
async def admin_deposit_preview(deposit_id: str, payload: AdminConfirmIn, request: Request):
    await require_admin(request)
    dep = await db.deposits.find_one({"id": deposit_id}, {"_id": 0})
    if not dep:
        raise HTTPException(404, "Заявка не найдена")
    if payload.rap < MIN_DEPOSIT_RAP:
        raise HTTPException(400, "Минимальная сумма — 20 RAP")
    if dep["status"] == "processing":
        return {k: dep[k] for k in ("rap", "credited", "issued_skins", "skins_total", "balance_credited")}
    return await plan_deposit(db, dep, payload.rap)


@api_router.post("/admin/deposits/{deposit_id}/reject")
async def admin_reject_deposit(deposit_id: str, request: Request):
    await require_admin(request)
    res = await db.deposits.update_one({"id": deposit_id, "status": "pending"}, {"$set": {"status": "rejected", "resolved_at": now_utc()}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Заявка не найдена или уже обработана")
    return {"ok": True}


@api_router.get("/admin/withdrawals")
async def admin_withdrawals(request: Request, status: str = "pending"):
    await require_admin(request)
    if status not in ("pending", "done"):
        raise HTTPException(status_code=400, detail="Неверный статус")
    docs = await db.withdrawals.find({"status": status}, {"_id": 0}).sort("created_at", 1 if status == "pending" else -1).to_list(200)
    users = {u["session_id"]: u for u in await db.users.find({"session_id": {"$in": list({d["session_id"] for d in docs})}}, {"_id": 0, "session_id": 1, "nickname": 1, "roblox_nick": 1, "roblox_link": 1, "discord_id": 1}).to_list(500)}
    for d in docs:
        d["user"] = users.get(d["session_id"])
    return docs


@api_router.post("/admin/withdrawals/{withdrawal_id}/done")
async def admin_withdrawal_done(withdrawal_id: str, request: Request):
    await require_admin(request)
    w = await db.withdrawals.find_one_and_update(
        {"id": withdrawal_id, "status": "pending"}, {"$set": {"status": "done", "resolved_at": now_utc()}}, projection={"_id": 0}
    )
    if not w:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    await db.item_history.update_one(
        {"session_id": w["session_id"], "item.uid": w["item"]["uid"], "kind": "withdraw_requested"},
        {"$set": {"kind": "withdrawn", "resolved_at": now_utc()}},
    )
    price = float((w.get("item") or {}).get("price") or 0)
    bank = await bank_add("withdrawal", -price, note=f"Выдан {(w.get('item') or {}).get('name')}", ref_id=withdrawal_id, session_id=w.get("session_id"))
    return {"ok": True, "bank": bank}


@api_router.get("/admin/bank")
async def admin_bank(request: Request):
    await require_admin(request)
    bank = await bank_balance()
    li = await liabilities()
    st = await rtp_stats()
    deposits_total = await _sum(db.bank_ledger, {"kind": "deposit"}, "$amount")
    withdrawals_total = -await _sum(db.bank_ledger, {"kind": "withdrawal"}, "$amount")
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
    return {
        "bank": bank,
        "settings": await bank_settings(),
        "liabilities": li,
        "net": bank - li["total"],
        "deposits_total": deposits_total,
        "withdrawals_total": withdrawals_total,
        "adjustments_total": adjustments_total,
        "rtp": st,
        "rtp_24h": rtp_24h,
        "forced_top": forced_top,
        "games": {"total": total, "wins": wins, "forced_losses": forced, "forced_by": forced_by},
        "ledger": ledger,
    }


@api_router.put("/admin/bank/settings")
async def admin_bank_settings(payload: BankSettingsIn, request: Request):
    await require_admin(request)
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
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
    if abs(payload.amount) < 0.01:
        raise HTTPException(status_code=400, detail="Сумма должна быть не нулевой")
    amount = round(payload.amount, 2)
    if amount < 0:
        state = await db.bank_state.find_one_and_update(
            {"id": "main", "bank": {"$gte": -amount}}, {"$inc": {"bank": amount}},
            return_document=ReturnDocument.AFTER, projection={"_id": 0},
        )
        if not state:
            raise HTTPException(status_code=400, detail="Недостаточно средств в банке для списания")
        bank = float(state["bank"])
        await db.bank_ledger.insert_one({"id": str(uuid.uuid4()), "kind": "adjust", "amount": amount, "bank_after": bank, "note": payload.note.strip(), "created_at": now_utc()})
    else:
        bank = await bank_add("adjust", amount, note=payload.note.strip())
    return {"ok": True, "bank": bank}


@api_router.get("/live-drops")
async def live_drops(limit: int = 30):
    limit = max(1, min(limit, 100))
    docs = await db.drops.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    sids = list({d["session_id"] for d in docs})
    users = {u["session_id"]: u async for u in db.users.find({"session_id": {"$in": sids}}, {"_id": 0, "session_id": 1, "nickname": 1, "avatar": 1, "discord_id": 1, "gold_nick": 1})}
    out = []
    for d in docs:
        u = users.get(d["session_id"])
        if u:
            d.update({"nickname": u.get("nickname") or d.get("nickname"), "avatar": u.get("avatar"), "discord_id": u.get("discord_id"), "gold_nick": bool(u.get("gold_nick"))})
        out.append(Drop(**d).model_dump(exclude={"session_id"}))
    return out


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
    docs = await db.shop_items.find(query, {"_id": 0}).sort("price", direction).to_list(max(1, min(limit, 200)))
    return {"items": docs, "total": await db.shop_items.count_documents(query)}


@api_router.post("/upgrade", response_model=UpgradeOut)
async def upgrade(payload: UpgradeIn, request: Request):
    if read_token(request) != payload.session_id:
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
    if total_bet > target_price * max_ratio + 1e-6:
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

    # the roll itself is honest and independent of the bank; only the payout decision is serialized
    roll = random.random()
    win = abs(roll * 360 - 180) < chance * 180
    forced_loss = False
    forced_reason = None
    protection: dict = {"rtp": rtp}
    target = None
    upgrade_id = str(uuid.uuid4())
    if win:
        async with bank_lock() as lock:
            # solvency: the bank must cover every player liability plus this prize — otherwise the spin is a loss
            headroom, solvency = await solvency_headroom()
            bank_can_pay = headroom + 1e-9 >= target_price
            protection.update({**solvency, "bank_can_pay": bank_can_pay})
            if not lock.leased or not bank_can_pay:
                win, forced_loss, forced_reason = False, True, ("lock" if not lock.leased else "bank")
                roll = losing_roll(chance)
            else:
                target = {**shop_item, "uid": str(uuid.uuid4())}
                await db.users.update_one({"session_id": payload.session_id}, {"$push": {"skins": target}})
    angle = landing_angle(roll, chance, win)

    writes = [db.upgrades.insert_one({
        "id": upgrade_id,
        "session_id": payload.session_id,
        "bet_amount": payload.bet_amount,
        "bet_items": bet_skins,
        "items_total": items_total,
        "target_item": shop_item,
        "chance": chance,
        "roll": roll,
        "win": win,
        "forced_loss": forced_loss,
        "forced_reason": forced_reason if forced_loss else None,
        "protection": protection,
        "created_at": now_utc(),
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
            avatar=user.get("avatar"),
            discord_id=user.get("discord_id"),
            gold_nick=bool(user.get("gold_nick")),
        )
        writes.append(db.drops.insert_one(drop.model_dump()))
        writes.append(db.item_history.insert_one(
            {"id": str(uuid.uuid4()), "session_id": payload.session_id, "kind": "won", "item": target, "price": float(shop_item.get("price") or 0), "created_at": now_utc()}
        ))
    await asyncio.gather(*writes)
    upgrades_total = await count_upgrades()

    return UpgradeOut(
        id=upgrade_id,
        win=win,
        roll=roll,
        chance=chance,
        angle=angle,
        balance=new_balance,
        upgrades_total=upgrades_total,
    )


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

STATIC_DIR = ROOT_DIR / "static"

@api_router.get("/health")
async def health():
    return {"ok": True}


app.include_router(api_router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR / "static"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        file = STATIC_DIR / full_path
        if full_path and file.is_file():
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")

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


@app.on_event("startup")
async def ensure_indexes():
    await db.presence.create_index("session_id", unique=True)
    await db.presence.create_index("last_seen")
    await db.drops.create_index("created_at")
    await db.users.create_index("session_id", unique=True)
    await db.users.create_index("roblox_nick_normalized", unique=True, partialFilterExpression={"roblox_nick_normalized": {"$type": "string"}})
    await db.user_locks.create_index("session_id", unique=True)
    await db.item_history.create_index([("session_id", 1), ("created_at", -1)])
    await db.deposits.create_index([("status", 1), ("created_at", 1)])
    await db.withdrawals.create_index([("status", 1), ("created_at", 1)])
    await db.bank_ledger.create_index("created_at")
    await db.bank_ledger.create_index("id", unique=True)
    await db.bank_state.create_index("id", unique=True)
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
    for item in SHOP_ITEMS:
        await db.shop_items.update_one({"id": item["id"]}, {"$set": item}, upsert=True)
    # Never delete user inventory or historical drops as a side effect of restarting.
    for dep in await db.deposits.find({"status": "processing", "settlement_version": 1}, {"_id": 0}).to_list(None):
        try:
            await settle_deposit(db, dep)
        except Exception:
            logger.exception("Could not resume deposit %s; administrator may retry", dep["id"])


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
