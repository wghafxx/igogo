import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { adminApi } from "../../lib/api";
import { Btn, Field } from "./chat/ui";

const empty = { command: "", text: "" };

export default function QuickCommandsTab({ refreshKey }) {
  const [rows, setRows] = useState([]);
  const [draft, setDraft] = useState(empty);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    try { setRows(await adminApi.commands()); }
    catch { toast.error("Не удалось загрузить команды"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);
  const reset = () => { setDraft(empty); setEditing(null); };
  const name = draft.command.trim().replace(/^\//, "").toLowerCase();
  const valid = /^[a-z][a-z0-9_-]{0,31}$/.test(name) && draft.text.trim();
  const save = async (e) => {
    e.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    try {
      const payload = { command: name, text: draft.text.trim() };
      if (editing) await adminApi.updateCommand(editing, payload);
      else await adminApi.createCommand(payload);
      reset(); await load(); toast.success("Команда сохранена");
    } catch (err) { toast.error(err?.response?.data?.detail || "Не удалось сохранить команду"); }
    finally { setBusy(false); }
  };
  const remove = async (id) => {
    if (busy) return;
    setBusy(true);
    try {
      await adminApi.deleteCommand(id);
      if (editing === id) reset();
      setDeleting(null); await load(); toast.success("Команда удалена");
    } catch (err) { toast.error(err?.response?.data?.detail || "Не удалось удалить команду"); }
    finally { setBusy(false); }
  };
  return <div className="grid md:grid-cols-2 gap-4" data-testid="quick-commands-tab">
    <form onSubmit={save} className="blox-panel p-5 space-y-4 self-start">
      <h2 className="font-black">{editing ? "Редактировать команду" : "Новая команда"}</h2>
      <p className="text-[12px] text-[#a4a7b8]">Команды доступны всем админам в чате. Напишите /, выберите команду и отправьте готовый ответ.</p>
      <Field label="Название команды">
        <input aria-label="Название команды" value={draft.command} onChange={(e) => setDraft({ ...draft, command: e.target.value })} maxLength={33} disabled={busy} placeholder="/donat" className="w-full rounded-xl bg-white/[0.05] p-3 outline-none" />
        <span className="text-[11px] text-[#8e91a3]">Латинские буквы, цифры, _ и -. Начните с буквы.</span>
      </Field>
      <Field label="Текст ответа">
        <textarea aria-label="Текст ответа" value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} maxLength={2000} rows={8} disabled={busy} placeholder="Здравствуйте! Добавьте в друзья {nick}…" className="w-full rounded-xl bg-white/[0.05] p-3 outline-none resize-y text-[13px]" />
      </Field>
      <p className="text-[12px] text-[#a4a7b8]">Вставьте <code>{"{nick}"}</code> или <code>{"{args}"}</code>, чтобы подставлять текст после команды. Например, <code>/nick Builder</code> заменит <code>{"{nick}"}</code> на Builder. Без этих меток команда работает просто по названию.</p>
      <div className="flex gap-2"><Btn type="submit" tone="primary" disabled={busy || !valid}>Сохранить</Btn>{editing && <Btn disabled={busy} onClick={reset}>Отмена</Btn>}</div>
    </form>
    <div className="space-y-3">
      {loading && <p className="text-[#8e91a3]">Загрузка…</p>}
      {!loading && !rows.length && <p className="text-[#8e91a3]">Команд пока нет. Создайте первую.</p>}
      {rows.map((r) => <article key={r.id} className="blox-panel p-4 space-y-3">
        <div className="font-black text-[#ffcf5a]">/{r.command}</div>
        <p className="text-[13px] text-[#b4b7c7] whitespace-pre-wrap break-words">{r.text}</p>
        <div className="flex flex-wrap gap-2">
          <Btn size="sm" disabled={busy} onClick={() => { setEditing(r.id); setDraft({ command: r.command, text: r.text }); }}>Редактировать /{r.command}</Btn>
          {deleting === r.id ? <><Btn size="sm" tone="danger" disabled={busy} onClick={() => remove(r.id)}>Подтвердить удаление</Btn><Btn size="sm" disabled={busy} onClick={() => setDeleting(null)}>Отмена</Btn></> : <Btn size="sm" tone="danger" disabled={busy} onClick={() => setDeleting(r.id)}>Удалить /{r.command}</Btn>}
        </div>
      </article>)}
    </div>
  </div>;
}
