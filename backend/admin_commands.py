"""Shared, editable operator replies. Templates substitute literal arguments only."""
import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

DEFAULTS = {
    "nick": "Здравствуйте! Чтобы пополнить скины, вам нужно добавить в друзья в Roblox {nick} и зайти к нему в BloxStrike на трейд-плазу. Киньте ему трейд и ждите принятия трейда.\n\nВсе заявки обрабатываются в порядке очереди. Наберитесь терпения, прежде чем снова писать нам.",
    "donat": "Здравствуйте! Чтобы пополнить баланс удобной вам валютой, перейдите по ссылке https://www.donationalerts.com/r/bloxgrade и задонатьте ровно ту сумму, которую хотите зачислить на сайт. Мы лично зачислим её вам в монетах.",
}
ARGUMENT = re.compile(r"\{(?:nick|args)\}")


def now():
    return datetime.now(timezone.utc)


def public(row):
    return {k: row[k] for k in ("id", "command", "text")}


async def ensure_commands(db):
    await db.admin_commands.create_index("id", unique=True)
    await db.admin_commands.create_index("command", unique=True, partialFilterExpression={"deleted": False})
    for name, text in DEFAULTS.items():
        try:
            # Stable IDs and tombstones preserve edits, renames and deletions on restart.
            await db.admin_commands.update_one({"id": f"default-{name}"}, {"$setOnInsert": {
                "command": name, "text": text, "deleted": False, "created_at": now(),
            }}, upsert=True)
        except DuplicateKeyError:
            pass  # A custom command already owns this name.


async def list_commands(db):
    return [public(r) for r in await db.admin_commands.find({"deleted": False}).sort("command", 1).to_list(None)]


async def save_command(db, command, text, admin, command_id=None):
    changes = {"command": command, "text": text, "updated_at": now(), "updated_by": admin}
    try:
        if command_id:
            row = await db.admin_commands.find_one_and_update(
                {"id": command_id, "deleted": False}, {"$set": changes}, return_document=ReturnDocument.AFTER)
            if not row:
                raise HTTPException(404, "Команда не найдена")
        else:
            row = {"id": str(uuid.uuid4()), "deleted": False, "created_at": now(), **changes}
            await db.admin_commands.insert_one(dict(row))
    except DuplicateKeyError:
        raise HTTPException(409, "Команда с таким названием уже существует")
    return public(row)


async def delete_command(db, command_id, admin):
    result = await db.admin_commands.update_one({"id": command_id, "deleted": False}, {"$set": {
        "deleted": True, "updated_at": now(), "updated_by": admin,
    }})
    if not result.matched_count:
        raise HTTPException(404, "Команда не найдена")
    return {"ok": True}


async def expand(db, text):
    text = text.strip()
    if not text:
        raise HTTPException(400, "Пустое сообщение")
    if not text.startswith("/"):
        return text
    parts = text[1:].split(maxsplit=1)
    name = parts[0].lower() if parts else ""
    row = await db.admin_commands.find_one({"command": name, "deleted": False})
    if not row:
        raise HTTPException(400, "Команда не найдена. Выберите или создайте её в разделе «Быстрые команды»")
    args = parts[1].strip() if len(parts) > 1 else ""
    needs_args = bool(ARGUMENT.search(row["text"]))
    if needs_args and not args:
        raise HTTPException(400, f"После /{name} укажите {'ник' if '{nick}' in row['text'] else 'текст'}")
    if args and not needs_args:
        raise HTTPException(400, f"Команда /{name} используется без дополнительного текста")
    result = ARGUMENT.sub(lambda _: args, row["text"])
    if len(result) > 2000:
        raise HTTPException(400, "Ответ команды длиннее 2000 символов")
    return result
