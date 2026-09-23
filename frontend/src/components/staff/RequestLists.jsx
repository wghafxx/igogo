import React from "react";
import { toast } from "sonner";
import { staffApi, errText, fmtRap, StatePill } from "../../lib/staff-api";
import { Btn, ago, fmtTime } from "../admin/chat/ui";

export const QueueList = ({ rows, onClaimed }) => {
  const claim = async (id) => {
    try { await staffApi.claim(id); toast.success("Заявка ваша"); onClaimed(id); }
    catch (e) { toast.error(errText(e, "Не удалось взять заявку")); onClaimed(null); }
  };
  return (
    <div className="space-y-2" data-testid="staff-queue">
      {rows.length === 0 && <div className="blox-panel h-32 flex items-center justify-center text-[13px] text-[#6b6f84]" data-testid="staff-queue-empty">Свободных заявок нет</div>}
      {rows.map((d) => (
        <div key={d.id} className="blox-panel px-4 py-3 flex flex-wrap items-center gap-3 text-[13px]" data-testid={`staff-queue-row-${d.id}`}>
          <b className="w-40 truncate">{d.nickname}</b>
          <span className="text-[#8e91a3] flex-1 min-w-[160px] truncate">{d.roblox_display_name} (@{d.roblox_nick})</span>
          <span>~{fmtRap(d.expected_rap)} RAP</span>
          <span className="text-[#ffcf5a] text-[12px]">ждёт {ago(d.created_at)}</span>
          <Btn tone="primary" size="sm" onClick={() => claim(d.id)} data-testid={`staff-claim-${d.id}`}>Взять в работу</Btn>
        </div>
      ))}
    </div>
  );
};

export const MineList = ({ data, onOpen }) => (
  <div className="space-y-2" data-testid="staff-mine">
    {data.active.length === 0 && <div className="blox-panel h-24 flex items-center justify-center text-[13px] text-[#6b6f84]">Нет заявок в работе</div>}
    {[...data.active, ...data.done].map((d) => (
      <button type="button" key={d.id} onClick={() => onOpen(d.id)} className="w-full blox-panel px-4 py-3 flex flex-wrap items-center gap-3 text-[13px] text-left hover:bg-white/[0.04] transition-colors" data-testid={`staff-mine-row-${d.id}`}>
        <b className="w-40 truncate">{d.nickname}</b>
        <span className="text-[#8e91a3] flex-1 min-w-[160px] truncate">@{d.roblox_nick} · #{d.id.slice(0, 8)}</span>
        {d.staff_report_version && <span className="text-[12px] text-[#8e91a3]">v{d.staff_report_version}</span>}
        <StatePill state={d.status === "pending" || d.status === "processing" ? d.staff_state : d.status} />
        <span className="text-[12px] text-[#6b6f84] w-28 text-right">{fmtTime(d.assigned_at || d.created_at)}</span>
      </button>
    ))}
  </div>
);
