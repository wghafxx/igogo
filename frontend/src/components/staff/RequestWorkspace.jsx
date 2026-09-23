import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, Play } from "lucide-react";
import { staffApi, errText, fmtRap, StatePill } from "../../lib/staff-api";
import { Btn, Card, fmtTime } from "../admin/chat/ui";
import StaffChat from "./StaffChat";
import ReportForm from "./ReportForm";
import EvidenceUploader from "./EvidenceUploader";
import { EvidenceGallery } from "./EvidenceImage";

const ReturnForm = ({ dep, onDone }) => {
  const [evidence, setEvidence] = useState([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await staffApi.returnSkins(dep.id, { evidence, note }); toast.success("Подтверждение возврата отправлено владельцу"); onDone(); }
    catch (e) { toast.error(errText(e, "Не удалось отправить")); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-3" data-testid="return-form">
      <div className="m-note-err rounded-lg px-3 py-2 text-[12px]">Заявка отклонена: {dep.staff_reason}. Верните игроку полученные скины и приложите скриншоты возврата.</div>
      <EvidenceUploader value={evidence} onChange={setEvidence} purpose="return" depositId={dep.id} testId="return-evidence" />
      <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={2} placeholder="Комментарий" className="w-full rounded-lg bg-white/[0.05] p-3 text-[13px] outline-none" data-testid="return-note" />
      <Btn tone="primary" disabled={busy || !evidence.length} onClick={submit} data-testid="return-submit">Отправить подтверждение возврата</Btn>
    </div>
  );
};

const Versions = ({ reports }) => (
  <div className="space-y-2" data-testid="report-versions">
    {reports.map((r) => (
      <details key={r.id} className="rounded-xl bg-white/[0.03] p-3 text-[12px]" data-testid={`report-version-${r.version}`}>
        <summary className="flex items-center gap-2 cursor-pointer">
          <b>v{r.version}</b><StatePill state={r.status} /><span className="text-[#8e91a3]">{fmtRap(r.total_rap)} RAP · {r.items_count} шт · {fmtTime(r.created_at)}</span>
        </summary>
        <div className="mt-2 space-y-2">
          {r.items.map((i, n) => <div key={n}>{i.name} × {i.qty} — {fmtRap(i.value)} RAP</div>)}
          {r.decision?.reason && <div className="text-[#ffcf5a]">Причина: {r.decision.reason}</div>}
          <EvidenceGallery ids={r.evidence} load={staffApi.evidence} testId={`report-version-${r.version}-evidence`} />
        </div>
      </details>
    ))}
  </div>
);

export default function RequestWorkspace({ depId, onBack }) {
  const [data, setData] = useState(null);
  const load = useCallback(() => staffApi.request(depId).then(setData).catch((e) => toast.error(errText(e, "Заявка недоступна"))), [depId]);
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, [load]);
  if (!data) return <div className="blox-panel h-40 animate-pulse" />;
  const dep = data.deposit;
  const latest = data.reports[0];
  const state = dep.staff_state;
  const closed = dep.status !== "pending";
  const startTransfer = async () => {
    try { await staffApi.transferStarted(dep.id); toast.success("Отмечено: передача началась"); load(); }
    catch (e) { toast.error(errText(e)); }
  };
  return (
    <div className="space-y-4" data-testid="staff-workspace">
      <div className="flex flex-wrap items-center gap-3">
        <Btn tone="ghost" size="sm" onClick={onBack} data-testid="staff-workspace-back"><ArrowLeft size={14} /> Назад</Btn>
        <div className="text-[16px] font-black">Заявка #{dep.id.slice(0, 8)}</div>
        <StatePill state={closed ? dep.status : state} testId="staff-workspace-state" />
        {!closed && !dep.transfer_started_at && state === "assigned" && <Btn size="sm" tone="neutral" onClick={startTransfer} data-testid="staff-transfer-started"><Play size={13} /> Передача началась</Btn>}
      </div>
      <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-4">
        <StaffChat depId={dep.id} closed={closed} />
        <div className="space-y-4">
          <Card title="Отчёт о приёме" testId="staff-report-card">
            {["assigned", "revision"].includes(state) && !closed && <ReportForm key={latest?.id || "new"} dep={dep} previous={state === "revision" ? latest : null} onSubmitted={load} />}
            {state === "review" && <div className="text-[13px] text-[#ffcf5a]" data-testid="staff-report-waiting">Отчёт v{latest?.version} на проверке у владельца. Можно брать следующие заявки.</div>}
            {state === "return_required" && <ReturnForm dep={dep} onDone={load} />}
            {state === "return_review" && <div className="text-[13px] text-[#ff9b9b]">Подтверждение возврата на проверке у владельца.</div>}
            {closed && <div className="text-[13px] text-[#8e91a3]">Заявка закрыта: {dep.status === "confirmed" ? `зачислено ${fmtRap(dep.credited)} RAP` : dep.status}</div>}
          </Card>
          {data.reports.length > 0 && <Card title="Версии отчёта"><Versions reports={data.reports} /></Card>}
        </div>
      </div>
    </div>
  );
}
