import React, { useCallback, useEffect, useRef, useState } from "react";
import { Coins } from "lucide-react";
import { toast } from "sonner";
import { adminApi, formatMoney, parseServerDate } from "../../lib/api";
import { Card, Field, Btn } from "./chat/ui";

const storageKey = (id) => `admin-coin-grant:${id}`;
const readPending = (id) => {
  try { return JSON.parse(sessionStorage.getItem(storageKey(id))) || null; } catch { return null; }
};

export default function CoinGrantCard({ user, onChanged }) {
  const [pending, setPending] = useState(() => readPending(user.session_id));
  const [amount, setAmount] = useState(() => readPending(user.session_id)?.amount || "");
  const [note, setNote] = useState(() => readPending(user.session_id)?.note || "");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const locked = useRef(false);
  const load = useCallback(() => adminApi.coinGrants(user.session_id).then(setHistory).catch(() => {}), [user.session_id]);
  useEffect(() => { load(); }, [load]);
  const value = Number(amount);
  const valid = /^\d+(?:\.\d{1,2})?$/.test(amount) && value > 0 && value <= 2 ** 45;
  const grant = async () => {
    if (locked.current || !valid) return;
    locked.current = true; setBusy(true);
    let result;
    try {
      const op = pending || { request_id: crypto.randomUUID(), amount, note: note.trim() };
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
    } finally { locked.current = false; setBusy(false); }
    if (result) { load(); onChanged?.(result); }
  };
  return <Card title="Начислить монеты" icon={Coins} testId="admin-coin-grant">
    <div className="space-y-3">
      <p className="text-[12px] text-[#a4a7b8]">Игрок: <b className="text-white">{user.nickname}</b> · Discord {user.discord_id}</p>
      <p className="text-[11px] text-[#8e91a3]">На баланс поступит вся указанная сумма, без комиссии и лимита выдачи из банка.</p>
      <Field label="Количество монет">
        <input aria-label="Количество монет" inputMode="decimal" value={amount} disabled={busy || Boolean(pending)} onChange={(e) => { const v = e.target.value.replace(",", "."); if (/^\d*(?:\.\d{0,2})?$/.test(v)) setAmount(v); }} placeholder="0" className="w-full rounded-xl bg-white/[0.05] px-3 py-3 outline-none tabular-nums" />
      </Field>
      {value > 2 ** 45 && <p className="text-[12px] text-[#ff8a8a]">Сумма выходит за технический диапазон баланса.</p>}
      <input aria-label="Заметка к начислению" value={note} maxLength={200} disabled={busy || Boolean(pending)} onChange={(e) => setNote(e.target.value)} placeholder="Заметка: DonationAlerts, подарок…" className="w-full rounded-xl bg-white/[0.05] px-3 py-3 outline-none text-[12px]" />
      {pending && !busy && <p className="text-[12px] text-[#ffcf5a]">Есть незавершённый запрос на {formatMoney(pending.amount)} монет. Повтор безопасен, даже если сумма уже зачислена.</p>}
      <Btn tone="success" className="w-full" onClick={grant} disabled={busy || !valid}>{busy ? "Начисление…" : pending ? "Повторить запрос" : valid ? `Начислить ${formatMoney(value)} монет` : "Начислить"}</Btn>
      {history.length > 0 && <div className="border-t border-white/[0.06] pt-3 space-y-2">
        <div className="text-[11px] text-[#8e91a3]">Последние ручные начисления</div>
        {history.map((r) => <div key={r.id} className="text-[11px] text-[#a4a7b8] break-words">
          <b className={r.status === "completed" ? "text-[#7ee2a8]" : "text-[#ffcf5a]"}>{r.status === "completed" ? "+" : ""}{formatMoney(r.amount)}</b> · {r.status === "completed" ? "Зачислено" : r.status === "rejected" ? "Отклонено" : "Обрабатывается"} · {parseServerDate(r.created_at).toLocaleString("ru-RU")}{r.note && <div>{r.note}</div>}
        </div>)}
      </div>}
    </div>
  </Card>;
}
