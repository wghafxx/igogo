import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { PencilLine, Trash2 } from "lucide-react";
import { adminApi, formatMoney } from "../../lib/api";
import { Card, Field, Btn } from "./chat/ui";
import DepositConfirmDialog from "./DepositConfirmDialog";

const errText = (e) => e?.response?.data?.detail || "Ошибка";

export default function PlayerEditCard({ user, onChanged }) {
  const [data, setData] = useState(null);
  const [balance, setBalance] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const load = useCallback(() => adminApi.playerInventory(user.session_id).then((d) => { setData(d); setBalance(String(d.balance)); }).catch((e) => toast.error(errText(e))), [user.session_id]);
  useEffect(() => { load(); }, [load, user.balance, user.skins_count]);
  const value = Number(balance);
  const valid = /^\d+(?:\.\d{1,2})?$/.test(balance) && value <= 2 ** 45;
  const run = async () => {
    if (!confirm || busy) return;
    setBusy(true);
    try {
      const d = confirm.kind === "balance" ? await adminApi.setBalance(user.session_id, value, "") : await adminApi.removeSkin(user.session_id, confirm.skin.uid, "");
      setData(d); setBalance(String(d.balance));
      toast.success(confirm.kind === "balance" ? `Баланс: ${formatMoney(d.balance)}` : `Удалён ${confirm.skin.name}`);
      onChanged?.(d);
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); setConfirm(null); }
  };
  const skins = data?.skins || [];
  return <Card title="Баланс и инвентарь" icon={PencilLine} testId="admin-player-edit">
    <div className="space-y-3">
      <Field label={`Установить баланс · сейчас ${data ? formatMoney(data.balance) : "…"}`}>
        <div className="flex gap-2">
          <input aria-label="Новый баланс" inputMode="decimal" value={balance} disabled={busy || !data} onChange={(e) => { const v = e.target.value.replace(",", "."); if (/^\d{0,14}(?:\.\d{0,2})?$/.test(v)) setBalance(v); }} className="flex-1 min-w-0 rounded-xl bg-white/[0.05] px-3 h-11 outline-none tabular-nums font-bold" data-testid="admin-player-balance-input" />
          <Btn tone="success" className="h-11" disabled={busy || !data || !valid || value === data?.balance} onClick={() => setConfirm({ kind: "balance" })} data-testid="admin-player-balance-save">Сохранить</Btn>
        </div>
      </Field>
      <div className="text-[11px] text-[#8e91a3]">Инвентарь · {skins.length} шт.</div>
      {skins.length === 0 ? <div className="h-12 flex items-center justify-center text-[12px] text-[#6b6f84]" data-testid="admin-player-inventory-empty">Инвентарь пуст</div> : (
        <div className="space-y-1.5 max-h-[280px] overflow-y-auto pr-1" data-testid="admin-player-inventory">
          {skins.map((s) => <div key={s.uid} className="flex items-center gap-3 rounded-xl bg-white/[0.04] px-3 py-2" data-testid="admin-player-skin-row">
            <span className="w-9 h-9 rounded-lg bg-black/30 flex items-center justify-center shrink-0">{s.image && <img src={s.image} alt="" className="w-8 h-8 object-contain" />}</span>
            <span className="flex-1 min-w-0"><span className="block text-[12px] font-bold truncate">{s.name}</span><span className="block text-[11px] text-[#8e91a3] truncate">{s.type}</span></span>
            <span className="text-[12px] font-black text-[#ffcf5a] tabular-nums shrink-0">{formatMoney(s.price)}</span>
            <button type="button" onClick={() => setConfirm({ kind: "skin", skin: s })} disabled={busy} title="Удалить скин" className="w-8 h-8 rounded-lg text-[#8e91a3] hover:bg-[#ff5c5c]/15 hover:text-[#ff8a8a] flex items-center justify-center disabled:opacity-40 shrink-0 transition-colors" data-testid={`admin-player-skin-remove-${s.uid}`}><Trash2 size={14} /></button>
          </div>)}
        </div>
      )}
      <DepositConfirmDialog open={Boolean(confirm)} busy={busy} onClose={() => setConfirm(null)} onConfirm={run}
        confirmLabel={confirm?.kind === "skin" ? "Да, удалить" : "Да, сохранить"} busyLabel="Сохранение…"
        description={confirm?.kind === "skin" ? `Удалить у ${user.nickname} скин ${confirm.skin.name} (${formatMoney(confirm.skin.price)})?` : confirm ? `Установить ${user.nickname} баланс ${formatMoney(value)} (сейчас ${formatMoney(data?.balance)})?` : ""} />
    </div>
  </Card>;
}
