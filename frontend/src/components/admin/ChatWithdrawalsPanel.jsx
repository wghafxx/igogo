import React, { useState } from "react";
import { toast } from "sonner";
import { PackageCheck, Ban, ExternalLink } from "lucide-react";
import { adminApi, formatMoney, parseServerDate } from "../../lib/api";
import { skinImg } from "../../lib/img";
import { RobuxIcon } from "../Logo";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../ui/dialog";

const waitingFor = (iso) => {
  const mins = Math.max(0, Math.floor((Date.now() - parseServerDate(iso).getTime()) / 60000));
  if (mins < 60) return `${mins} мин`;
  const h = Math.floor(mins / 60);
  return h < 48 ? `${h} ч` : `${Math.floor(h / 24)} дн`;
};

export default function ChatWithdrawalsPanel({ chatId, user, withdrawals, total, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [cancel, setCancel] = useState(null);
  const [reason, setReason] = useState("");
  const run = async (fn, msg) => {
    if (busy) return false;
    setBusy(true);
    try { await fn(); toast.success(msg); onChanged(); return true; } catch (e) { toast.error(e?.response?.data?.detail || "Ошибка"); return false; } finally { setBusy(false); }
  };
  const pendingCount = withdrawals.filter((w) => w.status === "pending").length;
  return (
    <div className="rounded-2xl bg-[#0f1015] p-4 space-y-3" data-testid="admin-chat-withdrawals">
      <div className="flex items-center gap-2">
        <span className="w-8 h-8 rounded-xl bg-[#ffb000]/15 text-[#ffb000] flex items-center justify-center"><PackageCheck size={15} /></span>
        <div className="text-[13px] font-black">Вывод скинов</div>
        <span className="ml-auto text-[12px] text-[#8e91a3]">{withdrawals.length} шт. · <b className="text-white inline-flex items-center gap-1" data-testid="admin-chat-withdrawals-total">{formatMoney(total)} <RobuxIcon size={11} /></b></span>
      </div>
      {user?.roblox_link ? (
        <a href={user.roblox_link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-[12px] text-[#b4d9ff] hover:text-white" data-testid="admin-chat-roblox-link">Roblox: {user.roblox_nick} <ExternalLink size={12} /></a>
      ) : <div className="text-[12px] text-[#ff9b9b]">Roblox-профиль не привязан</div>}
      {withdrawals.length === 0 ? (
        <div className="text-[12px] text-[#5f6377] py-3 text-center" data-testid="admin-chat-withdrawals-empty">Нет скинов на выводе</div>
      ) : (
        <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
          {withdrawals.map((w) => (
            <div key={w.id} className="flex items-center gap-3 rounded-xl bg-[#16171d] px-3 py-2 text-[12px]" data-testid="admin-chat-withdrawal-row">
              {w.item?.image && <img src={skinImg(w.item.image)} alt="" className="w-9 h-9 object-contain" />}
              <div className="min-w-0 flex-1"><b className="block truncate">{w.item?.name}</b><span className="text-[#7d8194] text-[11px]">{w.item?.type} · ждёт {waitingFor(w.created_at)}</span></div>
              <span className="font-bold tabular-nums inline-flex items-center gap-1">{formatMoney(w.item?.price)} <RobuxIcon size={10} /></span>
              <button onClick={() => { setReason(w.cancellation_reason || ""); setCancel(w); }} disabled={busy} title={w.status === "cancelling" ? "Завершить отмену" : "Отменить вывод"} className="w-8 h-8 rounded-lg bg-[#ff5c5c]/10 text-[#ff8a8a] hover:bg-[#ff5c5c] hover:text-white flex items-center justify-center disabled:opacity-40 transition-colors" data-testid="admin-chat-withdrawal-cancel"><Ban size={13} /></button>
            </div>
          ))}
        </div>
      )}
      {pendingCount > 0 && (
        <button onClick={() => run(() => adminApi.chatWithdrawalsDone(chatId), "Все скины отмечены выданными")} disabled={busy} className="w-full h-11 rounded-xl bg-[#ffb000] hover:bg-[#ffc233] text-black font-bold text-[13px] disabled:opacity-40 inline-flex items-center justify-center gap-2 transition-colors" data-testid="admin-chat-withdrawals-done">
          <PackageCheck size={15} /> Отметить все как выданные ({pendingCount} шт. · {formatMoney(total)} RAP)
        </button>
      )}
      <Dialog open={Boolean(cancel)} onOpenChange={(o) => { if (!o && !busy) setCancel(null); }}>
        <DialogContent className="bg-[#1e1f23] border-0 text-white max-w-[calc(100%-2rem)] sm:max-w-[420px] rounded-xl" data-testid="admin-cancel-withdrawal-dialog">
          <DialogHeader>
            <DialogTitle>Отменить вывод</DialogTitle>
            <DialogDescription className="text-[#8e91a3]">{cancel?.item?.name}. Скин вернётся в инвентарь, игрок увидит причину в чате и профиле.</DialogDescription>
          </DialogHeader>
          <button type="button" onClick={() => setReason("Долгое ожидание")} disabled={busy} className="justify-self-start px-3 py-2 rounded-lg bg-[#ff5c5c]/15 text-[#ff8a8a] text-[12px] font-bold" data-testid="admin-withdrawal-long-wait">Долгое ожидание</button>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy} maxLength={1000} rows={3} placeholder="Причина для игрока…" className="w-full bg-[#0f1015] rounded-lg p-3 outline-none focus:ring-1 focus:ring-[#ff5c5c] resize-y text-[13px]" data-testid="admin-withdrawal-cancel-reason" />
          <div className="flex gap-2">
            <button onClick={() => setCancel(null)} disabled={busy} className="blox-chip h-10 px-4 text-[12px] font-bold text-[#9a9db0]">Назад</button>
            <button disabled={busy || !reason.trim()} onClick={async () => { if (await run(() => adminApi.withdrawalCancel(cancel.id, reason.trim()), "Вывод отменён, скин возвращён")) setCancel(null); }} className="flex-1 h-10 rounded-lg bg-[#ff5c5c] hover:bg-[#ff7373] text-white font-bold text-[12px] disabled:opacity-40" data-testid="admin-withdrawal-cancel-confirm">{busy ? "Отмена…" : "Отменить и вернуть скин"}</button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
