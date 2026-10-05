import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Gift, Save } from "lucide-react";
import { adminApi, formatMoney, parseServerDate } from "../../lib/api";
import { Card, Field, Btn } from "./chat/ui";

const FIELDS = [
  ["g1_pct", "Подарок 1: бонус к пополнению, %", 100],
  ["g1_min_rap", "Подарок 1: пополнение от, RAP"],
  ["g2_min_rap", "Подарок 2 (Glove Case): пополнение от, RAP"],
  ["g3_min_rap", "Подарок 3 (AWP Railgun): пополнение от, RAP"],
  ["g4_min_rap", "Подарок 4 (AK-47 Aniki): пополнение от, RAP"],
  ["commission_share", "Бонус максимум от комиссии этого пополнения, %", 100],
  ["weekly_amount", "Еженедельный бонус, RAP"],
  ["weekly_min_games", "Еженедельный: минимум игр"],
  ["wager_x", "Отыгрыш перед выводом, ×"],
];
const KIND = { g1: "Подарок 1", g2: "Подарок 2", g3: "Подарок 3", g4: "Подарок 4", weekly: "Еженедельный" };
const toForm = (s) => Object.fromEntries(FIELDS.map(([k, , m]) => [k, String(Math.round(s[k] * (m || 1) * 100) / 100)]));

export default function BonusesTab({ refreshKey }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => adminApi.bonuses().then((d) => { setData(d); setForm(toForm(d.settings)); }).catch((e) => toast.error(e?.response?.data?.detail || "Ошибка")), []);
  useEffect(() => { load(); }, [load, refreshKey]);
  const save = async () => {
    setBusy(true);
    try {
      const payload = Object.fromEntries(FIELDS.map(([k, , m]) => [k, Number(form[k]) / (m || 1)]));
      const d = await adminApi.bonusSettings(payload);
      setData(d); setForm(toForm(d.settings)); toast.success("Настройки бонусов сохранены");
    } catch (e) { toast.error(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Проверьте значения"); } finally { setBusy(false); }
  };
  if (!data || !form) return <div className="blox-panel h-40 animate-pulse" />;
  return (
    <div className="grid lg:grid-cols-[1fr_380px] gap-4 items-start" data-testid="admin-bonuses-tab">
      <Card title="Настройки бонусов" icon={Gift} testId="admin-bonus-settings">
        <div className="grid sm:grid-cols-2 gap-3">
          {FIELDS.map(([k, label]) => <Field key={k} label={label}>
            <input inputMode="decimal" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value.replace(",", ".") })} className="w-full rounded-xl bg-white/[0.05] px-3 h-11 outline-none tabular-nums font-bold" data-testid={`admin-bonus-${k}`} />
          </Field>)}
        </div>
        <div className="mt-3 rounded-xl bg-black/30 p-3 text-[12px] text-[#a4a7b8] space-y-1" data-testid="admin-bonus-effective">
          <div className="font-bold text-white">Фактический порог пополнения (комиссия 20% покрывает подарок)</div>
          {data.gifts.map((g) => <div key={g.id} className="flex justify-between gap-2"><span className="truncate">{g.item ? `${g.item.type} | ${g.item.name} · ${formatMoney(g.item.price)}` : `+${Math.round(g.pct * 100)}% к пополнению`}</span><b className="tabular-nums text-[#ffcf5a] shrink-0">от {Math.round(g.min_rap)} RAP</b></div>)}
        </div>
        <Btn tone="success" size="lg" className="w-full mt-3" disabled={busy} onClick={save} data-testid="admin-bonus-save"><Save size={15} /> Сохранить</Btn>
      </Card>
      <div className="space-y-4">
        <Card title="Бюджет бонусов" icon={Gift} testId="admin-bonus-budget">
          <div className="space-y-2 text-[13px]">
            <div className="flex justify-between"><span className="text-[#a4a7b8]">Осталось комиссии</span><b className="tabular-nums text-[#7ee2a8]" data-testid="admin-bonus-commission-left">{formatMoney(data.commission_left)}</b></div>
            <div className="flex justify-between"><span className="text-[#a4a7b8]">Выдано бонусами</span><b className="tabular-nums" data-testid="admin-bonus-spent">{formatMoney(data.spent)} · {data.claims} шт.</b></div>
            <p className="text-[11px] text-[#6b6f84]">Бонусы списываются только из отложенной комиссии. Если её не хватает, бонус не выдаётся.</p>
          </div>
        </Card>
        <Card title="Последние выдачи" icon={Gift} testId="admin-bonus-recent">
          {data.recent.length === 0 ? <div className="text-[12px] text-[#6b6f84]">Пока пусто</div> : <div className="space-y-1.5 max-h-[320px] overflow-y-auto">
            {data.recent.map((r) => <div key={r.id} className="flex items-center gap-2 text-[12px] rounded-lg bg-white/[0.04] px-3 py-2" data-testid="admin-bonus-recent-row">
              <span className="flex-1 min-w-0 truncate font-bold">{r.nickname || "—"}</span><span className="text-[#8e91a3]">{KIND[r.kind] || r.kind}</span>
              <b className="tabular-nums text-[#ffcf5a]">{formatMoney(r.amount)}</b><span className="text-[#6b6f84] w-20 text-right">{parseServerDate(r.at).toLocaleDateString("ru-RU")}</span>
            </div>)}
          </div>}
        </Card>
      </div>
    </div>
  );
}
