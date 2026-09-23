import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Coffee, Play, Square, WifiOff } from "lucide-react";
import { staffApi, errText, fmtDuration } from "../../lib/staff-api";
import { Btn } from "../admin/chat/ui";

// Server keeps the time; the browser only renders a live counter from the last server snapshot.
export default function ShiftBar({ shift, onChange }) {
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [base, setBase] = useState(() => Date.now());
  useEffect(() => { setBase(Date.now()); }, [shift]);
  useEffect(() => { const t = setInterval(() => setTick((v) => v + 1), 1000); return () => clearInterval(t); }, []);
  const act = async (action) => {
    setBusy(true);
    try { onChange(await staffApi.shiftAction(action)); }
    catch (e) { toast.error(errText(e)); onChange(await staffApi.shift().catch(() => null)); }
    finally { setBusy(false); }
  };
  const running = shift?.status === "open";
  const live = shift ? shift.worked_seconds + (running ? Math.floor((Date.now() - base) / 1000) : 0) : 0;
  void tick;
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="shift-bar">
      <div className="text-[12px] text-[#8e91a3]">Смена:</div>
      <div className={`text-[14px] font-black tabular-nums ${running ? "text-[#7ee2a8]" : shift ? "text-[#ffcf5a]" : "text-[#8e91a3]"}`} data-testid="shift-timer">
        {shift ? fmtDuration(live) : "не начата"}{shift?.status === "paused" && " · пауза"}
      </div>
      {shift?.long && <span className="text-[11px] font-bold text-[#ff9b9b]" data-testid="shift-long-flag">более 12 ч</span>}
      {shift?.gaps_count > 0 && <span className="text-[11px] text-[#ffcf5a] inline-flex items-center gap-1" data-testid="shift-gaps"><WifiOff size={12} /> без связи {fmtDuration(shift.gaps_seconds)}</span>}
      {!shift && <Btn size="sm" tone="success" disabled={busy} onClick={() => act("start")} data-testid="shift-start"><Play size={13} /> Начать смену</Btn>}
      {running && <Btn size="sm" tone="neutral" disabled={busy} onClick={() => act("pause")} data-testid="shift-pause"><Coffee size={13} /> Пауза</Btn>}
      {shift?.status === "paused" && <Btn size="sm" tone="success" disabled={busy} onClick={() => act("resume")} data-testid="shift-resume"><Play size={13} /> Продолжить</Btn>}
      {shift && <Btn size="sm" tone="danger" disabled={busy} onClick={() => act("end").then(() => onChange(null))} data-testid="shift-end"><Square size={12} /> Закончить</Btn>}
    </div>
  );
}
