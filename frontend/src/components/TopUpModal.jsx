import React, { useEffect, useState } from "react";
import { BoxesIcon } from "./icons/boxes";
import { FileTextIcon } from "./icons/file-text";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { api } from "../lib/api";
import { EVENTS, onEvent, openLiveChat } from "../lib/events";
import { useLang } from "../lib/i18n";
import { useAuth } from "../hooks/useAuth";
import AmountStep from "./topup/AmountStep";
import RubTopUp from "./topup/RubTopUp";
import CryptoTopUp from "./topup/CryptoTopUp";
import { HandCoinsIcon } from "./icons/hand-coins";
import { WalletIcon } from "./icons/wallet";
import MyRequests from "./topup/MyRequests";
import RobloxProfileStepper from "./RobloxProfileStepper";
import { hasRobloxProfile } from "../lib/roblox";

export { PromoInput } from "./topup/PromoInput";
export { DepositStatus } from "./DepositStatus";

export default function TopUpModal({ open, onOpenChange }) {
  const { authUser, openAuth } = useAuth();
  const { t } = useLang();
  const [info, setInfo] = useState(null);
  const [tab, setTab] = useState("skins");
  const [rap, setRap] = useState("");
  const [mine, setMine] = useState([]);
  const [infoError, setInfoError] = useState(false);
  const [mineError, setMineError] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const profileRequired = tab !== "requests" && !hasRobloxProfile(authUser);
  const startDepositChat = async () => {
    if (chatBusy || !hasRobloxProfile(authUser)) return;
    setChatBusy(true);
    try {
      const created = await api.createChat({ kind: "deposit", expected_rap: Number(rap) });
      toast.success(t("chat.deposit_created"));
      setRap("");
      loadMine();
      onOpenChange(false);
      openLiveChat(created.id);
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
  }, [open, authUser?.session_id]);
  useEffect(() => {
    const openRub = () => { setTab("rubles"); onOpenChange(true); };
    const openCrypto = () => { setTab("crypto"); onOpenChange(true); };
    const offRub = onEvent(EVENTS.openRubTopUp, openRub);
    const offCrypto = onEvent(EVENTS.openCryptoTopUp, openCrypto);
    return () => { offRub(); offCrypto(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!open || !authUser) return;
    const timer = setInterval(loadMine, 15000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, authUser?.session_id]);

  const pendingCount = mine.filter((d) => ["pending", "processing", "creating", "awaiting_payment"].includes(d.status)).length;
  const activeSkinDeposit = mine.find((d) => ["pending", "processing"].includes(d.status) && !["xrocket", "cryptobot"].includes(d.payment_method));
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

          {profileRequired && (authUser ? <RobloxProfileStepper key={authUser.session_id} required /> : <div className="m-box p-5 space-y-4"><p className="text-[13px] text-white/60">{t("topup.login_and_link")}</p><button className="m-cta" onClick={openAuth}>{t("amount.login")}</button></div>)}
          {!profileRequired && tab === "rubles" && <RubTopUp onDone={() => onOpenChange(false)} />}
          {!profileRequired && tab === "crypto" && <CryptoTopUp onChanged={loadMine} />}
          {!profileRequired && tab === "skins" && (activeSkinDeposit ? <div className="m-box p-4 space-y-3" data-testid="topup-active-skin-request"><b className="text-[14px]">{t("topup.active_request_title")}</b><p className="m-hint">{t("topup.active_request_hint")}</p><button className="m-cta" data-testid="topup-open-request-chat" onClick={() => { onOpenChange(false); openLiveChat(activeSkinDeposit.chat_id); }}>{t("topup.open_chat")}</button><button className="m-chip" data-testid="topup-view-request" onClick={() => setTab("requests")}>{t("topup.view_request")}</button></div> : <AmountStep ready={Boolean(info?.receivers?.length) && !chatBusy && !mineError} minRap={info?.min_rap ?? 200} rap={rap} setRap={setRap} onNext={startDepositChat} hint={t("chat.deposit_hint")} />)}
          {tab === "requests" && (authUser ? <MyRequests items={mine} onChanged={loadMine} onNew={() => setTab("skins")} /> : <div className="m-box h-[160px] flex items-center justify-center text-[13px] text-[#7d8194]" data-testid="my-requests-guest">{t("topup.guest_requests")}</div>)}
        </div>
      </DialogContent>
    </Dialog>
  );
}
