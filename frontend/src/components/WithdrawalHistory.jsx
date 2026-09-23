import React from "react";
import { formatMoney, parseServerDate } from "../lib/api";
import { skinImg } from "../lib/img";
import { useLang } from "../lib/i18n";

export default function WithdrawalHistory({ items = [], onInstructions }) {
  const { t, lang } = useLang();
  return <div className="space-y-2" data-testid="profile-withdrawals">
    {items.length === 0 && <div className="h-[200px] flex items-center justify-center text-[13px] text-[#5f6377]">{t("withdrawals.empty")}</div>}
    {items.map((w) => <div key={w.id} className="rounded-xl bg-[#0f1015] px-3 py-3 space-y-2 text-[12px]" data-testid="profile-withdrawal-item">
      <div className="flex flex-wrap items-center gap-3">
        {w.item?.image && <img src={skinImg(w.item.image)} alt="" width={40} height={40} loading="lazy" decoding="async" className="w-10 h-10 object-contain" />}
        <div className="flex-1 min-w-[120px]"><b>{w.item?.name}</b><div className="text-[#ffb000] font-bold">{formatMoney(w.item?.price)} RAP</div></div>
        <span className={`font-bold ${w.status === "cancelled" ? "text-[#ff8a8a]" : w.status === "done" ? "text-[#72dca0]" : "text-[#ffb000]"}`}>{t(`withdrawals.${w.status}`)}</span>
        <span className="text-[#8e91a3]">{parseServerDate(w.created_at).toLocaleString(lang === "en" ? "en-US" : "ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
      </div>
      {w.cancellation_reason && <div className="text-[#ff8a8a] whitespace-pre-wrap break-words" data-testid="profile-withdrawal-reason">{t("withdrawals.reason")}: {w.cancellation_reason}</div>}
      {w.status === "cancelled" && <div className="text-[#8e91a3]">{t("withdrawals.returned")}</div>}
      {w.status === "pending" && <button onClick={() => onInstructions(1)} className="text-[#00a2ff] hover:text-white font-bold" data-testid="profile-withdrawal-instructions">{t("withdrawals.instructions")}</button>}
    </div>)}
  </div>;
}
