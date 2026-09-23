"""Server-side duty shifts: one open shift per staff member, pauses excluded, days in Asia/Qyzylorda."""
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

TZ = ZoneInfo("Asia/Qyzylorda")
LONG_SHIFT = timedelta(hours=12)
OFFLINE_AFTER = timedelta(seconds=120)


def now():
    return datetime.now(timezone.utc)


def utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def ensure_indexes(db):
    await db.staff_shifts.create_index("id", unique=True)
    await db.staff_shifts.create_index("staff_id", unique=True, partialFilterExpression={"is_open": True})
    await db.staff_shifts.create_index([("staff_id", 1), ("started_at", -1)])


def worked_seconds(shift, start=None, end=None, at=None) -> int:
    at = at or now()
    lo, hi = utc(shift["started_at"]), utc(shift.get("ended_at")) or at
    if start:
        lo = max(lo, start)
    if end:
        hi = min(hi, end)
    if hi <= lo:
        return 0
    total = (hi - lo).total_seconds()
    for pause in shift.get("pauses", []):
        ps, pe = max(utc(pause["start"]), lo), min(utc(pause.get("end")) or at, hi)
        if pe > ps:
            total -= (pe - ps).total_seconds()
    return max(0, int(total))


def public(shift) -> dict:
    at = now()
    started, ended = utc(shift["started_at"]), utc(shift.get("ended_at"))
    duration = (ended or at) - started
    last_seen = utc(shift.get("last_seen")) or started
    return {
        "id": shift["id"], "staff_id": shift["staff_id"], "status": shift["status"],
        "started_at": started, "ended_at": ended, "worked_seconds": worked_seconds(shift, at=at),
        "paused_seconds": max(0, int(duration.total_seconds()) - worked_seconds(shift, at=at)),
        "pauses": shift.get("pauses", []), "gaps_seconds": int(shift.get("gaps_seconds", 0)), "gaps_count": int(shift.get("gaps_count", 0)),
        "offline": shift["status"] != "closed" and at - last_seen > OFFLINE_AFTER,
        "long": duration > LONG_SHIFT, "adjustments": shift.get("adjustments", []),
    }


async def current(db, staff_id):
    return await db.staff_shifts.find_one({"staff_id": staff_id, "is_open": True}, {"_id": 0})


async def start(db, staff_id):
    at = now()
    doc = {"id": str(uuid.uuid4()), "staff_id": staff_id, "status": "open", "is_open": True,
           "started_at": at, "ended_at": None, "pauses": [], "last_seen": at, "gaps_seconds": 0, "gaps_count": 0}
    try:
        await db.staff_shifts.insert_one(dict(doc))
    except DuplicateKeyError:
        raise HTTPException(409, "Смена уже открыта") from None
    return public(doc)


async def _transition(db, staff_id, query, update, array_filters=None, error="Нет открытой смены"):
    res = await db.staff_shifts.update_one({"staff_id": staff_id, "is_open": True, **query}, update, array_filters=array_filters)
    if not res.matched_count:
        raise HTTPException(409, error)
    shift = await db.staff_shifts.find_one({"staff_id": staff_id}, {"_id": 0}, sort=[("started_at", -1)])
    return public(shift)


async def pause(db, staff_id):
    at = now()
    return await _transition(db, staff_id, {"status": "open"},
                             {"$set": {"status": "paused", "last_seen": at}, "$push": {"pauses": {"start": at, "end": None}}},
                             error="Смена не идёт или уже на паузе")


async def resume(db, staff_id):
    at = now()
    return await _transition(db, staff_id, {"status": "paused"},
                             {"$set": {"status": "open", "last_seen": at, "pauses.$[p].end": at}}, [{"p.end": None}],
                             error="Смена не на паузе")


async def end(db, staff_id):
    at = now()
    return await _transition(db, staff_id, {}, {"$set": {"status": "closed", "ended_at": at, "pauses.$[p].end": at}, "$unset": {"is_open": ""}},
                             [{"p.end": None}])


async def close_any(db, staff_id):
    with_open = await current(db, staff_id)
    if with_open:
        await end(db, staff_id)


async def heartbeat(db, staff_id):
    shift = await current(db, staff_id)
    if not shift:
        return None
    at, last = now(), utc(shift.get("last_seen")) or utc(shift["started_at"])
    gap = at - last
    update = {"$set": {"last_seen": at}}
    if gap > OFFLINE_AFTER and shift["status"] == "open":
        update["$inc"] = {"gaps_seconds": int(gap.total_seconds()), "gaps_count": 1}
    # Conditional on the previous timestamp: several tabs cannot count the same gap twice.
    await db.staff_shifts.update_one({"id": shift["id"], "last_seen": shift.get("last_seen")}, update)
    return public(await db.staff_shifts.find_one({"id": shift["id"]}, {"_id": 0}))


async def edit(db, shift_id, started_at, ended_at, reason, actor):
    started_at, ended_at = utc(started_at), utc(ended_at)
    if not ended_at > started_at or ended_at > now() + timedelta(minutes=1) or ended_at - started_at > timedelta(days=7):
        raise HTTPException(400, "Неверный интервал смены")
    shift = await db.staff_shifts.find_one({"id": shift_id}, {"_id": 0})
    if not shift:
        raise HTTPException(404, "Смена не найдена")
    adjustment = {"at": now(), "by": actor, "reason": reason.strip(), "old_started_at": shift["started_at"], "old_ended_at": shift.get("ended_at"),
                  "new_started_at": started_at, "new_ended_at": ended_at}
    await db.staff_shifts.update_one({"id": shift_id}, {
        "$set": {"started_at": started_at, "ended_at": ended_at, "status": "closed", "pauses.$[p].end": ended_at},
        "$unset": {"is_open": ""}, "$push": {"adjustments": adjustment}}, array_filters=[{"p.end": None}])
    return public(await db.staff_shifts.find_one({"id": shift_id}, {"_id": 0}))


def local_day_start(day) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=TZ).astimezone(timezone.utc)


def period_bounds(period: str, date_from=None, date_to=None):
    today = now().astimezone(TZ).date()
    if period == "today":
        return local_day_start(today), local_day_start(today + timedelta(days=1))
    if period == "range":
        try:
            first = datetime.strptime(date_from, "%Y-%m-%d").date()
            last = datetime.strptime(date_to, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            raise HTTPException(400, "Укажите даты периода в формате ГГГГ-ММ-ДД") from None
        if last < first or (last - first).days > 366:
            raise HTTPException(400, "Неверный период")
        return local_day_start(first), local_day_start(last + timedelta(days=1))
    if period == "all":
        return None, None
    raise HTTPException(400, "Неверный период")


def by_day(shifts, start, end) -> list:
    """Worked time per local day; a shift across midnight is split between both days."""
    if not shifts:
        return []
    at = now()
    first = start or min(utc(s["started_at"]) for s in shifts)
    last = end or at
    day = first.astimezone(TZ).date()
    rows = []
    while local_day_start(day) < last and len(rows) < 400:
        lo, hi = local_day_start(day), local_day_start(day + timedelta(days=1))
        seconds = sum(worked_seconds(s, lo, hi, at) for s in shifts)
        if seconds:
            rows.append({"day": day.isoformat(), "worked_seconds": seconds})
        day += timedelta(days=1)
    return rows
