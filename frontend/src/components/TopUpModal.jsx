import React, { useEffect, useState } from "react";
import { CheckIcon } from "./icons/check";
import { TicketIcon } from "./icons/ticket";
import { BoxesIcon } from "./icons/boxes";
import { FileTextIcon } from "./icons/file-text";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { api, pct } from "../lib/api";
import { useAuth } from "../hooks/useAuth";
import AmountStep from "./topup/AmountStep";
import ReceiverStep from "./topup/ReceiverStep";
import MyRequests from "./topup/MyRequests";

export const PromoInput = ({ compact = false }) => {
  const { authUser, setAuthUser } = useAuth();
  const [code, setCode] = useState(authUser?.promo_code || "");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (authUser?.promo_code) setCode(authUser.promo_code);
  }, [authUser?.promo_code]);
  const active = authUser?.promo_code && authUser.promo_code === code.trim().toUpperCase();

  const apply = async () => {
    if (!code.trim() || busy) return;
    setBusy(true);
    try {
      const u = await api.applyPromo(code.trim());
      setAuthUser(u);
      toast.success(`Промокод ${u.promo_code} активирован: +${pct(u.promo_bonus)}% к пополнению`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Промокод не найден");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="promo-block">
      <div className="flex items-center gap-2 h-12 px-3 rounded-lg bg-[#0f1015]">
        <TicketIcon size={16} className="text-[#ffb000] shrink-0" />
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && apply()}
          placeholder="Введите промокод"
          maxLength={32}
          className="flex-1 min-w-0 bg-transparent outline-none text-[13px] font-bold tracking-wide placeholder:font-normal placeholder:text-[#5f6377]"
          data-testid="promo-input"
        />
        <button
          onClick={apply}
          disabled={busy || !code.trim() || !authUser}
          className={`h-8 px-3 rounded-md text-[12px] font-bold transition-colors ${active ? "bg-[#2ecc71] text-black" : "bg-[#00a2ff] text-white hover:bg-[#1ab0ff]"} disabled:opacity-40`}
          data-testid="promo-apply-button"
        >
          {active ? <CheckIcon size={16} /> : "Применить"}
        </button>
      </div>
      {authUser?.promo_bonus > 0 && !compact && (
        <div className="mt-2 h-8 rounded-md bg-[#ffb000]/15 text-[#ffb000] text-[12px] font-bold flex items-center justify-center uppercase tracking-wide" data-testid="promo-bonus">
          +{pct(authUser.promo_bonus)}% к депозиту
        </div>
      )}
    </div>
  );
};

const STATUS = {
  pending: ["Ожидает проверки", "text-[#ffb000]"],
  processing: ["Начисляется", "text-[#ffb000]"],
  confirmed: ["Зачислено", "text-[#2ecc71]"],
  rejected: ["Отклонено", "text-[#ff5c5c]"],
  cancelled: ["Отменена", "text-[#9a9db0]"],
};

export const DepositStatus = ({ status }) => {
  const [label, cls] = STATUS[status] || [status, ""];
  return <span className={`font-bold ${cls}`}>{label}</span>;
};

export default function TopUpModal({ open, onOpenChange }) {
  const { authUser } = useAuth();
  const [info, setInfo] = useState(null);
  const [tab, setTab] = useState("skins");
  const [step, setStep] = useState("amount");
  const [rap, setRap] = useState("");
  const [mine, setMine] = useState([]);
  const [infoError, setInfoError] = useState(false);
  const [mineError, setMineError] = useState(false);
  const loadInfo = () => { setInfoError(false); api.depositInfo().then(setInfo).catch(() => setInfoError(true)); };

  const loadMine = () => authUser && api.myDeposits().then((rows) => { setMine(rows); setMineError(false); }).catch(() => setMineError(true));
  useEffect(() => {
    if (open && !info) loadInfo();
    if (open) loadMine();
    if (!open) {
      setStep("amount");
      setTab("skins");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, authUser]);
  useEffect(() => {
    if (!open || !authUser) return;
    const timer = setInterval(loadMine, 15000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, authUser?.session_id]);

  const pendingCount = mine.filter((d) => ["pending", "processing"].includes(d.status)).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1e1f23] border-0 text-white sm:max-w-[480px] p-0 overflow-hidden rounded-2xl max-h-[92vh] flex flex-col" data-testid="topup-dialog">
        <DialogHeader className="px-6 py-4 border-b border-[#2a2b31] shrink-0">
          <DialogTitle className="text-[17px] font-bold text-left">Пополнение скинами</DialogTitle>
        </DialogHeader>

        <div className="px-6 pt-4 pb-6 space-y-4 overflow-y-auto">
          {infoError && <div className="text-sm text-[#ff8a8a]" data-testid="topup-info-error">Не удалось загрузить данные пополнения. <button data-testid="topup-info-retry" onClick={loadInfo}>Повторить</button></div>}
          {mineError && <div className="text-sm text-[#ff8a8a]" data-testid="topup-requests-error">Не удалось загрузить заявки. <button data-testid="topup-requests-retry" onClick={loadMine}>Повторить</button></div>}
          <div className="grid grid-cols-2 rounded-lg bg-[#0f1015] p-1">
            <button onClick={() => setTab("skins")} className={`h-9 rounded-md flex items-center justify-center gap-2 text-[13px] font-bold transition-colors ${tab === "skins" ? "bg-[#2a2b31] text-white" : "text-[#8e91a3] hover:text-white"}`} data-testid="topup-tab-skins">
              <BoxesIcon size={14} /> Скины
            </button>
            <button onClick={() => setTab("requests")} className={`h-9 rounded-md flex items-center justify-center gap-2 text-[13px] font-bold transition-colors ${tab === "requests" ? "bg-[#2a2b31] text-white" : "text-[#8e91a3] hover:text-white"}`} data-testid="topup-tab-requests">
              <FileTextIcon size={14} /> Мои заявки
              {pendingCount > 0 && <span className="h-5 min-w-5 px-1.5 rounded-full bg-[#ffb000] text-black text-[11px] font-black flex items-center justify-center" data-testid="topup-pending-badge">{pendingCount}</span>}
            </button>
          </div>

          {tab === "skins" && step === "amount" && <AmountStep ready={Boolean(info?.receivers?.length)} minRap={info?.min_rap ?? 20} rap={rap} setRap={setRap} onNext={() => setStep("receiver")} />}
          {tab === "skins" && step === "receiver" && (
            <ReceiverStep
              receivers={info?.receivers || []}
              rap={rap}
              onBack={() => setStep("amount")}
              onDone={() => { setRap(""); setStep("amount"); loadMine(); setTab("requests"); }}
            />
          )}
          {tab === "requests" && (authUser ? <MyRequests items={mine} onChanged={loadMine} onNew={() => { setTab("skins"); setStep("amount"); }} /> : <div className="h-[140px] flex items-center justify-center text-[13px] text-[#5f6377]" data-testid="my-requests-guest">Войдите, чтобы видеть заявки</div>)}

          <div className="text-[11px] text-[#5f6377] text-center leading-snug">Проверка обычно занимает до 30 минут. Вопросы — в Telegram t.me/bloxgrade.</div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
