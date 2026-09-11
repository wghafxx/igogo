import React, { useState } from "react";
import { toast } from "sonner";
import { RobuxIcon } from "../Logo";
import { api, formatMoney, parseServerDate } from "../../lib/api";
import { DepositStatus } from "../TopUpModal";
import { DepositReceipt } from "../DepositReceipt";

const fmtDate = (d) => parseServerDate(d).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export default function MyRequests({ items, onChanged, onNew }) {
  const [busyId, setBusyId] = useState(null);
  const cancel = async (id) => {
    setBusyId(id);
    try {
      await api.cancelDeposit(id);
      toast.success("Заявка отменена");
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Не удалось отменить");
    } finally {
      setBusyId(null);
    }
  };
  return (
    <div className="space-y-3" data-testid="my-requests">
      <div className="flex items-center justify-between">
        <div className="text-[13px] font-bold">Мои заявки</div>
        <button onClick={onNew} className="h-8 px-3 rounded-lg bg-[#ffb000] hover:bg-[#ffc233] text-black text-[12px] font-bold transition-colors" data-testid="my-requests-new">
          + Новая заявка
        </button>
      </div>
      {items.length === 0 && <div className="h-[140px] flex items-center justify-center text-[13px] text-[#5f6377] rounded-xl bg-[#0f1015]" data-testid="my-requests-empty">Заявок пока нет</div>}
      <div className="space-y-1.5 max-h-[360px] overflow-y-auto pr-0.5">
        {items.map((d) => (
          <div key={d.id} className="rounded-xl bg-[#0f1015] px-3 py-2.5 space-y-1.5" data-testid="my-request-item">
            <div className="flex items-center gap-2 text-[12px]">
              <span className="font-bold inline-flex items-center gap-1">{formatMoney(d.expected_rap ?? 0)} RAP</span>
              <span className="text-[#8e91a3]">→ {d.receiver_nick || "—"}</span>
              <span className="ml-auto"><DepositStatus status={d.status} /></span>
            </div>
            <div className="text-[12px] text-[#b4b7c7] break-words" data-testid="my-request-description">{d.description}</div>
            <div className="flex items-center gap-2 text-[11px] text-[#8e91a3]">
              <span>{fmtDate(d.created_at)}</span>
              {d.status === "pending" && (
                <button onClick={() => cancel(d.id)} disabled={busyId === d.id} className="ml-auto h-7 px-2.5 rounded-md bg-[#ff5c5c]/15 text-[#ff8a8a] hover:bg-[#ff5c5c] hover:text-white font-bold transition-colors disabled:opacity-40" data-testid="my-request-cancel">
                  Отменить
                </button>
              )}
            </div>
            <DepositReceipt deposit={d} testId={`request-receipt-${d.id}`} />
          </div>
        ))}
      </div>
      <div className="text-[11px] text-[#5f6377] leading-snug">Заявку нельзя редактировать — отмените и создайте новую. Не чаще одной заявки в минуту.</div>
    </div>
  );
}
