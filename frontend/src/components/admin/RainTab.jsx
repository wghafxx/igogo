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

// СЕКРЕТНАЯ полоса удачи. Видно только здесь, в админке.
// Игрокам ничего не показывается: они просто крутят апгрейды и выигрывают скины.
export default function RainTab({ refreshKey }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ pool_threshold: "", budget_min_pct: "", budget_max_pct: "", max_single_pct: "", timeout_min: "" });
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
        max_single_pct: Math.round((s.max_single_pct ?? 0.6) * 100),
        timeout_min: s.timeout_min ?? "",
      });
      setEnabled(s.enabled !== false);
    }).catch((e) => toast.error(e?.response?.data?.detail || "Не удалось загрузить"));
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);

  const save = async () => {
    setBusy(true);
    try {
      await adminApi.saveRainSettings({
        enabled,
        pool_threshold: Number(form.pool_threshold),
        budget_min_pct: Number(form.budget_min_pct) / 100,
        budget_max_pct: Number(form.budget_max_pct) / 100,
        max_single_pct: Number(form.max_single_pct) / 100,
        timeout_min: parseInt(form.timeout_min, 10),
      });
      toast.success("Сохранено");
      load();
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
      toast.success(r.ok ? `Закрыто, в пул вернулось ${formatMoney(r.returned)}` : "Нет активной полосы");
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
      <div className="rounded-lg bg-[#ffb000]/10 border border-[#ffb000]/40 px-3 py-2.5 text-[12px] text-[#ffd166] leading-snug">
        <b>Секретно, игрокам не видно.</b> Как только свободный пул ≥ порога — резервируется 20-30% рандомно.
        Пока резерв не кончился, прокруты судятся по показываемому шансу (без комиссии RTP) — игрок видит 50% и реально имеет 50%.
        Призы списываются из резерва. Один приз — не больше 60% остатка резерва, иначе жирный приз идёт по обычным правилам.
        Остаток по таймауту возвращается в пул.
      </div>

      <div className="blox-panel p-4 space-y-3" data-testid="rain-settings">
        <div className="flex items-center justify-between">
          <div className="font-bold text-[14px]">Настройки</div>
          <button onClick={() => setEnabled((v) => !v)} className={`h-8 px-3 rounded-md text-[12px] font-bold ${enabled ? "bg-[#2ecc71] text-black" : "bg-[#23242e] text-[#8e91a3]"}`} data-testid="rain-enabled-toggle">
            {enabled ? "Включена" : "Выключена"}
          </button>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <Num label="Порог пула" hint="старт полосы" value={form.pool_threshold} setValue={set("pool_threshold")} testId="rain-threshold" />
          <Num label="Бюджет мин %" hint="20 = 20%" value={form.budget_min_pct} setValue={set("budget_min_pct")} testId="rain-min-pct" />
          <Num label="Бюджет макс %" hint="30 = 30%" value={form.budget_max_pct} setValue={set("budget_max_pct")} testId="rain-max-pct" />
          <Num label="Макс приз %" hint="% остатка резерва" value={form.max_single_pct} setValue={set("max_single_pct")} testId="rain-max-single" />
          <Num label="Таймаут, мин" hint="возврат остатка" value={form.timeout_min} setValue={set("timeout_min")} testId="rain-timeout" />
        </div>
        <div className="flex gap-2">
          <button onClick={save} disabled={busy} className="h-9 px-4 rounded-lg bg-[#ffb000] text-black font-bold text-[13px] disabled:opacity-50" data-testid="rain-save">Сохранить</button>
          {active && <button onClick={closeActive} disabled={busy} className="h-9 px-4 rounded-lg bg-[#23242e] font-bold text-[13px] disabled:opacity-50" data-testid="rain-close">Закрыть и вернуть остаток</button>}
        </div>
        <div className="text-[12px] text-[#8e91a3]">Свободный пул сейчас: <b className="text-white">{formatMoney(data?.pool ?? 0)}</b></div>
      </div>

      <div className="blox-panel p-4 space-y-2" data-testid="rain-history">
        <div className="font-bold text-[14px]">Последние полосы</div>
        {(data?.rains || []).length === 0 && <div className="text-[12px] text-[#5f6377]">Пока не было</div>}
        {(data?.rains || []).map((r) => (
          <div key={r.id} className="rounded-lg bg-[#0f1015] px-3 py-2 text-[12px] flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className={`font-black ${r.status === "active" ? "text-[#00a2ff]" : "text-[#2ecc71]"}`}>{r.status === "active" ? "Активна" : "Закрыта"}</span>
            <span>бюджет <b>{formatMoney(r.budget)}</b></span>
            <span className="text-[#8e91a3]">потрачено {formatMoney(r.spent)} · осталось {formatMoney(r.left)}</span>
            <span className="text-[#8e91a3]">побед: {(r.wins || []).length}</span>
            {Number(r.returned_amount) > 0 && <span className="text-[#8e91a3]">возврат {formatMoney(r.returned_amount)}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
