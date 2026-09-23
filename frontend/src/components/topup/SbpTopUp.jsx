import React, { useState } from "react";
import { toast } from "sonner";
import { RobuxIcon } from "../Logo";
import { useAuth } from "../../hooks/useAuth";
import { useLang } from "../../lib/i18n";
import { api } from "../../lib/api";
import { openLiveChat } from "../../lib/events";

// Тариф: 1 RAP = 0,50 ₽. Минимальный платёж — 35 ₽ (70 RAP).
export const RAP_RUB_RATE = 0.5;
export const MIN_RUB = 35;
const QUICK_RUB = [50, 100, 250, 500, 1000];
const DA_CURRENCIES = ["USD", "EUR", "UAH", "KZT", "BYN", "PLN", "TRY", "BRL", "UZS", "RUB"];

// Any currency: DonationAlerts steps are posted in the support chat, the owner approves in Telegram.
const DonationForm = ({ onDone }) => {
  const { authUser, openAuth } = useAuth();
  const { t } = useLang();
  const [currency, setCurrency] = useState("USD");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const value = Number(amount) || 0;
  const submit = async () => {
    if (!authUser) return openAuth();
    if (busy || value <= 0) return;
    setBusy(true);
    try {
      const res = await api.donationRequest(currency, value);
      toast.success(t("da.created"));
      onDone?.();
      openLiveChat(res.chat_id);
    } catch (e) {
      const m = e?.response?.data?.detail;
      toast.error(typeof m === "string" ? m : t("chat.create_error"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="m-foot space-y-3" data-testid="donation-form">
      <div className="rounded-[12px] m-note-info px-4 py-3 text-[12px] leading-relaxed" data-testid="card-info">{t("da.intro")}</div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("da.currency")} data-testid="donation-currencies">
        {DA_CURRENCIES.map((c) => (
          <button key={c} type="button" onClick={() => setCurrency(c)} className="m-chip" data-active={currency === c ? "true" : "false"} data-testid={`donation-currency-${c}`}>{c}</button>
        ))}
      </div>
      <div className="m-input" data-testid="donation-amount-box">
        <input value={amount} onChange={(e) => { const next = e.target.value.replace(",", "."); if (/^\d{0,9}(\.\d{0,2})?$/.test(next)) setAmount(next); }} placeholder="0" inputMode="decimal" data-testid="donation-amount-input" />
        <span className="text-xl text-white/50 font-bold">{currency}</span>
      </div>
      <button onClick={submit} disabled={busy || (authUser && value <= 0)} className="m-cta" data-testid="card-support-button">
        {!authUser ? t("rub.login") : t("da.submit")}
      </button>
      <div className="m-hint" data-testid="donation-rate-note">{t("da.rate_note")}</div>
      <div className="m-hint" data-testid="card-terms-note">{t("rub.terms")}</div>
    </div>
  );
};

const SbpLogo = () => (
  <span className="flex items-center gap-3">
    <img src="/payments/sbp.png" alt="" width={34} height={40} className="h-10 w-auto object-contain" />
    <b className="text-[18px] font-black tracking-wide">СБП</b>
  </span>
);

const CardLogo = ({ label }) => (
  <span className="flex flex-col items-center justify-center gap-2">
    <img src="/payments/visa.png" alt="Visa" width={80} height={26} className="h-[26px] w-auto object-contain" />
    <b className="text-[12px] font-black tracking-wide uppercase text-white/80">{label}</b>
  </span>
);

export default function SbpTopUp({ onDone }) {
  const { authUser, openAuth } = useAuth();
  const { t } = useLang();
  const [method, setMethod] = useState("sbp");
  const [rub, setRub] = useState("");
  const [busy, setBusy] = useState(false);

  const num = Number(rub) || 0;
  const tooSmall = num > 0 && num < MIN_RUB;
  const rap = Math.floor(num / RAP_RUB_RATE * 100) / 100;
  const sbpValid = Number.isFinite(num) && num >= MIN_RUB && num <= 1000000;

  const goToSupport = async (text) => {
    if (!authUser) return openAuth();
    if (busy) return;
    setBusy(true);
    try {
      const created = await api.createChat({ kind: "support", for_topup: true, text });
      toast.success(t("chat.deposit_created"));
      onDone?.();
      openLiveChat(created.id);
    } catch (e) {
      const m = e?.response?.data?.detail;
      toast.error(typeof m === "string" ? m : t("chat.create_error"));
    } finally {
      setBusy(false);
    }
  };

  const paySbp = () => {
    if (!authUser) return openAuth();
    if (!sbpValid) return;
    goToSupport(`${t("rub.chat_sbp")} ${num} ₽ (≈ ${rap} RAP)`);
  };

  return (
    <div data-testid="topup-rub-step">
      <div className="grid grid-cols-2 gap-1.5" role="group" aria-label={t("topup.rubles")}>
        <button type="button" onClick={() => setMethod("sbp")} className="m-tile min-h-[100px] flex items-center justify-center" aria-pressed={method === "sbp"} data-testid="rub-method-sbp">
          <SbpLogo />
        </button>
        <button type="button" onClick={() => setMethod("card")} className="m-tile min-h-[100px] flex items-center justify-center" aria-pressed={method === "card"} data-testid="rub-method-card">
          <CardLogo label={t("rub.method_card")} />
        </button>
      </div>

      {method === "sbp" && (
        <div className="m-foot space-y-3">
          <div className="flex flex-wrap gap-2 items-center justify-between">
            <span className="m-label">{t("rub.title")}</span>
            <div className="flex flex-wrap items-center gap-1.5" data-testid="rub-quick-amounts">
              {QUICK_RUB.map((q) => (
                <button key={q} onClick={() => setRub(String(q))} className="m-chip" data-active={num === q ? "true" : "false"} data-testid={`rub-quick-${q}`}>
                  {q} ₽
                </button>
              ))}
            </div>
          </div>

          <div className="m-input" data-invalid={tooSmall ? "true" : "false"} data-testid="rub-amount-box">
            <input
              value={rub}
              onChange={(e) => { const next = e.target.value.replace(",", "."); if (/^\d{0,7}(\.\d{0,2})?$/.test(next)) setRub(next); }}
              placeholder="0"
              inputMode="decimal"
              data-testid="rub-input"
            />
            <span className="text-2xl text-white/50">₽</span>
            <div className="text-right shrink-0 pl-2">
              <div className="text-[13px] flex items-center justify-end gap-1 text-white">≈ {rap} <RobuxIcon size={12} /></div>
              <div className={`text-[11px] ${tooSmall ? "text-[#ff8a8a]" : "text-[#7d8194]"}`}>{t("rub.min_rate")}</div>
            </div>
          </div>

          <button onClick={paySbp} disabled={busy || (authUser && !sbpValid)} className="m-cta" data-testid="rub-pay-button">
            {!authUser ? t("rub.login") : (
              <>
                {t("rub.pay")}
                {sbpValid && <span className="flex items-center gap-1.5">{num} ₽<span className="inline-flex items-center gap-1 text-[12px] font-bold text-black/60">≈ {rap} <RobuxIcon size={11} /></span></span>}
              </>
            )}
          </button>

          <div className="m-hint" data-testid="rub-sbp-hint">{t("rub.sbp_hint")}</div>
          <div className="m-hint" data-testid="rub-terms-note">{t("rub.terms")}</div>
        </div>
      )}

      {method === "card" && <DonationForm onDone={onDone} />}
    </div>
  );
}
