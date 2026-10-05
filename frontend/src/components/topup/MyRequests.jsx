import React, { useState } from "react";
import { toast } from "sonner";
import { RobuxIcon } from "../Logo";
import { api, formatMoney, parseServerDate, rejectionReasonText } from "../../lib/api";
import { useLang } from "../../lib/i18n";
import { DepositStatus } from "../DepositStatus";
import { DepositReceipt } from "../DepositReceipt";
import XrocketPaymentActions from "./XrocketPaymentActions";

const fmtDate = (d, lang) => parseServerDate(d).toLocaleString(lang === "en" ? "en-US" : "ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export default function MyRequests({ items, onChanged, onNew }) {
  const { t, lang } = useLang();
  const [busyId, setBusyId] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const activeStatuses = ["pending", "processing", "creating", "awaiting_payment"];
  const active = items.filter((item) => activeStatuses.includes(item.status));
  const history = items.filter((item) => !activeStatuses.includes(item.status));
  const visible = showHistory ? history : active;
  const cancel = async (id) => {
    setBusyId(id);
    try {
      await api.cancelDeposit(id);
      toast.success(t("requests.cancelled"));
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("requests.cancel_fail"));
    } finally {
      setBusyId(null);
    }
  };
  return (
    <div className="space-y-3" data-testid="my-requests">
      <div className="flex items-center justify-between">
        <div className="m-label">{t("requests.title")}</div>
        <button onClick={onNew} className="m-cta !w-auto !h-9 !text-[13px] !px-4 !shadow-none" data-testid="my-requests-new">
          {t("requests.new")}
        </button>
      </div>
      <div className="flex gap-2"><button type="button" className="m-chip" data-active={!showHistory} onClick={() => setShowHistory(false)} data-testid="my-requests-tab-active">{t("requests.tab_active")} · {active.length}</button><button type="button" className="m-chip" data-active={showHistory} onClick={() => setShowHistory(true)} data-testid="my-requests-tab-done">{t("requests.tab_done")} · {history.length}</button></div>
      {visible.length === 0 && <div className="m-box h-[160px] flex items-center justify-center text-[13px] text-white/50" data-testid="my-requests-empty">{showHistory ? t("requests.empty_done") : t("requests.empty_active")}</div>}
      <div className="space-y-1.5 max-h-[360px] overflow-y-auto pr-0.5">
        {visible.map((d) => (
          <div key={d.id} className="m-box px-4 py-3 space-y-1.5" data-testid="my-request-item">
            <div className="flex items-center gap-2 text-[12px]">
              {d.payment_method === "donationalerts"
                ? <span className="font-bold" data-testid="my-request-donation">DonationAlerts · {formatMoney(d.declared_amount)} {d.declared_currency}</span>
                : <><span className="font-bold inline-flex items-center gap-1">{formatMoney(d.expected_rap ?? 0)} RAP</span><span className="text-[#8e91a3]">→ {d.receiver_nick || "—"}</span></>}
              <span className="ml-auto"><DepositStatus status={d.status} /></span>
            </div>
            <div className="text-[12px] text-[#b4b7c7] break-words" data-testid="my-request-description">{d.description}</div>
            {d.status === "rejected" && d.rejection_reason && (
              <div className="text-[12px] text-[#ff8a8a] whitespace-pre-wrap break-words" data-testid="my-request-rejection-reason">
                {t("requests.rejection_reason")}: {rejectionReasonText(d.rejection_reason, t)}
              </div>
            )}
            <div className="flex items-center gap-2 text-[11px] text-[#8e91a3]">
              <span>{fmtDate(d.created_at, lang)}</span>
              {d.status === "pending" && (
                <button onClick={() => cancel(d.id)} disabled={busyId === d.id} className="ml-auto h-7 px-2.5 rounded-md m-note-err hover:!bg-[#ff5c5c] hover:!text-white font-bold transition-colors disabled:opacity-40" data-testid="my-request-cancel">
                  {t("requests.cancel")}
                </button>
              )}
            </div>
            <DepositReceipt deposit={d} testId={`request-receipt-${d.id}`} />
            <XrocketPaymentActions deposit={d} onChanged={onChanged} />
          </div>
        ))}
      </div>
      <div className="m-hint">{t("requests.hint")}</div>
    </div>
  );
}
