import React, { useCallback, useEffect, useRef, useState } from "react";
import { Coins } from "lucide-react";
import { toast } from "sonner";
import { adminApi, formatMoney, parseServerDate } from "../../lib/api";
import { Card, Field, Btn } from "./chat/ui";
import DepositConfirmDialog from "./DepositConfirmDialog";

const COINS_PER_RUB = 2;
const coinAmount = (op) => op.amount_rub != null ? Math.round(Number(op.amount_rub) * 100) * COINS_PER_RUB / 100 : Number(op.amount);
const storageKey = (id) => `admin-coin-grant:${id}`;
const readPending = (id) => {
  try { return JSON.parse(sessionStorage.getItem(storageKey(id))) || null; } catch { return null; }
};

export default function CoinGrantCard({ user, onChanged }) {
  const [pending, setPending] = useState(() => readPending(user.session_id));
  const [amount, setAmount] = useState(() => readPending(user.session_id)?.amount_rub || "");
  const [note, setNote] = useState(() => readPending(user.session_id)?.note || "");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const [confirmation, setConfirmation] = useState(null);
  const locked = useRef(false);
  const load = useCallback(() => adminApi.coinGrants(user.session_id).then(setHistory).catch(() => {}), [user.session_id]);
  useEffect(() => { load(); }, [load]);
  const value = Number(amount);
  const legacyPending = pending && pending.amount_rub == null;
  const credited = pending ? coinAmount(pending) : Math.round(value * 100) * COINS_PER_RUB / 100;
  const valid = Boolean(pending) || (/^\d+(?:\.\d{1,2})?$/.test(amount) && value > 0 && credited <= 2 ** 45);
  const confirm = () => {
    if (!valid || locked.current) return;
    setConfirmation(pending || { request_id: crypto.randomUUID(), amount_rub: amount, note: note.trim() });
  };
  const grant = async () => {
    if (locked.current || !confirmation) return;
    locked.current = true; setBusy(true);
    let result;
    try {
      const op = confirmation;
      // Save before sending, so timeout, navigation and reload all reuse the same ID.
      sessionStorage.setItem(storageKey(user.session_id), JSON.stringify(op));
      setPending(op);
      result = await adminApi.grantCoins(user.session_id, op);
      sessionStorage.removeItem(storageKey(user.session_id));
      setPending(null); setAmount(""); setNote("");
      toast.success(`Начислено ${formatMoney(result.amount)} монет игроку ${user.nickname}`);
    } catch (e) {
      if ([400, 404, 409, 422].includes(e?.response?.status)) {
        sessionStorage.removeItem(storageKey(user.session_id)); setPending(null);
      }
      toast.error(e?.response?.data?.detail || "Ответ не получен. Нажмите «Повторить запрос» — повторного начисления не будет.");
    } finally { locked.current = false; setBusy(false); setConfirmation(null); }
    if (result) { load(); onChanged?.(result); }
  };
  return <Card title="Пополнение монетами" icon={Coins} testId="admin-coin-grant">
    <div className="space-y-3">
      <p className="text-[12px] text-[#a4a7b8]">Игрок: <b className="text-white">{user.nickname}</b> · Discord {user.discord_id}</p>
      <p className="text-[11px] text-[#8e91a3]">Введите сумму, которую игрок уже оплатил в рублях. Курс: 1 ₽ = 2 монеты, без комиссии. Например, 45 ₽ = 90 монет.</p>
      <Field label={legacyPending ? "Монеты по незавершённому запросу" : "Оплачено рублей"}>
        <input aria-label={legacyPending ? "Монеты по незавершённому запросу" : "Оплачено рублей"} inputMode="decimal" value={legacyPending ? pending.amount : amount} disabled={busy || Boolean(pending)} onChange={(e) => { const v = e.target.value.replace(",", "."); if (/^\d*(?:\.\d{0,2})?$/.test(v)) setAmount(v); }} placeholder="0" className="w-full rounded-xl bg-white/[0.05] px-3 py-3 outline-none tabular-nums" />
      </Field>
      {valid && <p className="text-[13px] font-bold text-[#7ee2a8]">К зачислению: {formatMoney(credited)} монет</p>}
      {credited > 2 ** 45 && <p className="text-[12px] text-[#ff8a8a]">Сумма выходит за технический диапазон баланса.</p>}
      <input aria-label="Заметка к начислению" value={note} maxLength={200} disabled={busy || Boolean(pending)} onChange={(e) => setNote(e.target.value)} placeholder="Заметка: DonationAlerts…" className="w-full rounded-xl bg-white/[0.05] px-3 py-3 outline-none text-[12px]" />
      {pending && !busy && <p className="text-[12px] text-[#ffcf5a]">Есть незавершённый запрос на {formatMoney(coinAmount(pending))} монет. Повтор безопасен, даже если сумма уже зачислена.</p>}
      <Btn tone="success" className="w-full" onClick={confirm} disabled={busy || !valid}>{busy ? "Начисление…" : pending ? "Повторить запрос" : valid ? `Начислить ${formatMoney(credited)} монет` : "Начислить"}</Btn>
      <DepositConfirmDialog open={Boolean(confirmation)} busy={busy} onConfirm={grant} onClose={() => setConfirmation(null)}
        description={confirmation ? `Игрок: ${user.nickname}. ${confirmation.amount_rub != null ? `Оплачено: ${formatMoney(Number(confirmation.amount_rub))} ₽.\n` : ""}На баланс поступит ${formatMoney(coinAmount(confirmation))} монет.` : ""} />
      {history.length > 0 && <div className="border-t border-white/[0.06] pt-3 space-y-2">
        <div className="text-[11px] text-[#8e91a3]">Последние ручные начисления</div>
        {history.map((r) => <div key={r.id} className="text-[11px] text-[#a4a7b8] break-words">
          <b className={r.status === "completed" ? "text-[#7ee2a8]" : "text-[#ffcf5a]"}>{r.status === "completed" ? "+" : ""}{formatMoney(r.amount)} монет</b>{r.amount_rub != null && <> · {formatMoney(r.amount_rub)} ₽</>} · {r.status === "completed" ? "Зачислено" : r.status === "rejected" ? "Отклонено" : "Обрабатывается"} · {parseServerDate(r.created_at).toLocaleString("ru-RU")}{r.note && <div>{r.note}</div>}
        </div>)}
      </div>}
    </div>
  </Card>;
}
