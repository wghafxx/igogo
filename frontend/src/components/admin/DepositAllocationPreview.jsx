import React, { useEffect, useState } from "react";
import { adminApi } from "../../lib/api";
import { DepositReceipt } from "../DepositReceipt";

export const DepositAllocationPreview = ({ depositId, rap, onReady }) => {
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setPlan(null); setError(false); onReady(false);
    if (!Number.isFinite(rap) || rap < 35 || rap > 1000000) return;
    const timer = setTimeout(() => {
      adminApi.depositPreview(depositId, rap).then((result) => {
        if (alive) { setPlan(result); onReady(true); }
      }).catch(() => { if (alive) setError(true); });
    }, 300);
    return () => { alive = false; clearTimeout(timer); };
  }, [depositId, rap, retry, onReady]);
  if (rap < 35 || !Number.isFinite(rap) || rap > 1000000) return null;
  if (error) return <div className="text-[11px] text-[#ff8a8a]" data-testid={`allocation-error-${depositId}`}>Не удалось рассчитать выдачу. <button data-testid={`allocation-retry-${depositId}`} onClick={() => setRetry((v) => v + 1)} className="text-[#00a2ff]">Повторить</button></div>;
  if (!plan) return <div className="text-[11px] text-[#8e91a3]" data-testid={`allocation-loading-${depositId}`}>Подбираем скины…</div>;
  return <div className="rounded-lg bg-[#0f1015] p-3 space-y-2" data-testid={`allocation-preview-${depositId}`}>
    <div className="text-[11px] font-bold">Предварительная выдача</div>
    <DepositReceipt deposit={{ ...plan, status: "processing" }} testId={`allocation-receipt-${depositId}`} />
    <p className="text-[10px] text-[#7d8194]">Только в пределах суммы после комиссии и промокода. Состав зависит от каталога; остаток — на баланс.</p>
  </div>;
};