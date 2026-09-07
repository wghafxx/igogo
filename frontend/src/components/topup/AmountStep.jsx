import React, { useState } from "react";
import { toast } from "sonner";
import { CheckIcon } from "../icons/check";
import { TicketIcon } from "../icons/ticket";
import { RobuxIcon } from "../Logo";
import { api, formatMoney, DEPOSIT_FEE, pct } from "../../lib/api";
import { useAuth } from "../../hooks/useAuth";

const QUICK = [50, 100, 250, 500, 1000];

export const calcCredit = (rap, bonus) => Math.round(rap * (1 - DEPOSIT_FEE) * (1 + (bonus || 0)) * 100) / 100;

export default function AmountStep({ minRap, rap, setRap, onNext, ready }) {
  const { authUser, setAuthUser, openAuth } = useAuth();
  const [code, setCode] = useState(authUser?.promo_code || "");
  const [busy, setBusy] = useState(false);
  const bonus = authUser?.promo_bonus || 0;
  const active = Boolean(authUser?.promo_code) && authUser.promo_code === code.trim().toUpperCase();
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
      toast.success(`Промокод ${u.promo_code}: +${pct(u.promo_bonus)}% к депозиту`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Промокод не найден");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="topup-amount-step">
      <div className="flex flex-wrap gap-2 items-center justify-between">
        <span className="text-[13px] font-bold">Сумма пополнения</span>
        <div className="flex items-center gap-1.5" data-testid="topup-quick-amounts">
          {QUICK.map((q) => (
            <button key={q} onClick={() => setRap(String(q))} className={`h-6 px-2 rounded-md text-[11px] font-bold transition-colors ${num === q ? "bg-[#ffb000] text-black" : "bg-[#2a2b31] text-[#8e91a3] hover:text-white"}`} data-testid={`topup-quick-${q}`}>
              {q}
            </button>
          ))}
        </div>
      </div>

      <div className={`rounded-xl bg-[#0f1015] border px-4 py-3 flex items-center gap-3 ${tooSmall ? "border-[#ff5c5c]" : "border-[#ffb000]/60 focus-within:border-[#ffb000]"}`} data-testid="topup-amount-box">
        <input
          value={rap}
          onChange={(e) => { const next = e.target.value.replace(",", "."); if (/^\d{0,7}(\.\d{0,2})?$/.test(next)) setRap(next); }}
          placeholder="0"
          inputMode="decimal"
          className="flex-1 min-w-0 bg-transparent outline-none text-[26px] font-black placeholder:text-[#3a3c47]"
          data-testid="topup-rap-input"
        />
        <div className="text-right shrink-0">
          <div className="text-[11px] text-[#ffb000] font-bold">RAP скина</div>
          <div className={`text-[11px] ${tooSmall ? "text-[#ff8a8a]" : "text-[#7d8194]"}`}>мин. {minRap} RAP · комиссия {Math.round(DEPOSIT_FEE * 100)}%</div>
        </div>
      </div>

      <div className="flex items-center gap-2 h-12 px-3 rounded-xl bg-[#0f1015]" data-testid="promo-block">
        <TicketIcon size={16} className="text-[#ffb000] shrink-0" />
        <input
          value={code}
          maxLength={32}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && applyPromo()}
          placeholder="Промокод"
          className="flex-1 min-w-0 bg-transparent outline-none text-[13px] font-bold tracking-wide placeholder:font-normal placeholder:text-[#5f6377]"
          data-testid="promo-input"
        />
        <button onClick={applyPromo} disabled={busy || !code.trim()} className={`h-8 w-9 rounded-md flex items-center justify-center transition-colors ${active ? "bg-[#ffb000] text-black" : "bg-[#2a2b31] text-white hover:bg-[#3a3c47]"} disabled:opacity-40`} data-testid="promo-apply-button" title="Применить">
          <CheckIcon size={16} />
        </button>
      </div>
      {bonus > 0 && (
        <div className="h-8 rounded-md bg-[#ffb000]/15 text-[#ffb000] text-[12px] font-bold flex items-center justify-center uppercase tracking-wide" data-testid="promo-bonus">
          +{pct(bonus)}% к депозиту
        </div>
      )}

      <button
        onClick={() => (authUser ? onNext() : openAuth())}
        disabled={authUser && (!ready || num < minRap || num > 1000000 || !Number.isFinite(num))}
        className="w-full h-13 py-3.5 rounded-xl bg-[#ffb000] hover:bg-[#ffc233] disabled:opacity-40 disabled:hover:bg-[#ffb000] text-black font-black text-[15px] flex items-center justify-center gap-2 transition-colors"
        data-testid="topup-next-button"
      >
        {!authUser ? "Войти для пополнения" : (
          <>
            Пополнить
            {num >= minRap && (
              <span className="flex items-center gap-1.5">
                <span className="inline-flex items-center gap-1">{formatMoney(credit)} <RobuxIcon size={13} /></span>
                <span className="text-[12px] font-bold text-black/50 line-through">{formatMoney(num)}</span>
              </span>
            )}
          </>
        )}
      </button>
      <div className="text-[11px] text-[#8e91a3] text-center leading-snug" data-testid="deposit-allocation-explanation">После комиссии 20%{bonus > 0 ? ` и бонуса ${pct(bonus)}%` : ""} — до 5 разных скинов в инвентарь, остаток на баланс. Подбор стремится к равным долям, но зависит от цен в каталоге. Если не хватит на один скин, вся рассчитанная сумма останется на балансе. Выдача только после подтверждения администратора.</div>
    </div>
  );
}
