"""Persistent promo codes and one activation record per account and promo.

Two promo types (backwards compatible):
- deposit_percent (default for old docs/requests): percent bonus applied to future
  deposits. One activation record per (promo_id, Discord-account) in
  promo_activations. User's active bonus fields (promo_id/code/bonus) are updated.
- rap_fixed: instant RAP gift credited to balance, no payment. One issuance per
  (promo_id, Discord-account) in promo_gift_ops, independent of session. Amount
  is snapshotted from DB. Active percent bonus is NOT touched. No fictitious
  deposit, no bank/pool change, no deposit referral reward.

Safety (no Mongo transactions required, works on standalone):
- Gift operation doc is the idempotency key: unique (promo_id, account_key),
  immutable recipient (account_key/session/discord) and amount.
- Limit reservation is a single atomic promo_codes update (reserved_count < max_uses
  + $addToSet reserved_keys). Retries reuse the same operation and never double-count:
  second attempt sees its own account_key already in reserved_keys and proceeds
  without re-incrementing.
- Balance credit + claim marker is a single conditional users update:
  balance is increased and claimed_promo_gifts marker added atomically; retries
  with the same gift id cannot credit twice.
- Repeat after timeout resumes the SAME operation (same promo_id/account_key),
  never creates a new one. A single asyncio.Lock is NOT sufficient (multi-worker),
  so all mutual exclusion is via these atomic single-document updates.
- Already-reserved operations complete per saved conditions even if the promo was
  later deleted or expired. New reservations after delete/expire are blocked.

NOTE on budget: there is no separate bonus wallet — gifted RAP lands on the
ordinary spendable balance and increases site liabilities (balances can buy /
withdraw skins). Until the giveaway budget and RAP-spend rules are approved,
keep rap_fixed DISABLED (RAP_FIXED_ENABLED=0, default). The flag gates creation
and activation; the code paths remain fully implemented and tested.
"""

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


DEFAULT_PROMOS = (
    ("SINZUKU", 10, False),
    ("XYIPACHOSIK", 6.7, True),
    ("PELMEN", 10, False),
    ("INKAB00M", 9, False),
)

PROMO_TYPE_DEPOSIT = "deposit_percent"
PROMO_TYPE_RAP = "rap_fixed"

# Instant-gift validation bounds (Decimal-checked, max 2 decimals).
MIN_RAP_GIFT = Decimal("0.01")
MAX_RAP_GIFT = Decimal("100000")
MAX_USES_LIMIT = 100000

# Kill-switch: rap_fixed stays OFF until the giveaway budget and the rules for
# spending/withdrawing gifted RAP are approved. No bonus wallet exists yet, so
# gifted RAP would otherwise become ordinary spendable balance.
# Enable explicitly with RAP_FIXED_ENABLED=1.
def rap_fixed_enabled() -> bool:
    return os.environ.get("RAP_FIXED_ENABLED", "0") == "1"


RAP_DISABLED_MESSAGE = (
    "RAP-промокоды временно отключены: бюджет раздачи и правила траты подаренного "
    "RAP ещё не согласованы"
)


class GiftLimitExhausted(Exception):
    pass


class GiftNotAvailable(Exception):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and getattr(dt, "tzinfo", None) is None else dt


def promo_type(promo) -> str:
    """Old documents/requests without a type are deposit_percent."""
    if not promo:
        return PROMO_TYPE_DEPOSIT
    t = promo.get("type") or PROMO_TYPE_DEPOSIT
    return t if t in (PROMO_TYPE_DEPOSIT, PROMO_TYPE_RAP) else PROMO_TYPE_DEPOSIT


def is_rap_fixed(promo) -> bool:
    return promo_type(promo) == PROMO_TYPE_RAP


def is_expired(promo, at=None) -> bool:
    exp = (promo or {}).get("expires_at")
    if not exp:
        return False
    try:
        exp = as_utc(exp)
        at = as_utc(at or now_utc())
        return exp <= at
    except Exception:
        return False


def validate_rap_amount(value) -> float:
    """Decimal validation: positive, <= MAX, max two decimals. Returns rounded float."""
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        raise ValueError("Сумма RAP должна быть числом")
    if d.is_nan() or d.is_infinite():
        raise ValueError("Сумма RAP должна быть конечным числом")
    if d <= 0:
        raise ValueError("Сумма RAP должна быть положительной")
    if d < MIN_RAP_GIFT:
        raise ValueError(f"Минимальная сумма — {MIN_RAP_GIFT} RAP")
    if d > MAX_RAP_GIFT:
        raise ValueError(f"Максимальная сумма — {MAX_RAP_GIFT} RAP")
    # Max two decimal places: exponent >= -2 (e.g. 10.00 ok, 10.001 not).
    if d.as_tuple().exponent < -2:
        raise ValueError("Сумма RAP — максимум два знака после запятой")
    return float(d.quantize(Decimal("0.01")))


def validate_max_uses(value) -> int:
    try:
        # bool is subclass of int — reject explicitly.
        if isinstance(value, bool):
            raise ValueError()
        n = int(value) if not isinstance(value, int) else value
        if isinstance(value, float) and not value.is_integer():
            raise ValueError()
        if isinstance(value, str) and str(value).strip() != str(n):
            # "10.5", "abc" etc. fall through to range check failure below,
            # but keep strictness for floats in strings.
            float(value)  # raises if not numeric
            if float(value) != n:
                raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("Лимит использований должен быть целым числом")
    if n < 1 or n > MAX_USES_LIMIT:
        raise ValueError(f"Лимит использований — от 1 до {MAX_USES_LIMIT}")
    return n


def promo_fields(promo):
    # Deposit terms are frozen per promo; gifts never touch these fields.
    if not promo or is_rap_fixed(promo):
        return {"promo_id": None, "promo_code": None, "promo_bonus": 0.0}
    return {
        "promo_id": promo["id"] if promo else None,
        "promo_code": promo["code"] if promo else None,
        "promo_bonus": round(promo["percent"] / 100, 6) if promo else 0.0,
    }


def account_key(user):
    # Discord login always uses discord_<id>; older deposits may omit discord_id.
    discord_id = user.get("discord_id")
    sid = user.get("session_id") or ""
    if not discord_id and sid.startswith("discord_"):
        discord_id = sid[len("discord_"):]
    return f"discord:{discord_id}" if discord_id else f"session:{sid}" if sid else None


def discord_id_of(user):
    discord_id = user.get("discord_id")
    sid = user.get("session_id") or ""
    if not discord_id and sid.startswith("discord_"):
        discord_id = sid[len("discord_"):]
    return discord_id or None


def gift_id_for(promo_id: str, acc_key: str) -> str:
    return f"rap:{promo_id}:{acc_key}"


async def record_activation(db, promo_id, user):
    key = account_key(user)
    if key is None:
        return
    query = {"promo_id": promo_id, "account_key": key}
    try:
        await db.promo_activations.update_one(query, {"$setOnInsert": {
            **query, "created_at": datetime.now(timezone.utc),
        }}, upsert=True)
    except DuplicateKeyError:
        # A simultaneous activation of this same promo/account already recorded it.
        pass


async def refresh_user_promo(db, user):
    """Resolve current terms; cached user fields cannot revive a deleted bonus."""
    if not user.get("promo_id") and not user.get("promo_code"):
        return user
    query = {"id": user["promo_id"]} if user.get("promo_id") else {"code": user["promo_code"].upper()}
    promo = await db.promo_codes.find_one({**query, "deleted": False}, {"_id": 0})
    # A rap_fixed promo never owns the active percent bonus fields; if the cached
    # promo_id somehow points at a gift promo (legacy misuse), clear the bonus.
    if promo is not None and is_rap_fixed(promo):
        return {**user, **promo_fields(None)}
    return {**user, **promo_fields(promo)}


# ---------------------------------------------------------------------------
# RAP gift flow (idempotent, no transactions)
# ---------------------------------------------------------------------------

async def get_or_create_gift_op(db, promo, acc_key, session_id, discord_id):
    """Same (promo_id, account_key) always maps to the SAME operation doc.

    Recipient and amount are immutable: $setOnInsert only; retries reuse saved values.
    """
    now = now_utc()
    key = {"promo_id": promo["id"], "account_key": acc_key}
    amount = float(promo["amount_rap"])
    await db.promo_gift_ops.update_one(key, {"$setOnInsert": {
        **key,
        "session_id": session_id,
        "discord_id": discord_id,
        "amount_rap": amount,
        "promo_code": promo.get("code"),
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }}, upsert=True)
    return await db.promo_gift_ops.find_one(key)


async def reserve_rap_slot(db, promo_id, acc_key):
    """Idempotent atomic limit reservation on the promo document itself.

    Single find_one_and_update with (deleted=False, not expired, still rap_fixed,
    this account not yet in reserved_keys, reserved_count < max_uses).
    - Success -> this call booked the slot (exactly once per account).
    - Failure because this account is already in reserved_keys -> already booked
      (e.g. retry after a crash between promo update and op marking): treat as success.
    - Failure because deleted/expired/type-changed and NOT already booked -> blocked.
    - Failure because limit reached -> GiftLimitExhausted (op stays pending so a
      later max_uses increase can unblock a retry; no slot consumed).
    """
    now = now_utc()
    promo = await db.promo_codes.find_one({"id": promo_id}, {"_id": 0})
    if promo is None:
        raise GiftNotAvailable("Промокод не найден")
    if promo.get("deleted"):
        # Already-reserved completions bypass deletion; check booking first.
        if acc_key in (promo.get("reserved_keys") or []):
            return promo
        raise GiftNotAvailable("Промокод удалён")
    if promo_type(promo) != PROMO_TYPE_RAP:
        raise GiftNotAvailable("Тип промокода изменён")
    if is_expired(promo, now):
        if acc_key in (promo.get("reserved_keys") or []):
            return promo
        raise GiftNotAvailable("Срок действия промокода истёк")
    try:
        max_uses = validate_max_uses(promo.get("max_uses"))
    except ValueError:
        raise GiftNotAvailable("У промокода некорректный лимит")

    updated = await db.promo_codes.find_one_and_update(
        {
            "id": promo_id,
            "deleted": False,
            "type": PROMO_TYPE_RAP,
            "reserved_keys": {"$ne": acc_key},
            "$and": [
                {"$or": [
                    {"reserved_count": {"$lt": max_uses}},
                    {"reserved_count": {"$exists": False}},
                ]},
                {"$or": [
                    {"expires_at": None},
                    {"expires_at": {"$exists": False}},
                    {"expires_at": {"$gt": now}},
                ]},
            ],
        },
        {
            "$inc": {"reserved_count": 1},
            "$addToSet": {"reserved_keys": acc_key},
            "$set": {"updated_at": now},
        },
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    if updated is not None:
        return updated
    # Distinguish the failure reason with a fresh read (no slot consumed here).
    fresh = await db.promo_codes.find_one({"id": promo_id}, {"_id": 0})
    if fresh is None or fresh.get("deleted"):
        if fresh is not None and acc_key in (fresh.get("reserved_keys") or []):
            return fresh
        raise GiftNotAvailable("Промокод удалён")
    if promo_type(fresh) != PROMO_TYPE_RAP:
        raise GiftNotAvailable("Тип промокода изменён")
    if is_expired(fresh, now_utc()):
        if acc_key in (fresh.get("reserved_keys") or []):
            return fresh
        raise GiftNotAvailable("Срок действия промокода истёк")
    if acc_key in (fresh.get("reserved_keys") or []):
        # Retry after crash: slot was booked but op marking was lost. No re-increment.
        return fresh
    reserved = fresh.get("reserved_count") or 0
    try:
        limit = validate_max_uses(fresh.get("max_uses"))
    except ValueError:
        raise GiftNotAvailable("У промокода некорректный лимит")
    if reserved >= limit:
        raise GiftLimitExhausted("Лимит использований исчерпан")
    # Extremely rare: filter missed for another reason (e.g. concurrent max_uses
    # edit). Do not consume a slot; caller retries and re-reads.
    raise GiftLimitExhausted("Лимит использований исчерпан")


async def settle_rap_credit(db, op):
    """Credit op's ORIGINAL session doc + claim marker in ONE conditional update.

    Returns True if the credit was already done before this call (repeat),
    False if this call performed it. Exactly-once per gift id across retries,
    restarts and session changes (all retries target the same original doc).
    No deposit, no bank/pool, no referral reward here.
    """
    gift_id = gift_id_for(op["promo_id"], op["account_key"])
    amount = round(float(op["amount_rap"]), 2)
    target_sid = op.get("session_id")
    if not target_sid:
        raise GiftNotAvailable("У операции нет получателя")

    res = await db.users.update_one(
        {"session_id": target_sid, "claimed_promo_gifts": {"$ne": gift_id}},
        {"$inc": {"balance": amount}, "$addToSet": {"claimed_promo_gifts": gift_id}},
    )
    if res.matched_count:
        already = False
    else:
        holder = await db.users.find_one(
            {"session_id": target_sid, "claimed_promo_gifts": gift_id}, {"_id": 1}
        )
        if holder:
            already = True  # idempotent repeat (or concurrent loser)
        else:
            # No doc matched and no marker: recipient doc is missing.
            if not await db.users.find_one({"session_id": target_sid}, {"_id": 1}):
                raise GiftNotAvailable("Аккаунт получателя не найден. Выдача не выполнена")
            # Should not happen (filter matched nothing but doc exists without marker
            # means a concurrent winner slipped in between — re-check once).
            holder = await db.users.find_one(
                {"session_id": target_sid, "claimed_promo_gifts": gift_id}, {"_id": 1}
            )
            already = bool(holder)
            if not already:
                raise GiftNotAvailable("Не удалось начислить подарок. Повторите попытку")

    now = now_utc()
    await db.promo_gift_ops.update_one(
        {"promo_id": op["promo_id"], "account_key": op["account_key"],
         "status": {"$in": ["pending", "reserved"]}},
        {"$set": {"status": "redeemed", "redeemed_at": now, "updated_at": now}},
    )
    # Separate gift journal (audit, immutable, no financial side effects).
    await db.promo_gifts.update_one({"id": gift_id}, {"$setOnInsert": {
        "id": gift_id,
        "promo_id": op["promo_id"],
        "promo_code": op.get("promo_code"),
        "account_key": op["account_key"],
        "session_id": target_sid,
        "discord_id": op.get("discord_id"),
        "amount_rap": amount,
        "created_at": op.get("created_at") or now,
        "redeemed_at": now,
    }}, upsert=True)
    return already


async def apply_rap_gift(db, promo, user):
    """Full gift pipeline for one POST /api/promo/apply call. Returns dict.

    - Resolves recipient ONLY from server-side auth (discord account).
    - Reuses the same operation on repeats/timeouts/restarts/session changes.
    - Never touches the active percent bonus.
    """
    acc_key = account_key(user)
    discord_id = discord_id_of(user)
    if not discord_id or not acc_key or not acc_key.startswith("discord:"):
        raise GiftNotAvailable("Войдите через Discord, чтобы получить подарок")
    if promo is None or promo.get("deleted"):
        raise GiftNotAvailable("Промокод не найден")
    if promo_type(promo) != PROMO_TYPE_RAP:
        raise GiftNotAvailable("Промокод не найден")
    if not rap_fixed_enabled():
        raise GiftNotAvailable(RAP_DISABLED_MESSAGE)
    if is_expired(promo, now_utc()):
        # Expired but already booked by THIS account -> finish per saved terms.
        booked = acc_key in ((await db.promo_codes.find_one(
            {"id": promo["id"]}, {"reserved_keys": 1})) or {}).get("reserved_keys", [])
        if not booked:
            # Mark terminal so repeats return the same error without re-booking.
            try:
                await db.promo_gift_ops.update_one(
                    {"promo_id": promo["id"], "account_key": acc_key, "status": "pending"},
                    {"$set": {"status": "failed", "fail_reason": "expired",
                              "updated_at": now_utc()}},
                )
            except Exception:
                pass
            raise GiftNotAvailable("Срок действия промокода истёк")

    op = await get_or_create_gift_op(
        db, promo, acc_key, user["session_id"], discord_id,
    )
    if op.get("status") == "redeemed":
        return {"amount": round(float(op["amount_rap"]), 2), "already": True, "op": op}
    if op.get("status") == "failed":
        raise GiftNotAvailable(op.get("fail_reason") or "Промокод недоступен")
    # NOTE: exhausted is NOT terminal here — creation keeps ops pending so a later
    # max_uses increase can unblock a retry. Only failed/expired/deleted stick.
    # Reservation (idempotent atomic). Already-booked completions ignore
    # deletion/expiry via saved amount inside reserve_rap_slot.
    if op.get("status") == "pending":
        try:
            await reserve_rap_slot(db, promo["id"], acc_key)
        except (GiftLimitExhausted, GiftNotAvailable):
            raise
        await db.promo_gift_ops.update_one(
            {"promo_id": promo["id"], "account_key": acc_key, "status": "pending"},
            {"$set": {"status": "reserved", "reserved_at": now_utc(),
                      "updated_at": now_utc()}},
        )
        op = await db.promo_gift_ops.find_one(
            {"promo_id": promo["id"], "account_key": acc_key})
        if op.get("status") in ("failed",):
            raise GiftNotAvailable(op.get("fail_reason") or "Промокод недоступен")

    # Settle to the IMMUTABLE original recipient (saved conditions).
    fresh_op = await db.promo_gift_ops.find_one(
        {"promo_id": promo["id"], "account_key": acc_key})
    # If a concurrent call already redeemed, this is a repeat.
    was_redeemed = (fresh_op.get("status") == "redeemed")
    # settle_rap_credit is idempotent; its return tells whether credit pre-existed.
    already_credited = await settle_rap_credit(db, fresh_op)
    return {"amount": round(float(fresh_op["amount_rap"]), 2),
            "already": bool(was_redeemed or already_credited),
            "op": fresh_op}


async def resume_incomplete_gifts(db, limit=100):
    """Best-effort completion of crash-interrupted gifts (called on startup).

    - reserved (booked) ops complete per SAVED amount even if the promo was later
      deleted/expired (no new bookings here, only settlement).
    - pending ops are left for the next user retry (which re-attempts the atomic
      booking); marking them here could wrongly fail an op whose promo still has
      capacity after a max_uses increase.
    """
    try:
        cursor = db.promo_gift_ops.find({"status": "reserved"}).sort("created_at", 1).limit(limit)
        ops = await cursor.to_list(limit)
    except Exception:
        return 0
    done = 0
    for op in ops:
        try:
            await settle_rap_credit(db, op)
            done += 1
        except Exception:
            continue
    return done


async def ensure_promotions(db):
    await db.promo_codes.create_index("id", unique=True)
    await db.promo_codes.create_index("code", unique=True, partialFilterExpression={"deleted": False})
    await db.promo_activations.create_index([("promo_id", 1), ("account_key", 1)], unique=True)
    await db.users.create_index("promo_id")
    # Gift operations: one issuance per (promo_id, Discord-account), any session.
    await db.promo_gift_ops.create_index([("promo_id", 1), ("account_key", 1)], unique=True)
    await db.promo_gift_ops.create_index([("promo_id", 1), ("status", 1)])
    await db.promo_gift_ops.create_index([("status", 1), ("created_at", 1)])
    # Separate gift journal (audit only — never a deposit, bank or referral entry).
    await db.promo_gifts.create_index("id", unique=True)
    await db.promo_gifts.create_index([("promo_id", 1), ("created_at", -1)])
    await db.promo_gifts.create_index([("account_key", 1), ("created_at", -1)])
    for code, percent, gold_nick in DEFAULT_PROMOS:
        # Stable seed IDs and tombstones preserve admin edits/deletions on restart.
        await db.promo_codes.update_one({"id": f"default-{code.lower()}"}, {"$setOnInsert": {
            "id": f"default-{code.lower()}", "code": code, "percent": percent,
            "type": PROMO_TYPE_DEPOSIT,
            "gold_nick": gold_nick, "deleted": False, "created_at": datetime.now(timezone.utc),
        }}, upsert=True)

    # Backfill: old promo docs without a type are deposit_percent; gift promos get
    # booking counters. Safe to re-run (only touches docs missing the fields).
    try:
        await db.promo_codes.update_many(
            {"type": {"$exists": False}},
            {"$set": {"type": PROMO_TYPE_DEPOSIT}},
        )
        await db.promo_codes.update_many(
            {"type": PROMO_TYPE_RAP, "reserved_count": {"$exists": False}},
            {"$set": {"reserved_count": 0}},
        )
        await db.promo_codes.update_many(
            {"type": PROMO_TYPE_RAP, "reserved_keys": {"$exists": False}},
            {"$set": {"reserved_keys": []}},
        )
    except Exception:
        pass

    migration_id = "promo-activation-history-v1"
    if await db.migrations.find_one({"_id": migration_id}):
        return
    promos = {p["code"]: p async for p in db.promo_codes.find({"deleted": False})}
    # Recover all available evidence, including previous codes in deposit history.
    # Activations overwritten before this migration with no deposit are unknowable.
    for collection in (db.users, db.deposits):
        async for row in collection.find({"promo_code": {"$type": "string"}}, {
            "session_id": 1, "discord_id": 1, "promo_code": 1,
        }):
            promo = promos.get(row["promo_code"].strip().upper())
            if promo and promo_type(promo) == PROMO_TYPE_DEPOSIT:
                await record_activation(db, promo["id"], row)
    async for user in db.users.find({"promo_code": {"$type": "string"}, "promo_id": {"$exists": False}}):
        promo = promos.get(user["promo_code"].strip().upper())
        if promo and promo_type(promo) == PROMO_TYPE_DEPOSIT:
            await db.users.update_one({"_id": user["_id"], "promo_code": user["promo_code"]}, {"$set": promo_fields(promo)})
    await db.migrations.update_one({"_id": migration_id}, {"$setOnInsert": {
        "completed_at": datetime.now(timezone.utc),
    }}, upsert=True)
