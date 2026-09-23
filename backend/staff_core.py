"""Staff skin intake: atomic claims, immutable report versions, owner decisions and real-skin movements.

Crediting reuses deposit_settlement.settle_deposit (crash-resumable). The deposit document is the single
decision lock: approve/revision/reject all require staff_state == "review" and the current report id.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument

import live_chat as chat
import staff_evidence as ev
from chat_texts import tr
from deposit_allocation import cents
from deposit_settlement import plan_deposit, settle_deposit
from roblox_profile import profile_fields

logger = logging.getLogger(__name__)
MIN_RAP = 200
FEE = 0.20
FREE = {"status": "pending", "payment_method": None, "staff_id": None, "via_chat": True}
BUSY_STATES = ("assigned", "review", "revision", "return_required", "return_review")


def now():
    return datetime.now(timezone.utc)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    qty: int = Field(ge=1, le=1000)
    value: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)


class ReportIn(Strict):
    items: List[ItemIn] = Field(min_length=1, max_length=50)
    evidence: List[str] = Field(min_length=1, max_length=6)
    received: bool
    value_checked: bool
    note: str = Field(default="", max_length=500)


class ReturnIn(Strict):
    evidence: List[str] = Field(min_length=1, max_length=6)
    note: str = Field(default="", max_length=500)


class TransferIn(Strict):
    items: List[ItemIn] = Field(min_length=1, max_length=50)
    evidence: List[str] = Field(min_length=1, max_length=6)
    note: str = Field(default="", max_length=500)


class ReasonIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


class StaffIn(Strict):
    discord_id: str = Field(min_length=3, max_length=32)
    roblox_display_name: str = Field(max_length=40)
    roblox_nick: str = Field(max_length=40)
    roblox_link: str = Field(max_length=300)


class StaffUpdateIn(Strict):
    roblox_display_name: str = Field(max_length=40)
    roblox_nick: str = Field(max_length=40)
    roblox_link: str = Field(max_length=300)


def clean_items(items) -> tuple:
    rows = [{"name": i.name.strip(), "qty": int(i.qty), "value": cents(i.value) / 100} for i in items]
    if any(not r["name"] for r in rows):
        raise HTTPException(400, "Укажите название каждого предмета")
    total = sum(r["qty"] * cents(r["value"]) for r in rows) / 100
    return rows, sum(r["qty"] for r in rows), total


async def ensure_indexes(db):
    await db.staff.create_index("id", unique=True)
    await db.staff.create_index("session_id", unique=True)
    await db.staff_reports.create_index("id", unique=True)
    await db.staff_reports.create_index([("deposit_id", 1), ("version", 1)], unique=True)
    await db.staff_reports.create_index([("staff_id", 1), ("created_at", -1)])
    await db.staff_reports.create_index("status")
    await db.staff_moves.create_index("id", unique=True)
    await db.staff_moves.create_index([("staff_id", 1), ("status", 1)])
    await db.staff_audit.create_index("created_at")
    await db.deposits.create_index([("staff_id", 1), ("status", 1)])


async def audit(db, actor, action, staff_id=None, ref=None, details=None):
    await db.staff_audit.insert_one({"id": str(uuid.uuid4()), "actor": actor, "action": action, "staff_id": staff_id,
                                     "ref": ref, "details": details or {}, "created_at": now()})


def receiver(staff) -> dict:
    return {k: staff.get(k) for k in ("roblox_display_name", "roblox_nick", "roblox_link")}


def player(dep) -> dict:
    return {k: dep.get(k) for k in ("session_id", "nickname", "discord_id", "roblox_display_name", "roblox_nick", "roblox_link", "chat_id")}


# ---------- staff accounts ----------
async def create_staff(db, payload: StaffIn, actor):
    fields = profile_fields(payload.roblox_display_name, payload.roblox_nick, payload.roblox_link)
    user = await db.users.find_one({"discord_id": payload.discord_id.strip()}, {"_id": 0, "session_id": 1, "nickname": 1, "discord_id": 1})
    if not user:
        raise HTTPException(404, "Игрок с таким Discord ID не найден. Сотрудник должен один раз войти на сайт через Discord")
    existing = await db.staff.find_one({"session_id": user["session_id"]}, {"_id": 0})
    if existing:
        raise HTTPException(409, "Этот аккаунт уже добавлен в сотрудники")
    doc = {"id": str(uuid.uuid4()), "session_id": user["session_id"], "discord_id": user.get("discord_id"),
           "nickname": user.get("nickname"), **fields, "active": True, "created_at": now(), "disabled_at": None}
    await db.staff.insert_one(dict(doc))
    await audit(db, actor, "staff_create", doc["id"], details={"discord_id": doc["discord_id"], **fields})
    return doc


async def update_staff(db, staff_id, payload: StaffUpdateIn, actor):
    fields = profile_fields(payload.roblox_display_name, payload.roblox_nick, payload.roblox_link)
    res = await db.staff.update_one({"id": staff_id}, {"$set": fields})
    if not res.matched_count:
        raise HTTPException(404, "Сотрудник не найден")
    await audit(db, actor, "staff_update", staff_id, details=fields)
    return await db.staff.find_one({"id": staff_id}, {"_id": 0})


async def set_active(db, staff_id, active: bool, actor):
    res = await db.staff.update_one({"id": staff_id}, {"$set": {"active": active, "disabled_at": None if active else now()}})
    if not res.matched_count:
        raise HTTPException(404, "Сотрудник не найден")
    await audit(db, actor, "staff_enable" if active else "staff_disable", staff_id)
    return await db.staff.find_one({"id": staff_id}, {"_id": 0})


# ---------- requests ----------
async def _chat_of(db, dep):
    return await db.chats.find_one({"id": dep.get("chat_id")}, {"_id": 0}) if dep.get("chat_id") else None


async def _tell_player(db, dep, sender, text, extra=None):
    found = await _chat_of(db, dep)
    if found:
        with_lang = text(chat.lang_of(found)) if callable(text) else text
        await chat.post_message(db, found, sender, with_lang, extra)


def _receiver_text(r):
    def render(lang):
        if lang == "en":
            return (f"Your trade is handled by our staff member.\nRoblox: {r['roblox_display_name']} (@{r['roblox_nick']})\n"
                    f"Profile: {r['roblox_link']}\nAdd this account and send the skins only to it.")
        return (f"Вашу заявку принимает сотрудник.\nRoblox: {r['roblox_display_name']} (@{r['roblox_nick']})\n"
                f"Профиль: {r['roblox_link']}\nДобавьте этот аккаунт и передавайте скины только ему.")
    return render


async def queue(db):
    return await db.deposits.find(FREE, {"_id": 0}).sort("created_at", 1).to_list(100)


async def claim(db, staff, dep_id):
    r = receiver(staff)
    dep = await db.deposits.find_one_and_update(
        {"id": dep_id, **FREE},
        {"$set": {"staff_id": staff["id"], "staff_nick": staff.get("nickname"), "staff_flow": True, "staff_state": "assigned",
                  "assigned_at": now(), "staff_receiver": r}},
        return_document=ReturnDocument.AFTER, projection={"_id": 0})
    if not dep:
        raise HTTPException(409, "Заявку уже взял другой сотрудник или она закрыта")
    await audit(db, f"staff:{staff['id']}", "claim", staff["id"], dep_id)
    await _tell_player(db, dep, "admin", _receiver_text(r), {"kind": "staff_receiver", "staff_receiver": r})
    return dep


async def assigned(db, staff, dep_id):
    dep = await db.deposits.find_one({"id": dep_id, "staff_id": staff["id"]}, {"_id": 0})
    if not dep:
        raise HTTPException(404, "Заявка не найдена или назначена другому сотруднику")
    return dep


async def my_requests(db, staff):
    active = await db.deposits.find({"staff_id": staff["id"], "status": {"$in": ["pending", "processing"]}}, {"_id": 0}).sort("assigned_at", -1).to_list(200)
    done = await db.deposits.find({"staff_id": staff["id"], "status": {"$nin": ["pending", "processing"]}}, {"_id": 0}).sort("resolved_at", -1).to_list(30)
    return {"active": active, "done": done}


async def mark_transfer_started(db, staff, dep_id):
    res = await db.deposits.update_one({"id": dep_id, "staff_id": staff["id"], "status": "pending", "transfer_started_at": None},
                                       {"$set": {"transfer_started_at": now()}})
    if res.modified_count:
        await audit(db, f"staff:{staff['id']}", "transfer_started", staff["id"], dep_id)
    return await assigned(db, staff, dep_id)


async def submit_report(db, staff, dep_id, payload: ReportIn):
    dep = await assigned(db, staff, dep_id)
    if dep["status"] != "pending" or dep.get("staff_state") not in ("assigned", "revision"):
        raise HTTPException(409, "Отчёт сейчас отправить нельзя: заявка на проверке или уже закрыта")
    if not (payload.received and payload.value_checked):
        raise HTTPException(400, "Отметьте «Скины получил» и «Стоимость проверил»")
    items, count, total = clean_items(payload.items)
    if total < MIN_RAP:
        raise HTTPException(400, f"Минимальная сумма пополнения — {MIN_RAP} RAP")
    evidence = await ev.validate(db, payload.evidence, staff["id"], dep_id, "intake")
    try:
        plan = await plan_deposit(db, dep, total)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    previous = dep.get("staff_report_version")
    report = {
        "id": str(uuid.uuid4()), "kind": "intake", "deposit_id": dep_id, "version": (previous or 0) + 1,
        "staff_id": staff["id"], "staff_nick": staff.get("nickname"), "receiver": dep.get("staff_receiver") or receiver(staff),
        "player": player(dep), "items": items, "items_count": count, "total_rap": total,
        "promo_code": dep.get("promo_code"), "promo_bonus": float(dep.get("promo_bonus") or 0), "plan": plan,
        "evidence": evidence, "checks": {"received": True, "value_checked": True}, "note": payload.note.strip(),
        "status": "submitted", "decision": None, "created_at": now(),
    }
    await db.staff_reports.insert_one(dict(report))
    res = await db.deposits.update_one(
        {"id": dep_id, "staff_id": staff["id"], "status": "pending", "staff_state": dep["staff_state"], "staff_report_version": previous},
        {"$set": {"staff_state": "review", "staff_report_id": report["id"], "staff_report_version": report["version"],
                  "transfer_started_at": dep.get("transfer_started_at") or now()},
         "$min": {"first_submitted_at": report["created_at"]}})
    if not res.modified_count:
        await db.staff_reports.delete_one({"id": report["id"]})
        raise HTTPException(409, "Заявка изменилась. Обновите страницу")
    await audit(db, f"staff:{staff['id']}", "report_submit", staff["id"], dep_id, {"report_id": report["id"], "version": report["version"], "total_rap": total})
    return report


async def current_report(db, report_id):
    rep = await db.staff_reports.find_one({"id": report_id}, {"_id": 0})
    if not rep:
        raise HTTPException(404, "Отчёт не найден")
    return rep


async def _finalize_approval(db, rep, dep, actor, via):
    res = await db.staff_reports.update_one({"id": rep["id"], "status": "submitted"}, {"$set": {
        "status": "approved", "credited": dep.get("credited"), "decision": {"action": "approve", "by": actor, "via": via, "at": now()}}})
    await db.deposits.update_one({"id": dep["id"]}, {"$set": {"staff_state": "approved", "approved_at": now()}})
    if res.modified_count:
        await audit(db, actor, "report_approve", rep["staff_id"], dep["id"], {"report_id": rep["id"], "via": via, "credited": dep.get("credited")})
        credited = float(dep.get("credited") or 0)
        await _tell_player(db, dep, "system", lambda lang: tr("deposit_confirmed", lang, credited=credited))
    return res.modified_count > 0


async def approve(db, report_id, actor, via):
    rep = await current_report(db, report_id)
    if rep["status"] == "approved":
        return {"ok": True, "already": True, "report": rep}
    if rep["status"] != "submitted":
        raise HTTPException(409, "Эта версия отчёта уже не актуальна")
    dep = await db.deposits.find_one({"id": rep["deposit_id"]}, {"_id": 0})
    if not dep or dep.get("staff_report_id") != report_id:
        raise HTTPException(409, "Эта версия отчёта уже не актуальна")
    if dep["status"] == "pending":
        plan = {**rep["plan"], "issued_skins": [{**item, "uid": str(uuid.uuid4()), "deposit_id": dep["id"]} for item in rep["plan"]["issued_skins"]]}
        dep = await db.deposits.find_one_and_update(
            {"id": dep["id"], "status": "pending", "staff_state": "review", "staff_report_id": report_id},
            {"$set": {**plan, "status": "processing", "staff_state": "approving", "planned_at": now(),
                      "note": f"Отчёт сотрудника v{rep['version']} · {via}"}},
            return_document=ReturnDocument.AFTER, projection={"_id": 0}) or await db.deposits.find_one({"id": dep["id"]}, {"_id": 0})
    if dep["status"] not in ("processing", "confirmed") or dep.get("staff_report_id") != report_id:
        raise HTTPException(409, "По заявке уже принято другое решение")
    if dep["status"] == "processing":
        await settle_deposit(db, dep)
        dep = await db.deposits.find_one({"id": dep["id"]}, {"_id": 0})
    first = await _finalize_approval(db, rep, dep, actor, via)
    return {"ok": True, "already": not first, "report": await current_report(db, report_id), "credited": dep.get("credited")}


async def decide(db, report_id, action, reason, actor, via):
    """action: 'revision' (back to staff) or 'reject' (skins must be returned to the player)."""
    reason = reason.strip()
    if not 3 <= len(reason) <= 500:
        raise HTTPException(400, "Укажите причину (3–500 символов)")
    rep = await current_report(db, report_id)
    if rep["status"] != "submitted":
        raise HTTPException(409, "Эта версия отчёта уже не актуальна")
    state = "revision" if action == "revision" else "return_required"
    dep = await db.deposits.find_one_and_update(
        {"id": rep["deposit_id"], "status": "pending", "staff_state": "review", "staff_report_id": report_id},
        {"$set": {"staff_state": state, "staff_reason": reason}}, return_document=ReturnDocument.AFTER, projection={"_id": 0})
    if not dep:
        raise HTTPException(409, "По заявке уже принято другое решение")
    await db.staff_reports.update_one({"id": report_id}, {"$set": {
        "status": "revision" if action == "revision" else "rejected",
        "decision": {"action": action, "reason": reason, "by": actor, "via": via, "at": now()}}})
    await audit(db, actor, f"report_{action}", rep["staff_id"], dep["id"], {"report_id": report_id, "reason": reason, "via": via})
    if action == "reject":
        await _tell_player(db, dep, "system", lambda lang: (
            f"Request rejected: {reason}. The staff member will return your skins." if lang == "en"
            else f"Заявка отклонена: {reason}. Сотрудник вернёт вам переданные скины."))
    return await current_report(db, report_id)


async def revision_after_reject(db, dep_id, reason, actor):
    reason = reason.strip()
    dep = await db.deposits.find_one_and_update(
        {"id": dep_id, "status": "pending", "staff_state": "return_required"},
        {"$set": {"staff_state": "revision", "staff_reason": reason}}, return_document=ReturnDocument.AFTER, projection={"_id": 0})
    if not dep:
        raise HTTPException(409, "Заявка не ожидает возврата")
    await audit(db, actor, "revision_after_reject", dep.get("staff_id"), dep_id, {"reason": reason})
    return dep


# ---------- real skins: returns and transfers ----------
def _move(kind, staff, items, count, value, evidence, note, **extra):
    return {"id": str(uuid.uuid4()), "kind": kind, "staff_id": staff["id"], "staff_nick": staff.get("nickname"), "items": items,
            "items_count": count, "value_total": value, "evidence": evidence, "note": note.strip(), "status": "pending",
            "created_at": now(), "decided_at": None, "decided_by": None, **extra}


async def submit_return(db, staff, dep_id, payload: ReturnIn):
    dep = await assigned(db, staff, dep_id)
    if dep["status"] != "pending" or dep.get("staff_state") != "return_required":
        raise HTTPException(409, "Заявка не ожидает возврата скинов")
    rep = await current_report(db, dep["staff_report_id"])
    evidence = await ev.validate(db, payload.evidence, staff["id"], dep_id, "return")
    move = _move("return", staff, rep["items"], rep["items_count"], rep["total_rap"], evidence, payload.note,
                 deposit_id=dep_id, report_id=rep["id"], player=rep["player"], reason=dep.get("staff_reason"))
    await db.staff_moves.insert_one(dict(move))
    res = await db.deposits.update_one({"id": dep_id, "status": "pending", "staff_state": "return_required"},
                                       {"$set": {"staff_state": "return_review", "return_move_id": move["id"]}})
    if not res.modified_count:
        await db.staff_moves.delete_one({"id": move["id"]})
        raise HTTPException(409, "Заявка изменилась. Обновите страницу")
    await audit(db, f"staff:{staff['id']}", "return_submit", staff["id"], dep_id, {"move_id": move["id"]})
    return move


async def submit_transfer(db, staff, payload: TransferIn):
    items, count, value = clean_items(payload.items)
    evidence = await ev.validate(db, payload.evidence, staff["id"], None, "transfer")
    move = _move("transfer", staff, items, count, value, evidence, payload.note)
    await db.staff_moves.insert_one(dict(move))
    await audit(db, f"staff:{staff['id']}", "transfer_submit", staff["id"], move["id"], {"items_count": count, "value": value})
    return move


async def decide_move(db, move_id, confirm: bool, reason, actor):
    status = "confirmed" if confirm else "declined"
    move = await db.staff_moves.find_one_and_update(
        {"id": move_id, "status": "pending"}, {"$set": {"status": status, "decided_at": now(), "decided_by": actor, "decline_reason": reason}},
        return_document=ReturnDocument.AFTER, projection={"_id": 0})
    if not move:
        raise HTTPException(409, "Уже обработано")
    if move["kind"] == "return":
        if confirm:
            dep = await db.deposits.find_one_and_update(
                {"id": move["deposit_id"], "staff_state": "return_review", "return_move_id": move_id},
                {"$set": {"status": "rejected", "staff_state": "returned", "rejection_reason": move.get("reason") or "Отклонено", "resolved_at": now()}},
                return_document=ReturnDocument.AFTER, projection={"_id": 0})
            if dep:
                await _tell_player(db, dep, "system", lambda lang: "Skins returned. The request is closed." if lang == "en"
                                   else "Скины возвращены. Заявка закрыта.")
        else:
            await db.deposits.update_one({"id": move["deposit_id"], "staff_state": "return_review", "return_move_id": move_id},
                                         {"$set": {"staff_state": "return_required"}, "$unset": {"return_move_id": ""}})
    await audit(db, actor, f"{move['kind']}_{status}", move["staff_id"], move_id, {"reason": reason})
    return move


# ---------- recovery / reset ----------
async def resume(db):
    """Finish approvals interrupted after crediting (settle_deposit itself is resumed by server startup)."""
    async for rep in db.staff_reports.find({"status": "submitted"}, {"_id": 0}):
        dep = await db.deposits.find_one({"id": rep["deposit_id"], "staff_report_id": rep["id"], "status": "confirmed"}, {"_id": 0})
        if dep:
            try:
                await _finalize_approval(db, rep, dep, "startup-recovery", "recovery")
            except Exception:
                logger.exception("Could not finalize staff report %s", rep["id"])


async def on_economy_reset(db, journal):
    """Keep staff journals and evidence; unfinished staff requests move to manual review, old buttons die."""
    async for dep in db.deposits.find({"staff_flow": True, "status": {"$in": ["pending", "processing"]}}, {"_id": 0}):
        await db.staff_manual.update_one({"_id": dep["id"]}, {"$setOnInsert": {
            "deposit": dep, "reset_id": journal["_id"], "status": "open", "created_at": now()}}, upsert=True)
        await db.staff_reports.update_many({"deposit_id": dep["id"], "status": "submitted"}, {"$set": {"status": "manual_review"}})
    await db.staff_tg_outbox.update_many({"status": "pending"}, {"$set": {"status": "cancelled"}})
    await audit(db, "economy_reset", "economy_reset", ref=str(journal["_id"]))
