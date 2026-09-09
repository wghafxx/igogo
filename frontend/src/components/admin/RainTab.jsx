import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { adminApi, formatMoney } from "../../lib/api";

const Num = ({ label, hint, value, setValue, step = "1", testId }) => (
  <label className="block" data-testid={testId}>
    <div className="text-[12px] font-bold">{label}</div>
    <input
      type="number" step={step} value={value}
      onChange={(e) => setValue(e.target.value)}
      className="mt-1 h-9 w-full rounded-lg bg-[#0f1015] px-3 text-[13px] font-bold outline-none border border-[#23242e] focus:border-[#00a2ff]"
    />
    {hint && <div className="text-[11px] text-[#5f6377] mt-0.5">{hint}</div>}
  </label>
);

export default function RainTab({ refreshKey }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ pool_threshold: "", budget_min_pct: "", budget_max_pct: "", min_bet: "", timeout_min: "" });
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    adminApi.rains().then((v) => {
      setData(v);
      const s = v.settings || {};
      setForm({
        pool_threshold: s.pool_threshold ?? "",
        budget_min_pct: Math.round((s.budget_min_pct ?? 0.2) * 100),
        budget_max_pct: Math.round((s.budget_max_pct ?? 0.3) * 100),
        min_bet: s.min_bet ?? "",
        timeout_min: s.timeout_min ?? "",
      });
      setEnabled(s.enabled !== false);
    }).catch((e) => toast.error(e?.response?.data?.detail || "Не удалось загрузить дожди"));
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);

  const save = async () => {
    setBusy(true);
    try {
      const payload = {
        enabled,
        pool_threshold: Number(form.pool_threshold),
        budget_min_pct: Number(form.budget_min_pct) / 100,
        budget_max_pct: Number(form.budget_max_pct) / 100,
        min_bet: Number(form.min_bet),
        timeout_min: parseInt(form.timeout_min, 10),
      };
      const s = await adminApi.saveRainSettings(payload);
      toast.success("Настройки дождя сохранены");
      load();
      void s;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ошибка сохранения");
    } finally {
      setBusy(false);
    }
  };

  const closeActive = async () => {
    setBusy(true);
    try {
      const r = await adminApi.rainClose();
      toast.success(r.ok ? `Закрыто, в пул вернулось ${formatMoney(r.returned)}` : "Нет активной раздачи");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ошибка");
    } finally {
      setBusy(false);
    }
  };

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const active = (data?.rains || []).find((r) => r.status === "active");

  return (
    <div className="space-y-4" data-testid="rain-tab">
      <div className="rounded-lg bg-[#00a2ff]/10 border border-[#00a2ff]/40 px-3 py-2.5 text-[12px] text-[#b4d9ff] leading-snug">
        <b>Дождь по котлу, не по времени.</b> Как только свободный пул ≥ порога — резервируется 20-30% рандомно, режется на 4 куска по случайной схеме из 6.
        Следующие 4 прокрута от 4 разных акков (ставка от min_bet), которые слились, получают куски на баланс. Один акк — один кусок. Невостребованное по таймауту возвращается в пул. Обычные победы идут из остатка и не трогают резерв.
      </div>

      <div className="blox-panel p-4 space-y-3" data-testid="rain-settings">
        <div className="flex items-center justify-between">
          <div className="font-bold text-[14px]">Настройки</div>
          <button onClick={() => setEnabled((v) => !v)} className={`h-8 px-3 rounded-md text-[12px] font-bold ${enabled ? "bg-[#2ecc71] text-black" : "bg-[#23242e] text-[#8e91a3]"}`} data-testid="rain-enabled-toggle">
            {enabled ? "Включён" : "Выключен"}
          </button>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <Num label="Порог пула" hint="старт раздачи" value={form.pool_threshold} setValue={set("pool_threshold")} testId="rain-threshold" />
          <Num label="Бюджет мин %" hint="20 = 20%" value={form.budget_min_pct} setValue={set("budget_min_pct")} testId="rain-min-pct" />
          <Num label="Бюджет макс %" hint="30 = 30%" value={form.budget_max_pct} setValue={set("budget_max_pct")} testId="rain-max-pct" />
          <Num label="Мин. ставка" hint="вход в раздачу" value={form.min_bet} setValue={set("min_bet")} testId="rain-min-bet" />
          <Num label="Таймаут, мин" hint="возврат остатка" value={form.timeout_min} setValue={set("timeout_min")} testId="rain-timeout" />
        </div>
        <div className="flex gap-2">
          <button onClick={save} disabled={busy} className="h-9 px-4 rounded-lg bg-[#ffb000] text-black font-bold text-[13px] disabled:opacity-50" data-testid="rain-save">Сохранить</button>
          {active && <button onClick={closeActive} disabled={busy} className="h-9 px-4 rounded-lg bg-[#23242e] font-bold text-[13px] disabled:opacity-50" data-testid="rain-close">Закрыть активную и вернуть остаток</button>}
        </div>
        <div className="text-[12px] text-[#8e91a3]">Свободный пул сейчас: <b className="text-white">{formatMoney(data?.pool ?? 0)}</b></div>
      </div>

      <div className="blox-panel p-4 space-y-2" data-testid="rain-history">
        <div className="font-bold text-[14px]">Последние раздачи</div>
        {(data?.rains || []).length === 0 && <div className="text-[12px] text-[#5f6377]">Пока не было</div>}
        {(data?.rains || []).map((r) => (
          <div key={r.id} className="rounded-lg bg-[#0f1015] px-3 py-2 text-[12px] flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className={`font-black ${r.status === "active" ? "text-[#00a2ff]" : "text-[#2ecc71]"}`}>{r.status === "active" ? "Активна" : "Закрыта"}</span>
            <span className="text-[#8e91a3]">схема {(r.scheme || []).join("/")}</span>
            <span>бюджет <b>{formatMoney(r.budget)}</b></span>
            <span className="text-[#8e91a3]">куски: {(r.slices || []).map((s) => (s.session_id ? `✓${formatMoney(s.amount)}` : formatMoney(s.amount))).join(" · ")}</span>
            {Number(r.returned_amount) > 0 && <span className="text-[#8e91a3]">возврат {formatMoney(r.returned_amount)}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
