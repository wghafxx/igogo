import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCheck, FileSearch, UserCog, Hourglass } from "lucide-react";
import { adminStaffApi, errText, fmtRap } from "../../../lib/staff-api";
import ReportReviewDialog from "../staff/ReportReviewDialog";
import { Btn, ago } from "./ui";

const STATE_TEXT = {
  assigned: "принимает скины — отчёт со скриншотом ещё не отправлен",
  revision: "дорабатывает отчёт после вашего замечания",
  return_required: "отчёт отклонён — сотрудник возвращает скины игроку",
  return_review: "прислал подтверждение возврата скинов (Админка → Сотрудники)",
  approving: "зачисление выполняется…",
};

const ReportSummary = ({ reportId, busy, onApprove, onOpen }) => {
  const [rep, setRep] = useState(null);
  const [confirming, setConfirming] = useState(false);
  useEffect(() => { adminStaffApi.report(reportId).then((d) => setRep(d.report)).catch((e) => toast.error(errText(e))); }, [reportId]);
  if (!rep) return <div className="h-16 rounded-lg bg-white/[0.04] animate-pulse" />;
  return (
    <div className="space-y-2" data-testid="admin-chat-staff-report">
      <div className="rounded-lg bg-black/30 p-2.5 text-[12px] space-y-1">
        <div className="flex justify-between"><span className="text-[#a4a7b8]">Получено скинов</span><b className="tabular-nums">{fmtRap(rep.total_rap)} RAP · {rep.items_count} шт.</b></div>
        <div className="flex justify-between"><span className="text-[#a4a7b8]">К зачислению</span><b className="text-[#7ee2a8] tabular-nums" data-testid="admin-chat-staff-credited">{fmtRap(rep.plan.credited)} RAP</b></div>
        <div className="text-[11px] text-[#8e91a3] truncate">{rep.items.map((i) => `${i.name} × ${i.qty}`).join(", ")}</div>
      </div>
      {!confirming
        ? <Btn tone="success" size="lg" className="w-full" disabled={busy} onClick={() => setConfirming(true)} data-testid="admin-chat-staff-approve"><CheckCheck size={16} /> Подтвердить и зачислить</Btn>
        : <Btn tone="success" size="lg" className="w-full" disabled={busy} onClick={() => onApprove(rep.id)} data-testid="admin-chat-staff-approve-confirm"><CheckCheck size={16} /> {busy ? "Зачисление…" : `Да, зачислить ${fmtRap(rep.plan.credited)} RAP`}</Btn>}
      <Btn tone="neutral" className="w-full" disabled={busy} onClick={() => onOpen(rep.id)} data-testid="admin-chat-staff-open-report"><FileSearch size={14} /> Открыть отчёт и скриншоты</Btn>
    </div>
  );
};

export default function StaffRequestCard({ dep, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(null);
  const run = async (fn, ok) => {
    if (busy) return;
    setBusy(true);
    try { await fn(); toast.success(ok); onChanged(); } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const inReview = dep.status === "pending" && dep.staff_state === "review" && dep.staff_report_id;
  const canTake = dep.status === "pending" && ["assigned", "revision"].includes(dep.staff_state);
  return (
    <div className="rounded-xl bg-[#4b9dff]/[0.08] border border-[#4b9dff]/25 p-3 space-y-2" data-testid={`admin-chat-staff-request-${dep.id}`}>
      <div className="flex items-center justify-between text-[12px] gap-2">
        <span className="font-bold text-[#a6ccff] inline-flex items-center gap-1.5 min-w-0"><UserCog size={13} className="shrink-0" /><span className="truncate">Заявку ведёт сотрудник {dep.staff_nick || ""}</span></span>
        <span className="text-[#8e91a3] shrink-0">{ago(dep.assigned_at || dep.created_at)} назад</span>
      </div>
      {inReview ? (
        <>
          <div className="text-[12px] text-[#ffcf5a] inline-flex items-center gap-1.5"><Hourglass size={12} /> Отчёт ждёт вашего подтверждения — игрок ждёт RAP</div>
          <ReportSummary key={dep.staff_report_id} reportId={dep.staff_report_id} busy={busy} onOpen={setOpen}
            onApprove={(id) => run(() => adminStaffApi.approve(id), "Отчёт подтверждён, RAP зачислен игроку")} />
        </>
      ) : (
        <div className="text-[12px] text-[#b4b7c7]" data-testid="admin-chat-staff-state">Сотрудник {STATE_TEXT[dep.status === "processing" ? "approving" : dep.staff_state] || "обрабатывает заявку"}</div>
      )}
      {canTake && <Btn tone="neutral" className="w-full" disabled={busy} onClick={() => run(() => adminStaffApi.takeover(dep.id), "Заявка ваша — пополните игрока ниже")} data-testid="admin-chat-staff-takeover"><UserCog size={14} /> Забрать заявку и пополнить самому</Btn>}
      <ReportReviewDialog reportId={open} onClose={() => setOpen(null)} onDone={onChanged} />
    </div>
  );
}
