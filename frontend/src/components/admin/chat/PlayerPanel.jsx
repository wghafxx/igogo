import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Wallet, PackageCheck, ExternalLink, Copy, Ban, CheckCheck, XCircle, UserRound, ShieldAlert } from "lucide-react";
import { adminApi, formatMoney, pct, DEPOSIT_FEE, DEPOSIT_REJECTION_REASONS } from "../../../lib/api";
import { DepositAllocationPreview, MIN_DEPOSIT_RAP } from "../DepositAllocationPreview";
import { Avatar, Card, Field, Btn, ago } from "./ui";
import DepositConfirmDialog from "../DepositConfirmDialog";

const QUICK = [200, 250, 500, 1000, 2500];

const copy = (text) => navigator.clipboard?.writeText(text).then(() => toast.success("Скопировано")).catch(() => {});

export const PlayerCard = ({ user }) => (
  <Card title="Игрок" icon={UserRound} testId="admin-chat-userbar">
    <div className="flex items-center gap-3">
      <Avatar src={user.avatar} name={user.nickname} size={48} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2"><span className={`inline-block w-2 h-2 rounded-full shrink-0 ${user.online ? "bg-[#2ecc71] shadow-[0_0_6px_#2ecc71]" : "bg-[#5f6377]"}`} /><span className="text-[14px] font-black truncate">{user.nickname}</span><span className={`text-[10px] font-bold uppercase tracking-wide ${user.online ? "text-[#7ee2a8]" : "text-[#6b6f84]"}`} data-testid="admin-chat-user-online">{user.online ? "онлайн" : "не в сети"}</span></div>
        <button onClick={() => copy(user.discord_id)} className="text-[11px] text-[#8e91a3] hover:text-white inline-flex items-center gap-1 font-mono" title="Скопировать Discord ID">Discord {user.discord_id} <Copy size={10} /></button>
      </div>
    </div>
    <div className="mt-4 grid grid-cols-2 gap-2">
      <div className="rounded-xl bg-white/[0.04] p-3"><div className="text-[10px] uppercase tracking-wide text-[#6b6f84]">Баланс</div><div className="text-[16px] font-black text-[#7ee2a8]" data-testid="admin-chat-balance">{formatMoney(user.balance)}</div></div>
      <div className="rounded-xl bg-white/[0.04] p-3"><div className="text-[10px] uppercase tracking-wide text-[#6b6f84]">Инвентарь</div><div className="text-[16px] font-black">{user.skins_count} <span className="text-[11px] text-[#8e91a3] font-semibold">· {formatMoney(user.skins_total)}</span></div></div>
    </div>
    <div className="mt-3 rounded-xl bg-white/[0.04] p-3 space-y-1">
      <div className="text-[10px] uppercase tracking-wide text-[#6b6f84]">Roblox</div>
      {user.roblox_link ? (
        <div className="flex items-center gap-2 min-w-0">
          <a href={user.roblox_link} target="_blank" rel="noopener noreferrer" className="text-[13px] font-bold text-[#9fd6ff] hover:text-white inline-flex items-center gap-1 truncate" data-testid="admin-chat-roblox-link">{user.roblox_display_name && `${user.roblox_display_name} · `}@{user.roblox_nick} <ExternalLink size={12} /></a>
          <button onClick={() => copy(user.roblox_link)} className="ml-auto text-[#8e91a3] hover:text-white" title="Скопировать ссылку"><Copy size={13} /></button>
        </div>
      ) : <div className="text-[12px] text-[#ff9b9b] inline-flex items-center gap-1"><ShieldAlert size={13} /> Профиль не привязан</div>}
      {user.roblox_link && <div className="text-[11px] text-[#6b6f84] truncate">{user.roblox_link}</div>}
      {user.roblox_link && <div className="text-[10px] text-[#ffcf5a]/80 leading-snug" data-testid="admin-chat-roblox-unverified">Указано игроком: формат проверен, владение аккаунтом и совпадение ника со ссылкой — не подтверждены. Сверьте профиль перед трейдом.</div>}
    </div>
    {user.promo_bonus > 0 && <div className="mt-3 text-[11px] text-[#ffcf5a]">Промокод {user.promo_code} · +{pct(user.promo_bonus)}% к пополнению</div>}
  </Card>
);

export const DepositCard = ({ chatId, user, deposits, onChanged }) => {
  const pending = deposits.filter((d) => d.status === "pending");
  const processing = deposits.find((d) => d.status === "processing");
  const [rap, setRap] = useState(processing ? String(processing.rap) : pending[0]?.expected_rap ? String(pending[0].expected_rap) : "");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const locked = useRef(false);
  // One id per confirmed command: a retry after a lost response returns the first result, never a second credit.
  const commandId = useRef(null);
  const processingId = processing?.id;
  const processingRap = processing?.rap;
  useEffect(() => {
    if (processingId) setRap(String(processingRap));
  }, [processingId, processingRap]);
  const value = Number(rap) || 0;
  const net = value * (1 - DEPOSIT_FEE);
  const bonus = Math.min(0.5, Math.max(0, user.promo_bonus || 0));
  const credited = Math.round(net * (1 + bonus) * 100) / 100;
  const valid = value >= MIN_DEPOSIT_RAP && value <= 1000000;
  const run = async (fn, msg, onSuccess) => {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    try { await fn(); onSuccess?.(); toast.success(msg); onChanged(); } catch (e) { toast.error(e?.response?.data?.detail || "Ошибка"); } finally { locked.current = false; setBusy(false); setConfirmation(null); }
  };
  return (
    <Card title="Пополнение скинами" icon={Wallet} testId="admin-chat-deposit">
      <div className="space-y-3">
        {pending.map((d) => (
          <div key={d.id} className="rounded-xl bg-[#ffb000]/[0.08] border border-[#ffb000]/20 p-3 space-y-2" data-testid={`admin-chat-request-${d.id}`}>
            <div className="flex items-center justify-between text-[12px]"><span className="font-bold text-[#ffcf5a]">{d.payment_method === "donationalerts" ? `DonationAlerts · ${formatMoney(d.declared_amount)} ${d.declared_currency} · «${d.da_phrase || d.da_code}»${d.paid_claimed_at ? " · игрок нажал «оплатил»" : ""}` : `Заявка игрока · ~${formatMoney(d.expected_rap)} RAP`}</span><span className="text-[#8e91a3]">{ago(d.created_at)} назад</span></div>
            <div className="flex gap-2">
              <select value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy} className="flex-1 h-9 px-2 rounded-lg bg-black/30 text-[12px] outline-none" data-testid="admin-chat-reject-reason">
                <option value="">Причина отклонения…</option>
                {Object.entries(DEPOSIT_REJECTION_REASONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <Btn tone="danger" size="sm" className="h-9" onClick={() => run(() => adminApi.reject(d.id, reason), "Заявка отклонена")} disabled={busy || !reason} data-testid="admin-chat-reject-button"><XCircle size={13} /> Отклонить</Btn>
            </div>
          </div>
        ))}
        <Field label="Полный RAP полученных скинов">
          <div className="flex items-center gap-2 h-12 px-4 rounded-xl bg-white/[0.05] focus-within:ring-1 focus-within:ring-[#2ecc71] transition-shadow">
            <input value={rap} disabled={busy || Boolean(processing)} inputMode="decimal" onChange={(e) => { const v = e.target.value.replace(",", "."); if (/^\d{0,7}(\.\d{0,2})?$/.test(v)) setRap(v); }} placeholder="0" className="flex-1 min-w-0 bg-transparent outline-none text-[20px] font-black tabular-nums" data-testid="admin-chat-rap-input" />
            <span className="text-[12px] font-bold text-[#8e91a3]">RAP</span>
          </div>
        </Field>
        <div className="grid grid-cols-5 gap-1.5">
          {QUICK.map((v) => <button key={v} type="button" disabled={busy || Boolean(processing)} onClick={() => setRap(String(v))} className={`h-8 rounded-lg text-[12px] font-bold transition-colors ${value === v ? "bg-white text-black" : "bg-white/[0.05] text-[#a4a7b8] hover:bg-white/[0.1] hover:text-white"}`} data-testid={`admin-chat-quick-${v}`}>{v}</button>)}
        </div>
        {value > 0 && (
          <div className="rounded-xl bg-white/[0.04] p-3 text-[12px] space-y-1" data-testid="admin-chat-credit-preview">
            {!valid ? <div className="text-[#ff8a8a]">Минимум {MIN_DEPOSIT_RAP} RAP</div> : (
              <>
                <div className="flex justify-between text-[#a4a7b8]"><span>Получено</span><span className="tabular-nums">{formatMoney(value)}</span></div>
                <div className="flex justify-between text-[#a4a7b8]"><span>Комиссия 20%</span><span className="tabular-nums">− {formatMoney(value - net)}</span></div>
                {bonus > 0 && <div className="flex justify-between text-[#ffcf5a]"><span>Промо +{pct(bonus)}%</span><span className="tabular-nums">+ {formatMoney(credited - net)}</span></div>}
                <div className="flex justify-between font-black text-[13px] pt-1 border-t border-white/[0.06]"><span>К зачислению</span><span className="text-[#7ee2a8] tabular-nums">{formatMoney(credited)} RAP</span></div>
              </>
            )}
          </div>
        )}
        <DepositAllocationPreview chatId={chatId} rap={value} onReady={setReady} />
        <input value={note} disabled={busy} onChange={(e) => setNote(e.target.value.slice(0, 200))} placeholder="Заметка для банка (необязательно)" className="w-full h-10 px-3 rounded-xl bg-white/[0.05] outline-none text-[12px] placeholder:text-[#6b6f84]" data-testid="admin-chat-note-input" />
        <Btn tone="success" size="lg" className="w-full" onClick={() => { if (!commandId.current || commandId.current.value !== value) commandId.current = { value, id: crypto.randomUUID() }; setConfirmation({ value, credited, note }); }} disabled={busy || !valid || !ready} data-testid="admin-chat-confirm-button">
          <CheckCheck size={16} /> {processing ? "Завершить выдачу" : valid ? `Пополнить на ${formatMoney(credited)} RAP` : "Пополнить"}
        </Btn>
        <DepositConfirmDialog open={Boolean(confirmation)} busy={busy} onClose={() => setConfirmation(null)}
          description={confirmation ? `Игрок: ${user.nickname}. Получено скинов на ${formatMoney(confirmation.value)} RAP.\nК зачислению после комиссии и промокода: ${formatMoney(confirmation.credited)} RAP.` : ""}
          onConfirm={() => confirmation && run(() => adminApi.chatDeposit(chatId, confirmation.value, confirmation.note, commandId.current?.id), "Пополнение выполнено", () => { commandId.current = null; setRap(""); setNote(""); setReady(false); })} />
        <p className="text-[10px] leading-relaxed text-[#6b6f84]">Скины подбираются автоматически (до 5), остаток — на баланс. Полная сумма RAP уходит в банк.</p>
      </div>
    </Card>
  );
};

export const WithdrawCard = ({ chatId, withdrawals, total, onChanged, onCancel }) => {
  const [busy, setBusy] = useState(false);
  const pending = withdrawals.filter((w) => w.status === "pending");
  const doneAll = async () => {
    if (busy || !pending.length) return;
    setBusy(true);
    try { const r = await adminApi.chatWithdrawalsDone(chatId); toast.success(`Выдано ${r.done} шт. на ${formatMoney(r.total)} RAP`); onChanged(); } catch (e) { toast.error(e?.response?.data?.detail || "Ошибка"); } finally { setBusy(false); }
  };
  return (
    <Card title="Вывод скинов" icon={PackageCheck} right={withdrawals.length > 0 && <span className="text-[11px] font-bold text-[#ffcf5a]">{withdrawals.length} шт.</span>} testId="admin-chat-withdrawals">
      {withdrawals.length === 0 ? (
        <div className="h-16 flex items-center justify-center text-[12px] text-[#6b6f84]" data-testid="admin-chat-withdrawals-empty">Нет скинов, ожидающих выдачи</div>
      ) : (
        <div className="space-y-3">
          <div className="space-y-1.5 max-h-[300px] overflow-y-auto pr-1">
            {withdrawals.map((w) => (
              <div key={w.id} className="flex items-center gap-3 rounded-xl bg-white/[0.04] px-3 py-2" data-testid="admin-chat-withdrawal-row">
                <span className="w-10 h-10 rounded-lg bg-black/30 flex items-center justify-center shrink-0">{w.item?.image && <img src={w.item.image} alt="" className="w-9 h-9 object-contain" />}</span>
                <span className="flex-1 min-w-0"><span className="block text-[12px] font-bold truncate">{w.item?.name}</span><span className="block text-[11px] text-[#8e91a3] truncate">{w.item?.type} · ждёт {ago(w.created_at)}{w.status === "cancelling" ? " · отмена…" : w.status === "paying" ? " · выдача…" : ""}</span>{w.recipient?.roblox_nick && <span className={`block text-[10px] truncate ${w.recipient_changed ? "text-[#ff9b9b] font-bold" : "text-[#6b6f84]"}`} data-testid="admin-chat-withdrawal-recipient">Получатель по заявке: @{w.recipient.roblox_nick}{w.recipient_changed ? " · профиль игрока изменён после заявки" : ""}</span>}</span>
                <span className="text-[12px] font-black text-[#ffcf5a] tabular-nums shrink-0">{formatMoney(w.item?.price)}</span>
                <button onClick={() => onCancel(w)} disabled={busy || w.status === "paying"} title="Отменить вывод" className="w-8 h-8 rounded-lg text-[#8e91a3] hover:bg-[#ff5c5c]/15 hover:text-[#ff8a8a] flex items-center justify-center disabled:opacity-40 shrink-0 transition-colors" data-testid="admin-chat-withdrawal-cancel"><Ban size={14} /></button>
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between rounded-xl bg-white/[0.04] px-3 py-2.5 text-[12px]"><span className="text-[#a4a7b8]">Итого к выдаче</span><b className="text-[14px] text-[#ffcf5a] tabular-nums" data-testid="admin-chat-withdrawals-total">{formatMoney(total)} RAP</b></div>
          <Btn tone="primary" size="lg" className="w-full" onClick={doneAll} disabled={busy || !pending.length} data-testid="admin-chat-withdrawals-done-all"><PackageCheck size={16} /> Всё выдано ({pending.length})</Btn>
        </div>
      )}
    </Card>
  );
};
