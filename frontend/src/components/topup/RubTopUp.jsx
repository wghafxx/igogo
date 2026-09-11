import React, { useState } from "react";
import { toast } from "sonner";
import { RobuxIcon } from "../Logo";
import { useAuth } from "../../hooks/useAuth";
import { SUPPORT_HANDLE } from "../SupportDialog";
import { useLang } from "../../lib/i18n";

const SUPPORT_URL = process.env.REACT_APP_TELEGRAM_SUPPORT_URL || "https://t.me/bloxgradesupport";

// Тариф: 1 RAP = 0,50 ₽. Минимальный платёж — 35 ₽ (70 RAP).
export const RAP_RUB_RATE = 0.5;
export const MIN_RUB = 35;
const QUICK_RUB = [35, 50, 100, 250, 500, 1000];

export default function RubTopUp() {
  const { authUser, openAuth } = useAuth();
  const { t } = useLang();
  const [rub, setRub] = useState("");
  const [pending, setPending] = useState(null);

  const num = Number(rub) || 0;
  const tooSmall = num > 0 && num < MIN_RUB;
  const rap = Math.floor(num / RAP_RUB_RATE * 100) / 100;

  const pay = () => {
    if (!authUser) return openAuth();
    if (!Number.isFinite(num) || num < MIN_RUB || num > 1000000) return;
    // Онлайн-приём СБП на согласовании: фиксируем сумму и ведём в поддержку.
    setPending({ rub: num, rap });
    toast.info(t("rub.connecting"));
  };

  return (
    <div className="space-y-4" data-testid="topup-rub-step">
      <div className="flex flex-wrap gap-2 items-center justify-between">
        <span className="text-[13px] font-bold">{t("rub.title")}</span>
        <div className="flex flex-wrap items-center gap-1.5" data-testid="rub-quick-amounts">
          {QUICK_RUB.map((q) => (
            <button key={q} onClick={() => { setRub(String(q)); setPending(null); }} className={`h-6 px-2 rounded-md text-[11px] font-bold transition-colors ${num === q ? "bg-[#ffb000] text-black" : "bg-[#2a2b31] text-[#8e91a3] hover:text-white"}`} data-testid={`rub-quick-${q}`}>
              {q} ₽
            </button>
          ))}
        </div>
      </div>

      <div className={`rounded-xl bg-[#0f1015] border px-4 py-3 flex items-center gap-3 ${tooSmall ? "border-[#ff5c5c]" : "border-[#ffb000]/60 focus-within:border-[#ffb000]"}`} data-testid="rub-amount-box">
        <input
          value={rub}
          onChange={(e) => { const next = e.target.value.replace(",", "."); if (/^\d{0,7}(\.\d{0,2})?$/.test(next)) { setRub(next); setPending(null); } }}
          placeholder="0"
          inputMode="decimal"
          className="flex-1 min-w-0 bg-transparent outline-none text-[26px] font-black placeholder:text-[#3a3c47]"
          data-testid="rub-input"
        />
        <div className="text-right shrink-0">
          <div className="text-[11px] text-[#ffb000] font-bold">{t("rub.per")}</div>
          <div className={`text-[11px] ${tooSmall ? "text-[#ff8a8a]" : "text-[#7d8194]"}`}>{t("rub.min_rate")}</div>
        </div>
      </div>

      <button
        onClick={pay}
        disabled={authUser && (!Number.isFinite(num) || num < MIN_RUB || num > 1000000)}
        className="w-full h-13 py-3.5 rounded-xl bg-[#ffb000] hover:bg-[#ffc233] disabled:opacity-40 disabled:hover:bg-[#ffb000] text-black font-black text-[15px] flex items-center justify-center gap-2 transition-colors"
        data-testid="rub-pay-button"
      >
        {!authUser ? t("rub.login") : (
          <>
            {t("rub.pay")}
            {num >= MIN_RUB && (
              <span className="flex items-center gap-1.5">
                {num} ₽
                <span className="inline-flex items-center gap-1 text-[12px] font-bold text-black/60">≈ {rap} <RobuxIcon size={11} /></span>
              </span>
            )}
          </>
        )}
      </button>

      {pending && (
        <div className="rounded-xl bg-[#00a2ff]/10 border border-[#00a2ff]/40 px-4 py-3 text-[12px] text-[#b4d9ff] leading-relaxed" data-testid="rub-pending-notice">
          {t("rub.chosen")} <b>{pending.rub} ₽ ≈ {pending.rap} RAP</b>. {t("rub.pending")}{SUPPORT_HANDLE ? <>: <b>{SUPPORT_HANDLE}</b></> : ""} {t("rub.pending_manager")}
          {SUPPORT_URL && (
            <a href={SUPPORT_URL} target="_blank" rel="noopener noreferrer" className="mt-2 h-9 rounded-lg bg-[#00a2ff] hover:bg-[#1ab0ff] text-white font-bold text-[12px] items-center justify-center flex" data-testid="rub-support-link">
              {t("rub.support_btn")}
            </a>
          )}
        </div>
      )}

      <div className="text-[11px] text-[#8e91a3] text-center leading-snug" data-testid="rub-terms-note">
        {t("rub.terms")}
      </div>
    </div>
  );
}
