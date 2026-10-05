import React, { useState } from "react";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";
import { adminStaffApi, errText, fmtDuration, fmtRap } from "../../../lib/staff-api";
import { Btn, Card, Field } from "../chat/ui";

const input = "h-10 w-full rounded-lg bg-white/[0.05] px-3 text-[13px] outline-none border border-transparent focus:border-white/15";

const AddStaff = ({ onDone }) => {
  const [form, setForm] = useState({ discord_id: "", roblox_display_name: "", roblox_nick: "", roblox_link: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    setBusy(true);
    try { await adminStaffApi.create(form); toast.success("Сотрудник добавлен"); setForm({ discord_id: "", roblox_display_name: "", roblox_nick: "", roblox_link: "" }); onDone(); }
    catch (e) { toast.error(errText(e, "Не удалось добавить")); }
    finally { setBusy(false); }
  };
  return (
    <Card title="Добавить сотрудника" icon={UserPlus} testId="staff-add-card">
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Discord ID (должен войти на сайт)"><input className={input} value={form.discord_id} onChange={set("discord_id")} data-testid="staff-add-discord" /></Field>
        <Field label="Roblox Display Name аккаунта приёма"><input className={input} value={form.roblox_display_name} onChange={set("roblox_display_name")} data-testid="staff-add-display" /></Field>
        <Field label="Roblox @username"><input className={input} value={form.roblox_nick} onChange={set("roblox_nick")} data-testid="staff-add-nick" /></Field>
        <Field label="Ссылка на профиль Roblox"><input className={input} value={form.roblox_link} onChange={set("roblox_link")} data-testid="staff-add-link" /></Field>
      </div>
      <Btn tone="primary" className="mt-3" disabled={busy || Object.values(form).some((v) => !v.trim())} onClick={submit} data-testid="staff-add-submit">Добавить</Btn>
    </Card>
  );
};

export default function StaffList({ rows, selected, onSelect, onChanged }) {
  const toggle = async (s) => {
    if (s.active && !window.confirm(`Отключить доступ ${s.nickname}? История сохранится.`)) return;
    try { await adminStaffApi.setActive(s.id, !s.active); toast.success(s.active ? "Доступ отключён" : "Доступ включён"); onChanged(); }
    catch (e) { toast.error(errText(e)); }
  };
  return (
    <div className="space-y-4">
      <Card title={`Сотрудники · ${rows.length}`} testId="staff-list">
        <div className="space-y-2">
          {rows.length === 0 && <div className="text-[12px] text-[#6b6f84]">Пока никого нет</div>}
          {rows.map((s) => (
            <div key={s.id} className={`rounded-xl px-3 py-2.5 flex flex-wrap items-center gap-2 text-[13px] cursor-pointer transition-colors ${selected === s.id ? "bg-white/[0.09]" : "bg-white/[0.03] hover:bg-white/[0.06]"}`} onClick={() => onSelect(s.id)} data-testid={`staff-row-${s.id}`}>
              <span className={`w-2 h-2 rounded-full ${s.shift?.status === "open" ? "bg-[#2ecc71]" : s.shift ? "bg-[#ffb000]" : "bg-[#5f6377]"}`} />
              <b className="w-32 truncate">{s.nickname}</b>
              <span className="text-[#8e91a3] flex-1 min-w-[120px] truncate">@{s.roblox_nick}</span>
              <span className="text-[12px]">сегодня {fmtDuration(s.today.worked_seconds)} · {s.today.processed} заяв.</span>
              <span className="text-[12px] text-[#7cc8ff]">у него {s.today.holdings.items} шт · {fmtRap(s.today.holdings.value)} RAP</span>
              {!s.active && <span className="text-[11px] font-bold text-[#ff9b9b]">отключён</span>}
              <Btn size="sm" tone={s.active ? "danger" : "success"} onClick={(e) => { e.stopPropagation(); toggle(s); }} data-testid={`staff-toggle-${s.id}`}>{s.active ? "Отключить" : "Включить"}</Btn>
            </div>
          ))}
        </div>
      </Card>
      <AddStaff onDone={onChanged} />
    </div>
  );
}
