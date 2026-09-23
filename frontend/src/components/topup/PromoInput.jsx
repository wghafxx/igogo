import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckIcon } from "../icons/check";
import { TicketIcon } from "../icons/ticket";
import { api, pct, formatMoney } from "../../lib/api";
import { useLang } from "../../lib/i18n";
import { useAuth } from "../../hooks/useAuth";

export const PromoInput = ({ compact = false }) => {
  const { authUser, setAuthUser } = useAuth();
  const { t } = useLang();
  const [code, setCode] = useState(authUser?.promo_code || "");
  const [busy, setBusy] = useState(false);
  const [gift, setGift] = useState(null);
  useEffect(() => {
    if (authUser?.promo_code) setCode(authUser.promo_code);
  }, [authUser?.promo_code]);
  const active = authUser?.promo_code && authUser.promo_code === code.trim().toUpperCase();
  const giftActive = gift && gift.code === code.trim().toUpperCase();

  const apply = async () => {
    if (!code.trim() || busy) return;
    setBusy(true);
    try {
      const u = await api.applyPromo(code.trim());
      // authUser is the single source of the signed-in user (header balance included).
      setAuthUser(u);
      if (u.gift_type === "rap_fixed") {
        const upper = code.trim().toUpperCase();
        setGift({ code: upper, amount: u.gift_amount, already: Boolean(u.gift_already_received) });
        if (u.gift_already_received) toast.success(t("topup.promo_gift_already"));
        else toast.success(`${t("topup.promo_gift_done")} ${formatMoney(u.gift_amount)} RAP`);
      } else {
        setGift(null);
        toast.success(`${t("topup.promo_word")} ${u.promo_code} ${t("topup.promo_ok")}: +${pct(u.promo_bonus)}% ${t("topup.promo_topup_bonus")}`);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("topup.promo_fail"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="promo-block">
      <div className="m-input m-input-sm">
        <TicketIcon size={18} className="text-[#ffb000] shrink-0" />
        <input
          value={code}
          onChange={(e) => { setCode(e.target.value.toUpperCase()); }}
          onKeyDown={(e) => e.key === "Enter" && apply()}
          placeholder={t("topup.promo_placeholder")}
          maxLength={32}
          data-testid="promo-input"
        />
        <button
          onClick={apply}
          disabled={busy || !code.trim() || !authUser}
          className="m-iconbtn"
          data-active={active || giftActive ? "true" : "false"}
          aria-label={t("common.apply")}
          title={t("common.apply")}
          data-testid="promo-apply-button"
        >
          <CheckIcon size={16} />
        </button>
      </div>
      {giftActive ? (
        <div className="mt-2 h-9 rounded-[10px] m-note-ok text-[12px] font-bold flex items-center justify-center uppercase tracking-wide" data-testid="promo-gift">
          {gift.already ? t("topup.promo_gift_already") : `${t("topup.promo_gift_done")} ${formatMoney(gift.amount)} RAP`}
        </div>
      ) : (
        authUser?.promo_bonus > 0 && !compact && (
          <div className="mt-2 h-9 rounded-[10px] m-note-warn text-[12px] font-bold flex items-center justify-center uppercase tracking-wide" data-testid="promo-bonus">
            +{pct(authUser.promo_bonus)}% {t("topup.promo_bonus")}
          </div>
        )
      )}
    </div>
  );
};

export default PromoInput;
