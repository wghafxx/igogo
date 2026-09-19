import React, { useState } from "react";
import { toast } from "sonner";
import { CheckCheck, XCircle, Wallet } from "lucide-react";
import { adminApi, formatMoney, pct, DEPOSIT_FEE, DEPOSIT_REJECTION_REASONS } from "../../lib/api";
import { RobuxIcon } from "../Logo";
import { DepositAllocationPreview, MIN_DEPOSIT_RAP } from "./DepositAllocationPreview";

export default function ChatDepositPanel({ chatId, user, deposits, onChanged }) {
  const pending = deposits.find((d) => d.status === "pending");
  const processing = deposits.find((d) => d.status === "processing");
  const [rap, setRap] = useState(processing ? String(processing.rap) : pending?.expected_rap ? String(pending.expected_rap) : "");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const value = Number(rap) || 0;
  const bonus = Math.min(0.5, Math.max(0, Number(user?.promo_bonus) || 0));
  const net = value * (1 - DEPOSIT_FEE);
  const credited = Math.round(net * (1 + bonus) * 100) / 100;
  const run = async (fn, msg) => {
    if (busy) return;
    setBusy(true);
    try { await fn(); toast.success(msg); onChanged(); } catch (e) { toast.error(e?.response?.data?.detail || "Ошибка"); } finally { setBusy(false); }
  };
  if (!user) return <div className="rounded-2xl bg-[#0f1015] p-4 text-[12px] text-[#8e91a3]" data-testid="admin-chat-deposit-guest">Гость — пополнение недоступно. Попросите игрока войти через Discord.</div>;
  return (
    <div className="rounded-2xl bg-[#0f1015] p-4 space-y-3" data-testid="admin-chat-deposit">
      <div className="flex items-center gap-2">
        <span className="w-8 h-8 rounded-xl bg-[#2ecc71]/15 text-[#2ecc71] flex items-center justify-center"><Wallet size={15} /></span>
        <div className="text-[13px] font-black">Пополнить игроку</div>
        {pending && <span className="ml-auto text-[11px] font-bold text-[#ffb000] bg-[#ffb000]/15 rounded px-2 py-0.5" data-testid="admin-chat-deposit-expected">заявлено ~{formatMoney(pending.expected_rap)} RAP</span>}
        {processing && <span className="ml-auto text-[11px] font-bold text-[#00a2ff] bg-[#00a2ff]/15 rounded px-2 py-0.5">выдача {formatMoney(processing.rap)} RAP не завершена</span>}
      </div>
      <div className="flex items-center gap-2 h-12 px-4 rounded-xl bg-[#16171d] focus-within:ring-1 focus-within:ring-[#2ecc71]">
        <RobuxIcon size={14} />
        <input value={rap} disabled={busy || Boolean(processing)} inputMode="decimal" onChange={(e) => { const v = e.target.value.replace(",", "."); if (/^\d{0,7}(\.\d{0,2})?$/.test(v)) setRap(v); }} placeholder="Полный RAP полученных скинов" className="flex-1 min-w-0 bg-transparent outline-none text-[15px] font-black" data-testid="admin-chat-rap-input" />
        <span className="text-[11px] text-[#5f6377]">мин. {MIN_DEPOSIT_RAP}</span>
      </div>
      {value > 0 && value < MIN_DEPOSIT_RAP && <div className="text-[11px] text-[#ff8a8a]" data-testid="admin-chat-credit-preview">Меньше {MIN_DEPOSIT_RAP} RAP — зачислить нельзя</div>}
      {value >= MIN_DEPOSIT_RAP && (
        <div className="text-[12px] text-[#8e91a3]" data-testid="admin-chat-credit-preview">
          {formatMoney(value)} − 20% = {formatMoney(net)}{bonus > 0 && <> → +{pct(bonus)}% промо</>} = <b className="text-[#2ecc71]">{formatMoney(credited)} RAP</b>
        </div>
      )}
      <DepositAllocationPreview chatId={chatId} depositId={chatId} rap={value} onReady={setReady} />
      <input value={note} disabled={busy} onChange={(e) => setNote(e.target.value.slice(0, 200))} placeholder="Заметка для банка (необязательно)" className="w-full h-10 px-3 rounded-xl bg-[#16171d] outline-none text-[12px]" data-testid="admin-chat-note-input" />
      <div className="flex flex-wrap gap-2">
        <button onClick={() => run(() => adminApi.chatDeposit(chatId, value, note), "Пополнено: скины в инвентаре, остаток на балансе, банк обновлён")} disabled={busy || value < MIN_DEPOSIT_RAP || value > 1000000 || !ready} className="flex-1 min-w-[180px] h-11 px-4 rounded-xl bg-[#2ecc71] hover:bg-[#3ddb80] text-black font-bold text-[13px] disabled:opacity-40 inline-flex items-center justify-center gap-2 transition-colors" data-testid="admin-chat-confirm-button">
          <CheckCheck size={15} /> {processing ? "Завершить выдачу" : "Пополнить и выдать"}
        </button>
        {pending && (
          <div className="flex gap-2 flex-1 min-w-[220px]">
            <select value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy} className="flex-1 h-11 px-2 rounded-xl bg-[#16171d] text-[11px] outline-none" data-testid="admin-chat-reject-reason">
              <option value="">Причина отклонения…</option>
              {Object.entries(DEPOSIT_REJECTION_REASONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <button onClick={() => run(() => adminApi.reject(pending.id, reason), "Заявка отклонена")} disabled={busy || !reason} className="h-11 px-3 rounded-xl bg-[#ff5c5c]/15 text-[#ff8a8a] hover:bg-[#ff5c5c] hover:text-white font-bold text-[11px] disabled:opacity-40 inline-flex items-center gap-1 transition-colors" data-testid="admin-chat-reject-button">
              <XCircle size={13} /> Отклонить
            </button>
          </div>
        )}
      </div>
      <p className="text-[10px] text-[#7d8194]">Комиссия 20% и промокод учитываются автоматически, до 5 скинов подбираются из каталога, остаток — на баланс, сумма уходит в банк.</p>
    </div>
  );
}
