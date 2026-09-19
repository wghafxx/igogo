import React, { useEffect, useState } from "react";
import { CheckIcon } from "./icons/check";
import { TicketIcon } from "./icons/ticket";
import { BoxesIcon } from "./icons/boxes";
import { FileTextIcon } from "./icons/file-text";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { api, pct, formatMoney } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../hooks/useAuth";
import { useSessionCtx } from "../hooks/useSessionCtx";
import AmountStep from "./topup/AmountStep";
import RubTopUp from "./topup/RubTopUp";
import CryptoTopUp from "./topup/CryptoTopUp";
import { HandCoinsIcon } from "./icons/hand-coins";
import { WalletIcon } from "./icons/wallet";
import MyRequests from "./topup/MyRequests";

export const PromoInput = ({ compact = false }) => {
  const { authUser, setAuthUser } = useAuth();
  const sessionCtx = useSessionCtx();
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
      setAuthUser(u);
      // Header balance lives in useSession state — one setAuthUser() is not enough.
      try {
        sessionCtx?.setUser?.((prev) => ({
          ...(prev || {}),
          balance: u.balance,
          promo_code: u.promo_code,
          promo_bonus: u.promo_bonus,
        }));
      } catch { /* session stays consistent via next poll */ }
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
          aria-label="Применить"
          title="Применить"
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

export { DepositStatus } from "./DepositStatus";

export default function TopUpModal({ open, onOpenChange }) {
  const { authUser } = useAuth();
  const { t } = useLang();
  const [info, setInfo] = useState(null);
  const [tab, setTab] = useState("skins");
  const [rap, setRap] = useState("");
  const [mine, setMine] = useState([]);
  const [infoError, setInfoError] = useState(false);
  const [mineError, setMineError] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const startDepositChat = async () => {
    if (chatBusy) return;
    setChatBusy(true);
    try {
      const created = await api.createChat({ kind: "deposit", expected_rap: Number(rap) });
      toast.success(t("chat.deposit_created"));
      setRap("");
      loadMine();
      onOpenChange(false);
      window.dispatchEvent(new CustomEvent("open-live-chat", { detail: { chatId: created.id } }));
    } catch (e) {
      const m = e?.response?.data?.detail;
      toast.error(typeof m === "string" ? m : t("chat.create_error"));
    } finally {
      setChatBusy(false);
    }
  };
  const loadInfo = () => { setInfoError(false); api.depositInfo().then(setInfo).catch(() => setInfoError(true)); };

  const loadMine = () => authUser && api.myDeposits().then((rows) => { setMine(rows); setMineError(false); }).catch(() => setMineError(true));
  useEffect(() => {
    if (open && !info) loadInfo();
    if (open) loadMine();
    if (!open) setTab("skins");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, authUser]);
  useEffect(() => {
    const openRub = () => { setTab("rubles"); onOpenChange(true); };
    const openCrypto = () => { setTab("crypto"); onOpenChange(true); };
    window.addEventListener("open-rub-topup", openRub);
    window.addEventListener("open-crypto-topup", openCrypto);
    return () => { window.removeEventListener("open-rub-topup", openRub); window.removeEventListener("open-crypto-topup", openCrypto); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!open || !authUser) return;
    const timer = setInterval(loadMine, 15000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, authUser?.session_id]);

  const pendingCount = mine.filter((d) => ["pending", "processing", "creating", "awaiting_payment"].includes(d.status)).length;
  const TABS = [
    ["skins", <BoxesIcon size={18} />, t("topup.skins")],
    ["rubles", <WalletIcon size={18} />, t("topup.rubles").replace(/^₽\s*/, "")],
    ["crypto", <HandCoinsIcon size={18} />, t("topup.crypto")],
    ["requests", <FileTextIcon size={18} />, t("topup.requests")],
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="modal-surface border-0 text-white w-[calc(100%-1.25rem)] sm:max-w-[560px] p-0 overflow-hidden max-h-[92vh] flex flex-col gap-0" data-testid="topup-dialog">
        <DialogHeader className="modal-head px-6 pt-4 pb-4 shrink-0 text-left gap-4 space-y-0">
          <DialogTitle className="modal-title text-left">{t("topup.title")}</DialogTitle>
          <div className="seg" role="tablist">
            {TABS.map(([key, icon, label]) => (
              <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)} className="seg-btn" data-active={tab === key ? "true" : "false"} data-testid={`topup-tab-${key}`}>
                {icon} <span className="truncate">{label}</span>
                {key === "requests" && pendingCount > 0 && <span className="h-5 min-w-5 px-1.5 rounded-full bg-[#ffb000] text-black text-[11px] font-black flex items-center justify-center" data-testid="topup-pending-badge">{pendingCount}</span>}
              </button>
            ))}
          </div>
        </DialogHeader>

        <div className="px-6 pb-6 pt-4 overflow-y-auto">
          {infoError && <div className="mb-3 rounded-[10px] m-note-err px-3 py-2 text-sm" data-testid="topup-info-error">{t("topup.info_fail")} <button className="underline" data-testid="topup-info-retry" onClick={loadInfo}>{t("common.retry")}</button></div>}
          {mineError && <div className="mb-3 rounded-[10px] m-note-err px-3 py-2 text-sm" data-testid="topup-requests-error">{t("topup.requests_fail")} <button className="underline" data-testid="topup-requests-retry" onClick={loadMine}>{t("common.retry")}</button></div>}

          {tab === "rubles" && <RubTopUp onDone={() => onOpenChange(false)} />}
          {tab === "crypto" && <CryptoTopUp onChanged={loadMine} />}
          {tab === "skins" && <AmountStep ready={Boolean(info?.receivers?.length) && !chatBusy} minRap={info?.min_rap ?? 200} rap={rap} setRap={setRap} onNext={startDepositChat} hint={t("chat.deposit_hint")} />}
          {tab === "requests" && (authUser ? <MyRequests items={mine} onChanged={loadMine} onNew={() => setTab("skins")} /> : <div className="m-box h-[160px] flex items-center justify-center text-[13px] text-[#7d8194]" data-testid="my-requests-guest">{t("topup.guest_requests")}</div>)}
        </div>
      </DialogContent>
    </Dialog>
  );
}
