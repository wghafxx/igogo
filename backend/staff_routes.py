"""HTTP routes: /api/staff/* (staff cabinet), /api/admin/staff/* (owner), /api/staff-telegram/webhook."""
import hmac
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import Field

import admin_commands
import live_chat as chat
import staff_core as core
import staff_evidence as ev
import staff_shifts as shifts
import staff_stats as stats
import staff_telegram as stg

logger = logging.getLogger(__name__)


class MessageIn(core.Strict):
    text: str = Field(min_length=1, max_length=1000)


class DeclineIn(core.Strict):
    reason: str = Field(default="", max_length=500)


class RejectIn(core.Strict):
    deposit_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=300)


class ShiftEditIn(core.Strict):
    started_at: datetime
    ended_at: datetime
    reason: str = Field(min_length=3, max_length=500)


def _image(data, content_type):
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


def build_router(db, require_admin, token_user, bot: stg.StaffBot, app_url: str, notify_rejected=None) -> APIRouter:
    r = APIRouter(prefix="/api")

    async def require_staff(request: Request) -> dict:
        user = await token_user(request)
        if not user:
            raise HTTPException(401, "Не авторизован")
        staff = await db.staff.find_one({"session_id": user["session_id"], "active": True}, {"_id": 0})
        if not staff:
            raise HTTPException(403, "Нет доступа сотрудника")
        return staff

    async def admin_actor(request):
        sess = await require_admin(request)
        return f"owner:{sess['jti'][:8]}"

    async def after_decision(rep):
        await stg.mark_card(db, bot, rep["id"], stg.decision_suffix(rep))

    async def staff_summary(staff):
        reports, moves, rows = await stats.load(db, staff["id"])
        start, end = shifts.period_bounds("today")
        shift = await shifts.current(db, staff["id"])
        return {"today": stats.compute(reports, moves, rows, start, end), "shift": shifts.public(shift) if shift else None}

    # ---------- staff cabinet ----------
    @r.get("/staff/me")
    async def staff_me(request: Request):
        staff = await require_staff(request)
        return {"staff": staff, **await staff_summary(staff)}

    @r.get("/staff/queue")
    async def staff_queue(request: Request):
        await require_staff(request)
        rows = await core.queue(db)
        return [{k: d.get(k) for k in ("id", "nickname", "roblox_display_name", "roblox_nick", "roblox_link", "expected_rap", "created_at", "promo_code")} for d in rows]

    @r.post("/staff/requests/{dep_id}/claim")
    async def staff_claim(dep_id: str, request: Request):
        return await core.claim(db, await require_staff(request), dep_id)

    @r.get("/staff/requests")
    async def staff_requests(request: Request):
        return await core.my_requests(db, await require_staff(request))

    @r.get("/staff/requests/{dep_id}")
    async def staff_request(dep_id: str, request: Request):
        staff = await require_staff(request)
        dep = await core.assigned(db, staff, dep_id)
        reports = await db.staff_reports.find({"deposit_id": dep_id}, {"_id": 0, "tg_card": 0}).sort("version", -1).to_list(50)
        ret = await db.staff_moves.find({"deposit_id": dep_id}, {"_id": 0}).sort("created_at", -1).to_list(20)
        return {"deposit": dep, "reports": reports, "returns": ret}

    @r.get("/staff/requests/{dep_id}/messages")
    async def staff_messages(dep_id: str, request: Request, after: Optional[str] = None):
        dep = await core.assigned(db, await require_staff(request), dep_id)
        if not dep.get("chat_id"):
            return []
        return await chat.messages(db, dep["chat_id"], after)

    @r.post("/staff/requests/{dep_id}/messages", status_code=201)
    async def staff_send(dep_id: str, payload: MessageIn, request: Request):
        staff = await require_staff(request)
        dep = await core.assigned(db, staff, dep_id)
        if dep["status"] != "pending":
            raise HTTPException(409, "Заявка закрыта")
        found = await db.chats.find_one({"id": dep.get("chat_id")}, {"_id": 0})
        if not found:
            raise HTTPException(404, "Чат не найден")
        return await chat.post_message(db, found, "admin", payload.text, {"staff_id": staff["id"], "staff_nick": staff.get("nickname")})

    @r.get("/staff/requests/{dep_id}/attachments/{attachment_id}")
    async def staff_chat_attachment(dep_id: str, attachment_id: str, request: Request):
        dep = await core.assigned(db, await require_staff(request), dep_id)
        doc = await db.chat_attachments.find_one({"id": attachment_id, "chat_id": dep.get("chat_id")})
        if not doc:
            raise HTTPException(404, "Файл не найден")
        return _image(bytes(doc["data"]), doc["content_type"])

    @r.post("/staff/requests/{dep_id}/transfer-started")
    async def staff_transfer_started(dep_id: str, request: Request):
        return await core.mark_transfer_started(db, await require_staff(request), dep_id)

    @r.post("/staff/evidence", status_code=201)
    async def staff_upload(request: Request, file: UploadFile = File(...), purpose: str = Form(...), deposit_id: Optional[str] = Form(None)):
        staff = await require_staff(request)
        if purpose == "transfer":
            deposit_id = None
        else:
            dep = await core.assigned(db, staff, deposit_id or "")
            if dep["status"] != "pending":
                raise HTTPException(409, "Заявка закрыта")
        return await ev.save(db, staff["id"], deposit_id, purpose, file)

    @r.get("/staff/evidence/{file_id}")
    async def staff_evidence(file_id: str, request: Request):
        staff = await require_staff(request)
        data, meta = await ev.read(db, file_id)
        if meta.get("staff_id") != staff["id"]:
            raise HTTPException(404, "Файл не найден")
        return _image(data, meta["content_type"])

    @r.post("/staff/requests/{dep_id}/report", status_code=201)
    async def staff_report(dep_id: str, payload: core.ReportIn, request: Request):
        staff = await require_staff(request)
        rep = await core.submit_report(db, staff, dep_id, payload)
        await stg.enqueue(db, bot, rep)
        return rep

    @r.post("/staff/requests/{dep_id}/return", status_code=201)
    async def staff_return(dep_id: str, payload: core.ReturnIn, request: Request):
        return await core.submit_return(db, await require_staff(request), dep_id, payload)

    @r.get("/staff/transfers")
    async def staff_transfers(request: Request):
        await require_staff(request)
        return []

    # ---------- staff chat console (same as the owner's chats, without withdrawals) ----------
    async def owner_card(found):
        if str(found.get("owner", "")).startswith("guest:"):
            return None
        u = await db.users.find_one({"session_id": found["owner"]}, {"_id": 0, "session_id": 1, "nickname": 1, "discord_id": 1, "roblox_nick": 1,
                                                                      "roblox_display_name": 1, "roblox_link": 1, "balance": 1, "skins.price": 1,
                                                                      "promo_code": 1, "promo_bonus": 1, "created_at": 1})
        if not u:
            return None
        skins = u.pop("skins", []) or []
        return {**u, "balance": float(u.get("balance") or 0), "skins_count": len(skins), "skins_total": round(sum(float(s.get("price") or 0) for s in skins), 2)}

    @r.get("/staff/chats")
    async def staff_chats(request: Request, status: str = "open", q: Optional[str] = None, offset: int = 0, limit: int = 100):
        staff = await require_staff(request)
        return await chat.admin_list(db, status, q, max(0, offset), min(200, max(1, limit)), scope=core.chat_scope(staff))

    @r.get("/staff/chats/summary")
    async def staff_chats_summary(request: Request):
        return await chat.admin_summary(db, scope=core.chat_scope(await require_staff(request)))

    @r.get("/staff/commands")
    async def staff_commands(request: Request):
        await require_staff(request)
        return await admin_commands.list_commands(db)

    @r.get("/staff/chats/{chat_id}/messages")
    async def staff_chat_detail(chat_id: str, request: Request):
        staff = await require_staff(request)
        found = await core.visible_chat(db, staff, chat_id)
        mine = found.get("staff_id") == staff["id"]
        if mine:
            await chat.mark_read(db, chat_id, "admin")
        rows = await chat.messages(db, chat_id)
        user = await owner_card(found)
        found = (await chat.enrich_chats(db, [found]))[0]
        if user:
            user["online"] = found["online"]
        dep = await core.chat_deposit(db, staff, found) if mine and user else None
        reports = await db.staff_reports.find({"deposit_id": dep["id"]}, {"_id": 0, "tg_card": 0}).sort("version", -1).to_list(20) if dep else []
        withdrawals, payments = [], []
        if user:
            # Read-only for staff: they explain the process and call the owner; actions stay owner-only.
            withdrawals = await db.withdrawals.find({"session_id": found["owner"], "status": {"$in": ["pending", "cancelling", "paying"]}},
                                                    {"_id": 0, "id": 1, "item": 1, "status": 1, "created_at": 1, "recipient": 1}).sort("created_at", 1).to_list(100)
            payments = await db.deposits.find({"session_id": found["owner"], "status": {"$in": ["pending", "processing"]}, "payment_method": {"$ne": None}},
                                              {"_id": 0, "id": 1, "payment_method": 1, "status": 1, "declared_amount": 1, "declared_currency": 1,
                                               "da_code": 1, "paid_claimed_at": 1, "created_at": 1}).sort("created_at", 1).to_list(20)
        return {"chat": {**found, "admin_unread": 0 if mine else found.get("admin_unread", 0)}, "messages": rows, "user": user,
                "mine": mine, "deposit": dep, "reports": reports, "withdrawals": withdrawals, "payments": payments,
                "withdrawals_total": round(sum(float((w.get("item") or {}).get("price") or 0) for w in withdrawals), 2)}

    @r.post("/staff/chats/{chat_id}/accept")
    async def staff_chat_accept(chat_id: str, request: Request):
        return await core.take_chat(db, await require_staff(request), chat_id)

    @r.post("/staff/chats/{chat_id}/messages", status_code=201)
    async def staff_chat_send(chat_id: str, payload: MessageIn, request: Request):
        staff = await require_staff(request)
        found = await core.visible_chat(db, staff, chat_id)
        if found.get("staff_id") != staff["id"]:
            found = await core.take_chat(db, staff, chat_id)
        elif found["status"] != "active":
            found = await chat.accept(db, chat_id, staff.get("nickname") or "staff")
        text = await admin_commands.expand(db, payload.text)
        return await chat.post_message(db, found, "admin", text, {"staff_id": staff["id"], "staff_nick": staff.get("nickname")})

    @r.post("/staff/chats/{chat_id}/close")
    async def staff_chat_close(chat_id: str, request: Request):
        staff = await require_staff(request)
        found = await core.visible_chat(db, staff, chat_id)
        if found.get("staff_id") != staff["id"]:
            raise HTTPException(409, "Сначала примите чат")
        return await chat.close(db, chat_id)

    @r.get("/staff/chats/{chat_id}/attachments/{attachment_id}")
    async def staff_chat_file(chat_id: str, attachment_id: str, request: Request):
        await core.visible_chat(db, await require_staff(request), chat_id)
        doc = await db.chat_attachments.find_one({"id": attachment_id, "chat_id": chat_id})
        if not doc:
            raise HTTPException(404, "Файл не найден")
        return _image(bytes(doc["data"]), doc["content_type"])

    @r.post("/staff/chats/{chat_id}/evidence", status_code=201)
    async def staff_chat_evidence(chat_id: str, request: Request, file: UploadFile = File(...), purpose: str = Form("intake")):
        staff = await require_staff(request)
        found = await core.visible_chat(db, staff, chat_id)
        dep = await core.chat_deposit(db, staff, found, create=purpose == "intake")
        if not dep or dep["status"] != "pending":
            raise HTTPException(409, "Нет открытой заявки в этом чате")
        return {**await ev.save(db, staff["id"], dep["id"], purpose, file), "deposit_id": dep["id"]}

    @r.post("/staff/chats/{chat_id}/report", status_code=201)
    async def staff_chat_report(chat_id: str, payload: core.ReportIn, request: Request):
        staff = await require_staff(request)
        dep = await core.chat_deposit(db, staff, await core.visible_chat(db, staff, chat_id), create=True)
        rep = await core.submit_report(db, staff, dep["id"], payload)
        await stg.enqueue(db, bot, rep)
        return rep

    @r.post("/staff/chats/{chat_id}/reject")
    async def staff_chat_reject(chat_id: str, payload: RejectIn, request: Request):
        staff = await require_staff(request)
        found = await core.visible_chat(db, staff, chat_id)
        if found.get("staff_id") != staff["id"]:
            raise HTTPException(409, "Сначала примите чат")
        dep = await core.reject_request(db, staff, found, payload.deposit_id, payload.reason)
        if notify_rejected:
            await notify_rejected(dep, payload.reason)
        return {"ok": True}

    @r.post("/staff/chats/{chat_id}/return", status_code=201)
    async def staff_chat_return(chat_id: str, payload: core.ReturnIn, request: Request):
        staff = await require_staff(request)
        dep = await core.chat_deposit(db, staff, await core.visible_chat(db, staff, chat_id))
        if not dep:
            raise HTTPException(409, "Нет заявки для возврата")
        return await core.submit_return(db, staff, dep["id"], payload)

    @r.get("/staff/shift")
    async def staff_shift(request: Request):
        staff = await require_staff(request)
        shift = await shifts.current(db, staff["id"])
        return shifts.public(shift) if shift else None

    @r.post("/staff/shift/{action}")
    async def staff_shift_action(action: str, request: Request):
        staff = await require_staff(request)
        fn = {"start": shifts.start, "pause": shifts.pause, "resume": shifts.resume, "end": shifts.end, "heartbeat": shifts.heartbeat}.get(action)
        if not fn:
            raise HTTPException(404, "Неизвестное действие")
        result = await fn(db, staff["id"])
        if action != "heartbeat":
            await core.audit(db, f"staff:{staff['id']}", f"shift_{action}", staff["id"], (result or {}).get("id"))
        return result

    @r.get("/staff/stats")
    async def staff_stats(request: Request, period: str = "today", date_from: Optional[str] = None, date_to: Optional[str] = None):
        staff = await require_staff(request)
        start, end = shifts.period_bounds(period, date_from, date_to)
        reports, moves, rows = await stats.load(db, staff["id"])
        return {"stats": stats.compute(reports, moves, rows, start, end), "days": stats.by_day(rows, start, end)}

    # ---------- owner ----------
    @r.get("/admin/staff")
    async def admin_staff(request: Request):
        await require_admin(request)
        rows = await db.staff.find({}, {"_id": 0}).sort("created_at", 1).to_list(200)
        return [{**s, **await staff_summary(s)} for s in rows]

    @r.post("/admin/staff", status_code=201)
    async def admin_staff_create(payload: core.StaffIn, request: Request):
        return await core.create_staff(db, payload, await admin_actor(request))

    @r.put("/admin/staff/{staff_id}")
    async def admin_staff_update(staff_id: str, payload: core.StaffUpdateIn, request: Request):
        return await core.update_staff(db, staff_id, payload, await admin_actor(request))

    @r.post("/admin/staff/{staff_id}/disable")
    async def admin_staff_disable(staff_id: str, request: Request):
        doc = await core.set_active(db, staff_id, False, await admin_actor(request))
        await shifts.close_any(db, staff_id)
        return doc

    @r.post("/admin/staff/{staff_id}/enable")
    async def admin_staff_enable(staff_id: str, request: Request):
        return await core.set_active(db, staff_id, True, await admin_actor(request))

    @r.get("/admin/staff/{staff_id}/stats")
    async def admin_staff_stats(staff_id: str, request: Request, period: str = "today", date_from: Optional[str] = None, date_to: Optional[str] = None):
        await require_admin(request)
        start, end = shifts.period_bounds(period, date_from, date_to)
        reports, moves, rows = await stats.load(db, staff_id)
        detail = stats.details(reports, moves, rows, start, end)
        wanted = set(detail.pop("shift_ids"))
        detail["shifts"] = [shifts.public(s) for s in rows if s["id"] in wanted]
        active = await db.deposits.find({"staff_id": staff_id, "status": {"$in": ["pending", "processing"]}}, {"_id": 0}).to_list(200)
        return {"stats": stats.compute(reports, moves, rows, start, end), **detail, "active_requests": active}

    @r.get("/admin/staff-reviews")
    async def admin_reviews(request: Request):
        await require_admin(request)
        reports = await db.staff_reports.find({"status": "submitted"}, {"_id": 0}).sort("created_at", 1).to_list(200)
        moves = await db.staff_moves.find({"status": "pending"}, {"_id": 0}).sort("created_at", 1).to_list(200)
        returns_due = await db.deposits.find({"staff_state": "return_required", "status": "pending"}, {"_id": 0}).to_list(200)
        manual = await db.staff_manual.find({"status": "open"}, {"_id": 0, "deposit": 1, "created_at": 1}).to_list(200)
        outbox = await db.staff_tg_outbox.count_documents({"status": "pending"})
        return {"reports": reports, "moves": moves, "returns_due": returns_due, "manual": manual, "outbox_pending": outbox}

    @r.get("/admin/staff-reports/{report_id}")
    async def admin_report(report_id: str, request: Request):
        await require_admin(request)
        rep = await core.current_report(db, report_id)
        versions = await db.staff_reports.find({"deposit_id": rep["deposit_id"]}, {"_id": 0}).sort("version", -1).to_list(50)
        dep = await db.deposits.find_one({"id": rep["deposit_id"]}, {"_id": 0, "status": 1, "staff_state": 1, "staff_report_id": 1})
        return {"report": rep, "versions": versions, "deposit": dep}

    @r.post("/admin/staff-reports/{report_id}/approve")
    async def admin_report_approve(report_id: str, request: Request):
        result = await core.approve(db, report_id, await admin_actor(request), "admin")
        await after_decision(result["report"])
        return result

    @r.post("/admin/staff-reports/{report_id}/revision")
    async def admin_report_revision(report_id: str, payload: core.ReasonIn, request: Request):
        rep = await core.decide(db, report_id, "revision", payload.reason, await admin_actor(request), "admin")
        await after_decision(rep)
        return rep

    @r.post("/admin/staff-reports/{report_id}/reject")
    async def admin_report_reject(report_id: str, payload: core.ReasonIn, request: Request):
        rep = await core.decide(db, report_id, "reject", payload.reason, await admin_actor(request), "admin")
        await after_decision(rep)
        return rep

    @r.post("/admin/staff-requests/{dep_id}/revision")
    async def admin_revision_after_reject(dep_id: str, payload: core.ReasonIn, request: Request):
        return await core.revision_after_reject(db, dep_id, payload.reason, await admin_actor(request))

    @r.post("/admin/staff-moves/{move_id}/confirm")
    async def admin_move_confirm(move_id: str, request: Request):
        return await core.decide_move(db, move_id, True, None, await admin_actor(request))

    @r.post("/admin/staff-moves/{move_id}/decline")
    async def admin_move_decline(move_id: str, payload: DeclineIn, request: Request):
        return await core.decide_move(db, move_id, False, payload.reason.strip() or None, await admin_actor(request))

    @r.get("/admin/staff-evidence/{file_id}")
    async def admin_evidence(file_id: str, request: Request):
        await require_admin(request)
        data, meta = await ev.read(db, file_id)
        return _image(data, meta["content_type"])

    @r.put("/admin/staff-shifts/{shift_id}")
    async def admin_shift_edit(shift_id: str, payload: ShiftEditIn, request: Request):
        actor = await admin_actor(request)
        shift = await shifts.edit(db, shift_id, payload.started_at, payload.ended_at, payload.reason, actor)
        await core.audit(db, actor, "shift_edit", shift["staff_id"], shift_id, {"reason": payload.reason})
        return shift

    @r.post("/admin/staff-manual/{dep_id}/resolve")
    async def admin_manual_resolve(dep_id: str, payload: DeclineIn, request: Request):
        actor = await admin_actor(request)
        res = await db.staff_manual.update_one({"_id": dep_id, "status": "open"}, {"$set": {"status": "resolved", "resolved_by": actor, "note": payload.reason, "resolved_at": core.now()}})
        if not res.modified_count:
            raise HTTPException(409, "Уже разобрано")
        await core.audit(db, actor, "manual_resolve", ref=dep_id, details={"note": payload.reason})
        return {"ok": True}

    @r.get("/admin/staff-audit")
    async def admin_staff_audit(request: Request, staff_id: Optional[str] = None):
        await require_admin(request)
        query = {"staff_id": staff_id} if staff_id else {}
        return await db.staff_audit.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)

    @r.get("/admin/staff-telegram")
    async def admin_staff_tg(request: Request):
        await require_admin(request)
        info = {}
        if bot.enabled:
            try:
                info = await bot.call("getWebhookInfo")
            except Exception:
                info = {}
        expected = f"{app_url}/api/{'telegram' if bot.shared else 'staff-telegram'}/webhook"
        return {"enabled": bot.enabled, "shared": bot.shared, "webhook_url": info.get("url"), "expected_url": expected, "connected": info.get("url") == expected,
                "last_error": info.get("last_error_message"), "outbox_pending": await db.staff_tg_outbox.count_documents({"status": "pending"}),
                "outbox_failed": await db.staff_tg_outbox.count_documents({"status": "failed"})}

    @r.post("/admin/staff-telegram/setup")
    async def admin_staff_tg_setup(request: Request):
        await require_admin(request)
        if not bot.enabled:
            raise HTTPException(409, "Не заданы STAFF_TG_BOT_TOKEN / STAFF_TG_OWNER_ID / STAFF_TG_WEBHOOK_SECRET")
        if bot.shared:
            raise HTTPException(409, "Токен совпадает с ботом DonationAlerts: подключите его кнопкой «Подключить бота» во вкладке Чаты")
        try:
            url = await stg.setup_webhook(bot, app_url)
        except Exception as error:
            raise HTTPException(409, f"Telegram: {error}") from None
        return {"ok": True, "webhook_url": url}

    @r.post("/admin/staff-telegram/test")
    async def admin_staff_tg_test(request: Request):
        await require_admin(request)
        if not bot.enabled:
            raise HTTPException(409, "Бот проверки не настроен")
        try:
            await stg.send_test(bot)
        except Exception as error:
            raise HTTPException(409, f"Telegram: {error}. Откройте бота и нажмите /start") from None
        return {"ok": True}

    @r.post("/staff-telegram/webhook")
    async def staff_tg_webhook(request: Request):
        if not bot.enabled or bot.shared or not hmac.compare_digest(request.headers.get("x-telegram-bot-api-secret-token", ""), bot.secret):
            raise HTTPException(403, "Forbidden")
        try:
            await stg.handle_update(db, bot, await request.json())
        except Exception:
            logger.exception("Staff Telegram update failed")
        return {"ok": True}

    return r
