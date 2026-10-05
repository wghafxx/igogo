import React from "react";
import { fmtDuration, fmtRap } from "../../lib/staff-api";

const Metric = ({ label, value, sub, onClick, testId, tone = "" }) => (
  <button type="button" onClick={onClick} disabled={!onClick} className={`text-left rounded-xl bg-white/[0.04] p-3 transition-colors enabled:hover:bg-white/[0.08] ${tone}`} data-testid={testId}>
    <div className="text-[11px] text-[#8e91a3] font-semibold">{label}</div>
    <div className="text-[18px] font-black mt-0.5">{value}</div>
    {sub && <div className="text-[11px] text-[#8e91a3] mt-0.5">{sub}</div>}
  </button>
);

// onPick(section) lets the owner drill into requests / items / moves / shifts.
export default function StatsGrid({ stats, onPick, testId = "staff-stats" }) {
  if (!stats) return null;
  const pick = (k) => (onPick ? () => onPick(k) : undefined);
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2" data-testid={testId}>
      <Metric label="Принято" value={`${stats.accepted.items} шт`} sub={`${fmtRap(stats.accepted.value)} RAP`} onClick={pick("items")} testId={`${testId}-accepted`} />
      <Metric label="Одобрено" value={stats.approved.count} sub={`выдано ${fmtRap(stats.approved.credited)} RAP`} onClick={pick("requests")} testId={`${testId}-approved`} />
      <Metric label="Обработано заявок" value={stats.processed} onClick={pick("requests")} testId={`${testId}-processed`} />
      <Metric label="На проверке (ожидает)" value={stats.review.count} sub={`${fmtRap(stats.review.value)} RAP не подтверждено`} onClick={pick("requests")} tone="ring-1 ring-[#ffb000]/25" testId={`${testId}-review`} />
      <Metric label="На доработке / отклонено" value={`${stats.revision} / ${stats.rejected}`} onClick={pick("requests")} testId={`${testId}-revision-rejected`} />
      <Metric label="Возвращено игрокам" value={`${stats.returned.items} шт`} sub={`${fmtRap(stats.returned.value)} RAP`} onClick={pick("moves")} testId={`${testId}-returned`} />
      <Metric label="Осталось у сотрудника" value={`${stats.holdings.items} шт`} sub={`${fmtRap(stats.holdings.value)} RAP`} onClick={pick("items")} tone="ring-1 ring-[#00a2ff]/25" testId={`${testId}-holdings`} />
      <Metric label="Время работы" value={fmtDuration(stats.worked_seconds)} sub={stats.flags.long_shifts ? `смен > 12 ч: ${stats.flags.long_shifts}` : stats.flags.gaps_seconds ? `без связи ${fmtDuration(stats.flags.gaps_seconds)}` : "без пауз"} onClick={pick("shifts")} testId={`${testId}-worked`} />
    </div>
  );
}
