import React, { useState } from "react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { useLang } from "../../lib/i18n";
import { useAuth } from "../../hooks/useAuth";

export default function XrocketPaymentActions({ deposit, onChanged }) {
  const { t } = useLang();
  const { refresh } = useAuth();
  const [busy, setBusy] = useState(false);
  if (deposit.payment_method !== "xrocket" || !["creating", "awaiting_payment", "processing"].includes(deposit.status)) return null;
  const check = async () => {
    setBusy(true);
    try {
      const result = await api.refreshXrocketInvoice(deposit.id);
      if (result.status === "confirmed") { await refresh(); toast.success(t("xrocket.confirmed")); }
      else toast.info(t("xrocket.not_paid"));
      await onChanged?.();
    } catch (error) {
      toast.error(error?.response?.data?.detail || t("xrocket.check_error"));
    } finally { setBusy(false); }
  };
  return <div className="w-full flex flex-wrap items-center gap-2 text-[11px]">
    {deposit.invoice_url && <a href={deposit.invoice_url} target="_blank" rel="noopener noreferrer" className="px-3 py-2 bg-[#00a2ff]/15 text-[#00a2ff] rounded-lg hover:bg-[#00a2ff]/25">{t("xrocket.open")} ↗</a>}
    <button onClick={check} disabled={busy} className="px-3 py-2 rounded-lg bg-[#262830] text-[#b4b7c7] disabled:opacity-40">{busy ? t("xrocket.checking") : t("xrocket.check")}</button>
  </div>;
}
