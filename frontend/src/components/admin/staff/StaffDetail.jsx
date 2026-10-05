import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { adminStaffApi, errText, fmtDuration, fmtRap, StatePill } from "../../../lib/staff-api";
import StatsGrid from "../../staff/StatsGrid";
import { Btn, Card, fmtTime } from "../chat/ui";

const toLocalInput = (d) => (d ? new Date(new Date(d).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "");
const withZ = (d) => (typeof d === "string" && !/(Z|[+-]\d{2}:?\d{2})$/.test(d) ? `${d}Z` : d);

const ShiftRow = ({ s, onSaved }) => {
  const [edit, setEdit] = useState(false);
  const [start, setStart] = useState(toLocalInput(withZ(s.started_at)));
  const [end, setEnd] = useState(toLocalInput(withZ(s.ended_at)));
  const [reason, setReason] = useState("");
  const save = async () => {
    try { await adminStaffApi.editShift(s.id, { started_at: new Date(start).toISOString(), ended_at: new Date(end).toISOString(), reason }); toast.success("Смена исправлена"); setEdit(false); onSaved(); }
    catch (e) { toast.error(errText(e)); }
  };
  return (
    <div className="rounded-lg bg-white/[0.03] px-3 py-2 text-[12px] space-y-2" data-testid={`staff-shift-${s.id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span>{fmtTime(s.started_at)} → {s.ended_at ? fmtTime(s.ended_at) : "идёт"}</span>
        <b>{fmtDuration(s.worked_seconds)}</b>
        {s.paused_seconds > 0 && <span className="text-[#8e91a3]">пауз {fmtDuration(s.paused_seconds)}</span>}
        {s.gaps_count > 0 && <span className="text-[#ffcf5a]">без связи {fmtDuration(s.gaps_seconds)}</span>}
        {s.offline && <span className="text-[#ff9b9b]">сейчас нет связи</span>}
        {s.long && <span className="text-[#ff9b9b] font-bold">&gt; 12 ч — проверить</span>}
        {s.adjustments?.length > 0 && <span className="text-[#8e91a3]" title={s.adjustments.map((a) => a.reason).join("; ")}>исправлена ×{s.adjustments.length}</span>}
        <Btn size="sm" tone="ghost" className="ml-auto" onClick={() => setEdit((v) => !v)} data-testid={`staff-shift-edit-${s.id}`}>Исправить</Btn>
      </div>
      {edit && (
        <div className="flex flex-wrap items-center gap-2">
          <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className="h-8 rounded bg-white/[0.06] px-2" data-testid={`staff-shift-start-${s.id}`} />
          <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className="h-8 rounded bg-white/[0.06] px-2" data-testid={`staff-shift-end-${s.id}`} />
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Причина исправления" className="h-8 flex-1 min-w-[160px] rounded bg-white/[0.06] px-2" data-testid={`staff-shift-reason-${s.id}`} />
          <Btn size="sm" tone="primary" disabled={reason.trim().length < 3 || !start || !end} onClick={save} data-testid={`staff-shift-save-${s.id}`}>Сохранить</Btn>
        </div>
      )}
    </div>
  );
};

const SECTIONS = [["requests", "Заявки"], ["items", "Предметы"], ["moves", "Передачи/возвраты"], ["shifts", "Смены"]];

export default function StaffDetail({ staff, onChanged }) {
  const [period, setPeriod] = useState("today");
  const [range, setRange] = useState({ date_from: "", date_to: "" });
  const [data, setData] = useState(null);
  const [section, setSection] = useState("requests");
  const load = useCallback(() => {
    if (period === "range" && (!range.date_from || !range.date_to)) return;
    adminStaffApi.stats(staff.id, { period, ...(period === "range" ? range : {}) }).then(setData).catch((e) => toast.error(errText(e)));
  }, [staff.id, period, range]);
  useEffect(() => { load(); }, [load]);
  return (
    <Card title={`${staff.nickname} · @${staff.roblox_nick}`} testId="staff-detail" right={
      <div className="flex items-center gap-1">
        {[["today", "Сегодня"], ["range", "Период"], ["all", "Всё время"]].map(([k, l]) => (
          <button key={k} onClick={() => setPeriod(k)} className={`h-7 px-2.5 rounded-md text-[11px] font-bold ${period === k ? "bg-[#ffb000] text-black" : "text-[#8e91a3] hover:text-white"}`} data-testid={`staff-period-${k}`}>{l}</button>
        ))}
      </div>}>
      <div className="space-y-3">
        {period === "range" && (
          <div className="flex items-center gap-2 text-[12px]">
            <input type="date" value={range.date_from} onChange={(e) => setRange((r) => ({ ...r, date_from: e.target.value }))} className="h-8 rounded bg-white/[0.06] px-2" data-testid="staff-period-from" />
            <span>—</span>
            <input type="date" value={range.date_to} onChange={(e) => setRange((r) => ({ ...r, date_to: e.target.value }))} className="h-8 rounded bg-white/[0.06] px-2" data-testid="staff-period-to" />
            <span className="text-[#6b6f84]">дни по Asia/Qyzylorda</span>
          </div>
        )}
        {data && <StatsGrid stats={data.stats} onPick={setSection} testId="staff-detail-stats" />}
        {data?.days?.length > 0 && <div className="flex flex-wrap gap-1.5 text-[11px]" data-testid="staff-days">{data.days.map((d) => <span key={d.day} className="rounded bg-white/[0.05] px-2 py-1">{d.day}: {fmtDuration(d.worked_seconds)}</span>)}</div>}
        <div className="flex gap-1">{SECTIONS.map(([k, l]) => <button key={k} onClick={() => setSection(k)} className={`h-7 px-2.5 rounded-md text-[11px] font-bold ${section === k ? "bg-white/[0.12] text-white" : "text-[#8e91a3]"}`} data-testid={`staff-section-${k}`}>{l}</button>)}</div>
        {data && section === "requests" && (
          <div className="space-y-1.5" data-testid="staff-detail-requests">
            {data.active_requests.filter((d) => !d.staff_report_id).map((d) => <div key={d.id} className="flex items-center gap-2 text-[12px] rounded-lg bg-white/[0.03] px-3 py-2"><span className="flex-1">#{d.id.slice(0, 8)} · {d.nickname}</span><StatePill state={d.staff_state} /></div>)}
            {data.requests.map((r) => <div key={r.deposit_id} className="flex flex-wrap items-center gap-2 text-[12px] rounded-lg bg-white/[0.03] px-3 py-2"><span className="flex-1">#{r.deposit_id.slice(0, 8)} v{r.version} · {r.player.nickname}</span><span>{fmtRap(r.total_rap)} RAP{r.credited ? ` → ${fmtRap(r.credited)}` : ""}</span><StatePill state={r.status} /></div>)}
          </div>
        )}
        {data && section === "items" && (
          <div className="space-y-1 text-[12px]" data-testid="staff-detail-items">
            {data.items.map((i, n) => <div key={n} className="flex gap-2 rounded bg-white/[0.03] px-3 py-1.5"><span className="flex-1">{i.name} × {i.qty}</span><span>{fmtRap(i.value * i.qty)} RAP</span><span className="text-[#8e91a3]">#{i.deposit_id.slice(0, 8)}</span><StatePill state={i.status} /></div>)}
          </div>
        )}
        {data && section === "moves" && (
          <div className="space-y-1 text-[12px]" data-testid="staff-detail-moves">
            {data.moves.map((m) => <div key={m.id} className="flex gap-2 rounded bg-white/[0.03] px-3 py-1.5"><span className="flex-1">{m.kind === "return" ? "Возврат" : "Передача"} · {m.items_count} шт</span><span>{fmtRap(m.value_total)} RAP</span><StatePill state={m.status} /></div>)}
          </div>
        )}
        {data && section === "shifts" && <div className="space-y-1.5">{data.shifts.map((s) => <ShiftRow key={s.id} s={s} onSaved={() => { load(); onChanged(); }} />)}</div>}
      </div>
    </Card>
  );
}
