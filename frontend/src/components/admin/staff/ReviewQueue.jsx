import React, { useState } from "react";
import { toast } from "sonner";
import { adminStaffApi, errText, fmtRap, StatePill } from "../../../lib/staff-api";
import { EvidenceGallery } from "../../staff/EvidenceImage";
import { Btn, Card, ago } from "../chat/ui";
import ReportReviewDialog from "./ReportReviewDialog";

const MoveRow = ({ m, onDone }) => {
  const [busy, setBusy] = useState(false);
  const run = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); onDone(); } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-xl bg-white/[0.03] p-3 space-y-2 text-[13px]" data-testid={`staff-move-${m.id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <b>{m.kind === "return" ? "Возврат игроку" : "Передача вам"}</b>
        <span className="text-[#8e91a3]">{m.staff_nick} · {m.items_count} шт · {fmtRap(m.value_total)} RAP · {ago(m.created_at)}</span>
        {m.kind === "return" && <span className="text-[#8e91a3]">игрок {m.player?.nickname} (@{m.player?.roblox_nick})</span>}
      </div>
      <div className="text-[12px] text-[#b4b7c7]">{m.items.map((i) => `${i.name} × ${i.qty}`).join(", ")}{m.note ? ` · ${m.note}` : ""}</div>
      <EvidenceGallery ids={m.evidence} load={adminStaffApi.evidence} testId={`staff-move-${m.id}-evidence`} />
      <div className="flex gap-2">
        <Btn size="sm" tone="success" disabled={busy} onClick={() => run(() => adminStaffApi.confirmMove(m.id), "Подтверждено")} data-testid={`staff-move-confirm-${m.id}`}>Подтвердить</Btn>
        <Btn size="sm" tone="danger" disabled={busy} onClick={() => run(() => adminStaffApi.declineMove(m.id, ""), "Отклонено")} data-testid={`staff-move-decline-${m.id}`}>Не подтверждать</Btn>
      </div>
    </div>
  );
};

export default function ReviewQueue({ data, onChanged }) {
  const [open, setOpen] = useState(null);
  const revise = async (dep) => {
    const reason = window.prompt("Причина доработки вместо возврата");
    if (!reason || reason.trim().length < 3) return;
    try { await adminStaffApi.revisionAfterReject(dep.id, reason.trim()); toast.success("Отправлено на доработку"); onChanged(); }
    catch (e) { toast.error(errText(e)); }
  };
  const resolve = async (dep) => {
    const note = window.prompt("Как разобрано?") || "";
    try { await adminStaffApi.resolveManual(dep.id, note); toast.success("Отмечено"); onChanged(); } catch (e) { toast.error(errText(e)); }
  };
  if (!data) return <div className="blox-panel h-32 animate-pulse" />;
  return (
    <div className="grid lg:grid-cols-2 gap-4" data-testid="staff-review-queue">
      <Card title={`Отчёты на проверке · ${data.reports.length}`} right={data.outbox_pending ? <span className="text-[11px] text-[#ffcf5a]" data-testid="staff-outbox-pending">в очереди Telegram: {data.outbox_pending}</span> : null}>
        <div className="space-y-2">
          {data.reports.length === 0 && <div className="text-[12px] text-[#6b6f84]">Нет отчётов</div>}
          {data.reports.map((r) => (
            <button type="button" key={r.id} onClick={() => setOpen(r.id)} className="w-full text-left rounded-xl bg-white/[0.03] hover:bg-white/[0.07] transition-colors px-3 py-2.5 flex flex-wrap items-center gap-2 text-[13px]" data-testid={`staff-review-row-${r.id}`}>
              <b>#{r.deposit_id.slice(0, 8)} v{r.version}</b>
              <span className="text-[#8e91a3] flex-1 min-w-[140px] truncate">{r.staff_nick} → {r.player.nickname}</span>
              <span>{fmtRap(r.total_rap)} RAP → <b className="text-[#7ee2a8]">{fmtRap(r.plan.credited)}</b></span>
              <span className="text-[11px] text-[#ffcf5a]">{ago(r.created_at)}</span>
            </button>
          ))}
        </div>
      </Card>
      <Card title={`Передачи и возвраты · ${data.moves.length}`}>
        <div className="space-y-2">
          {data.moves.length === 0 && <div className="text-[12px] text-[#6b6f84]">Нет ожидающих</div>}
          {data.moves.map((m) => <MoveRow key={m.id} m={m} onDone={onChanged} />)}
        </div>
      </Card>
      {data.returns_due.length > 0 && (
        <Card title="Отклонены — ждут возврата скинов">
          <div className="space-y-2">
            {data.returns_due.map((d) => (
              <div key={d.id} className="flex flex-wrap items-center gap-2 text-[13px] rounded-xl bg-white/[0.03] px-3 py-2" data-testid={`staff-return-due-${d.id}`}>
                <span className="flex-1">#{d.id.slice(0, 8)} · {d.staff_nick} → {d.nickname} · {d.staff_reason}</span>
                <StatePill state={d.staff_state} />
                <Btn size="sm" tone="neutral" onClick={() => revise(d)} data-testid={`staff-return-revise-${d.id}`}>На доработку</Btn>
              </div>
            ))}
          </div>
        </Card>
      )}
      {data.manual.length > 0 && (
        <Card title="Ручной разбор после сброса экономики">
          <div className="space-y-2">
            {data.manual.map(({ deposit: d }) => (
              <div key={d.id} className="flex flex-wrap items-center gap-2 text-[13px] rounded-xl bg-white/[0.03] px-3 py-2" data-testid={`staff-manual-${d.id}`}>
                <span className="flex-1">#{d.id.slice(0, 8)} · {d.staff_nick} → {d.nickname} · {d.staff_state}</span>
                <Btn size="sm" tone="neutral" onClick={() => resolve(d)} data-testid={`staff-manual-resolve-${d.id}`}>Разобрано</Btn>
              </div>
            ))}
          </div>
        </Card>
      )}
      <ReportReviewDialog reportId={open} onClose={() => setOpen(null)} onDone={onChanged} />
    </div>
  );
}
