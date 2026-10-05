import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, RotateCcw, XCircle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../../ui/dialog";
import { adminStaffApi, errText, fmtRap, StatePill } from "../../../lib/staff-api";
import { EvidenceGallery } from "../../staff/EvidenceImage";
import { Btn, fmtTime } from "../chat/ui";

const Row = ({ label, children }) => <div className="flex gap-2 text-[13px]"><span className="text-[#8e91a3] w-36 shrink-0">{label}</span><span className="min-w-0 break-words">{children}</span></div>;

export default function ReportReviewDialog({ reportId, onClose, onDone }) {
  const [data, setData] = useState(null);
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setData(null); setReason(""); setConfirming(false);
    if (reportId) adminStaffApi.report(reportId).then(setData).catch((e) => toast.error(errText(e)));
  }, [reportId]);
  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); onDone(); onClose(); }
    catch (e) { toast.error(errText(e)); }
    finally { setBusy(false); }
  };
  const rep = data?.report;
  const plan = rep?.plan;
  const fee = rep ? rep.total_rap * 0.2 : 0;
  const live = rep?.status === "submitted";
  return (
    <Dialog open={Boolean(reportId)} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-[760px] max-h-[90vh] overflow-y-auto bg-[#13141a] border-white/[0.06] text-white" data-testid="staff-review-dialog">
        <DialogHeader>
          <DialogTitle>Отчёт по заявке {rep ? `#${rep.deposit_id.slice(0, 8)} · v${rep.version}` : ""}</DialogTitle>
          <DialogDescription className="text-[#8e91a3]">Зачисление выполняется строго по этой версии отчёта.</DialogDescription>
        </DialogHeader>
        {!rep ? <div className="h-40 animate-pulse bg-white/[0.04] rounded-xl" /> : (
          <div className="space-y-4">
            <div className="space-y-1">
              <Row label="Статус"><StatePill state={rep.status} testId="staff-review-status" /></Row>
              <Row label="Сотрудник">{rep.staff_nick} · приём на {rep.receiver.roblox_display_name} (@{rep.receiver.roblox_nick})</Row>
              <Row label="Игрок">{rep.player.nickname} · Discord {rep.player.discord_id}</Row>
              <Row label="Roblox игрока">{rep.player.roblox_display_name} (@{rep.player.roblox_nick}) <a className="text-[#60a5fa] underline" href={rep.player.roblox_link} target="_blank" rel="noopener noreferrer">профиль</a></Row>
              <Row label="Отправлен">{fmtTime(rep.created_at)}</Row>
            </div>
            <div className="rounded-xl bg-white/[0.04] p-3 space-y-1 text-[13px]" data-testid="staff-review-items">
              {rep.items.map((i, n) => <div key={n}>• {i.name} × {i.qty} — {fmtRap(i.value)} RAP{i.qty > 1 ? ` (= ${fmtRap(i.qty * i.value)})` : ""}</div>)}
            </div>
            <div className="space-y-1" data-testid="staff-review-totals">
              <Row label="Общая оценка"><b>{fmtRap(rep.total_rap)} RAP</b> ({rep.items_count} шт.)</Row>
              <Row label="Комиссия 20%">−{fmtRap(fee)} RAP</Row>
              <Row label="Промобонус">{rep.promo_code ? `${rep.promo_code} +${Math.round(rep.promo_bonus * 100)}% (+${fmtRap(plan.credited - (rep.total_rap - fee))} RAP)` : "нет"}</Row>
              <Row label="К выдаче"><b className="text-[#7ee2a8]" data-testid="staff-review-credited">{fmtRap(plan.credited)} RAP</b> = скины {plan.issued_skins.length} шт. на {fmtRap(plan.skins_total)} + баланс {fmtRap(plan.balance_credited)}</Row>
              <Row label="Виртуальные скины">{plan.issued_skins.map((s) => `${s.name} ${fmtRap(s.price)}`).join(", ") || "—"}</Row>
              <Row label="Отметки">✅ Скины получил · ✅ Стоимость проверил</Row>
              {rep.note && <Row label="Комментарий">{rep.note}</Row>}
              {rep.decision && <Row label="Решение">{rep.decision.action} · {rep.decision.reason || ""} · {rep.decision.via}</Row>}
            </div>
            <EvidenceGallery ids={rep.evidence} load={adminStaffApi.evidence} testId="staff-review-evidence" />
            {data.versions.length > 1 && <div className="text-[12px] text-[#8e91a3]">Версии: {data.versions.map((v) => `v${v.version} (${v.status})`).join(" · ")}</div>}
            {live && (
              <div className="space-y-2 border-t border-white/[0.06] pt-3">
                <textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} rows={2} placeholder="Причина (для доработки или отклонения)" className="w-full rounded-lg bg-white/[0.05] p-3 text-[13px] outline-none" data-testid="staff-review-reason" />
                <div className="flex flex-wrap gap-2">
                  {!confirming ? <Btn tone="success" disabled={busy} onClick={() => setConfirming(true)} data-testid="staff-review-approve"><Check size={15} /> Подтвердить</Btn>
                    : <Btn tone="success" disabled={busy} onClick={() => act(() => adminStaffApi.approve(rep.id), "Зачислено")} data-testid="staff-review-approve-confirm"><Check size={15} /> Да, зачислить {fmtRap(plan.credited)} RAP</Btn>}
                  <Btn tone="neutral" disabled={busy || reason.trim().length < 3} onClick={() => act(() => adminStaffApi.revision(rep.id, reason), "Отправлено на доработку")} data-testid="staff-review-revision"><RotateCcw size={14} /> На доработку</Btn>
                  <Btn tone="danger" disabled={busy || reason.trim().length < 3} onClick={() => act(() => adminStaffApi.reject(rep.id, reason), "Отклонено")} data-testid="staff-review-reject"><XCircle size={14} /> Отклонить</Btn>
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
