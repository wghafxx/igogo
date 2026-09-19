import React, { useState } from "react";
import { toast } from "sonner";
import { CheckIcon } from "../icons/check";
import { TicketIcon } from "../icons/ticket";
import { RobuxIcon } from "../Logo";
import { api, formatMoney, DEPOSIT_FEE, pct } from "../../lib/api";
import { useAuth } from "../../hooks/useAuth";
import { useSessionCtx } from "../../hooks/useSessionCtx";
import { useLang } from "../../lib/i18n";

const QUICK = [200, 250, 500, 1000, 2500];

export const calcCredit = (rap, bonus) => Math.round(rap * (1 - DEPOSIT_FEE) * (1 + (bonus || 0)) * 100) / 100;

export default function AmountStep({ minRap, rap, setRap, onNext, ready, hint }) {
  const { authUser, setAuthUser, openAuth } = useAuth();
  const sessionCtx = useSessionCtx();
  const { t } = useLang();
  const [code, setCode] = useState(authUser?.promo_code || "");
  const [busy, setBusy] = useState(false);
  const [gift, setGift] = useState(null);
  const bonus = authUser?.promo_bonus || 0;
  const active = Boolean(authUser?.promo_code) && authUser.promo_code === code.trim().toUpperCase();
  const giftActive = gift && gift.code === code.trim().toUpperCase();
  const num = Number(rap) || 0;
  const tooSmall = num > 0 && num < minRap;
  const credit = calcCredit(num, bonus);

  const applyPromo = async () => {
    if (!authUser) return openAuth();
    if (!code.trim() || busy) return;
    setBusy(true);
    try {
      const u = await api.applyPromo(code.trim());
      setAuthUser(u);
      try {
        sessionCtx?.setUser?.((prev) => ({
          ...(prev || {}),
          balance: u.balance,
          promo_code: u.promo_code,
          promo_bonus: u.promo_bonus,
        }));
      } catch { /* next poll restores consistency */ }
      if (u.gift_type === "rap_fixed") {
        setGift({ code: code.trim().toUpperCase(), amount: u.gift_amount, already: Boolean(u.gift_already_received) });
        if (u.gift_already_received) toast.success(t("topup.promo_gift_already"));
        else toast.success(`${t("topup.promo_gift_done")} ${formatMoney(u.gift_amount)} RAP`);
      } else {
        setGift(null);
        toast.success(`${t("topup.promo_word")} ${u.promo_code}: +${pct(u.promo_bonus)}% ${t("topup.promo_bonus")}`);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("topup.promo_fail"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="topup-amount-step">
      <div className="m-box p-4 flex items-start gap-3">
        <span className="w-10 h-10 rounded-xl bg-[#ffb000]/15 text-[#ffb000] flex items-center justify-center shrink-0"><RobuxIcon size={20} /></span>
        <div className="min-w-0 text-[12px] leading-relaxed text-[#b4b7c7]">
          <div className="text-[14px] font-bold text-white mb-1">{t("topup.skins")} · {Math.round((1 - DEPOSIT_FEE) * 100)}%</div>
          <span data-testid="topup-chat-hint">{hint}</span>
        </div>
      </div>

      <div className="m-foot space-y-3">
        <div className="flex flex-wrap gap-2 items-center justify-between">
          <span className="m-label">{t("amount.title")}</span>
          <div className="flex items-center gap-1.5" data-testid="topup-quick-amounts">
            {QUICK.map((q) => (
              <button key={q} onClick={() => setRap(String(q))} className="m-chip" data-active={num === q ? "true" : "false"} data-testid={`topup-quick-${q}`}>
                {q}
              </button>
            ))}
          </div>
        </div>

        <div className="m-input" data-invalid={tooSmall ? "true" : "false"} data-testid="topup-amount-box">
          <input
            value={rap}
            onChange={(e) => { const next = e.target.value.replace(",", "."); if (/^\d{0,7}(\.\d{0,2})?$/.test(next)) setRap(next); }}
            placeholder="0"
            inputMode="decimal"
            data-testid="topup-rap-input"
          />
          <div className="text-right shrink-0">
            <div className="text-[12px] text-[#ffb000] font-bold flex items-center justify-end gap-1">{t("amount.skin_rap")} <RobuxIcon size={12} /></div>
            <div className={`text-[11px] ${tooSmall ? "text-[#ff8a8a]" : "text-[#7d8194]"}`}>{t("amount.min_fee")} {minRap} RAP · {t("amount.fee")} {Math.round(DEPOSIT_FEE * 100)}%</div>
          </div>
        </div>

        <div className="m-input m-input-sm" data-testid="promo-block">
          <TicketIcon size={18} className="text-[#ffb000] shrink-0" />
          <input
            value={code}
            maxLength={32}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && applyPromo()}
            placeholder={t("amount.promo")}
            data-testid="promo-input"
          />
          <button onClick={applyPromo} disabled={busy || !code.trim()} className="m-iconbtn" data-active={active ? "true" : "false"} data-testid="promo-apply-button" title="Применить" aria-label="Применить">
            <CheckIcon size={16} />
          </button>
        </div>
        {giftActive ? (
          <div className="h-9 rounded-[10px] m-note-ok text-[12px] font-bold flex items-center justify-center uppercase tracking-wide" data-testid="promo-gift">
            {gift.already ? t("topup.promo_gift_already") : `${t("topup.promo_gift_done")} ${formatMoney(gift.amount)} RAP`}
          </div>
        ) : (
          bonus > 0 && (
            <div className="h-9 rounded-[10px] m-note-warn text-[12px] font-bold flex items-center justify-center uppercase tracking-wide" data-testid="promo-bonus">
              +{pct(bonus)}% {t("topup.promo_bonus")}
            </div>
          )
        )}

        <button
          onClick={() => (authUser ? onNext() : openAuth())}
          disabled={authUser && (!ready || num < minRap || num > 1000000 || !Number.isFinite(num))}
          className="m-cta"
          data-testid="topup-next-button"
        >
          {!authUser ? t("amount.login") : (
            <>
              {t("amount.topup")}
              {num >= minRap && (
                <span className="flex items-center gap-1.5">
                  <span className="inline-flex items-center gap-1">{formatMoney(credit)} <RobuxIcon size={14} /></span>
                  <span className="text-[12px] font-bold text-black/50 line-through">{formatMoney(num)}</span>
                </span>
              )}
            </>
          )}
        </button>
        <div className="m-hint" data-testid="deposit-allocation-explanation">{t("amount.explain")}{bonus > 0 ? ` ${t("amount.explain_bonus")} ${pct(bonus)}%` : ""} {t("amount.explain_tail")}</div>
      </div>
    </div>
  );
}
