"""Durable intent protects against duplicate ACCEPT after a crash/restart."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid


class Journal:
    def __init__(self, config_path):
        self.path = Path(config_path).with_suffix(".state.json")

    def read(self):
        if not self.path.exists():
            return {}
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or not isinstance(state.get("pending"), bool):
                raise ValueError("некорректный формат")
            return state
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Журнал сделки повреждён: {self.path}. Автоматический запуск запрещён") from exc

    def ensure_clear(self):
        if self.read().get("pending"):
            raise RuntimeError("Есть незавершённый ACCEPT. Проверь результат в игре, закрой трейд и выполни python bot.py --resolve-pending с тем же --config")

    def write(self, data):
        temporary = self.path.with_name(self.path.name + f".{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def begin(self, nick, total, display_name=None):
        self.ensure_clear()
        self.write({"pending": True, "nick": nick, "display_name": display_name, "total": total,
                    "started_at": datetime.now(timezone.utc).isoformat()})

    def complete(self, result):
        state = self.read()
        state.update(pending=False, result=result, finished_at=datetime.now(timezone.utc).isoformat())
        self.write(state)