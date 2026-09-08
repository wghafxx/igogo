import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { RobuxIcon } from "../Logo";
import { adminApi, formatMoney } from "../../lib/api";

const fmtDate = (d) => new Date(d).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const pct = (v) => `${(Number(v) * 100).toFixed(1)}%`;

const KIND = {
  deposit: ["Депозит", "text-[#2ecc71]"],
  withdrawal: ["Вывод скина", "text-[#ff8a8a]"],
  adjust: ["Корректировка", "text-[#ffb000]"],
  settings: ["Настройка", "text-[#8e91a3]"],
  pool: ["Пул выдачи", "text-[#4b9dff]"],
};

const Stat = ({ label, value, tone = "", testId, hint }) => (
  <div className="blox-panel p-4" data-testid={testId}>
    <div className="text-[10px] uppercase tracking-wider text-[#7d8194]">{label}</div>
    <div className={`text-[20px] font-black mt-1 flex items-center gap-1.5 ${tone}`}>{value}</div>
    {hint && <div className="text-[11px] text-[#5f6377] mt-0.5">{hint}</div>}
  </div>
);

const SETTINGS = [
  { key: "rtp_target", label: "RTP (доля возврата игрокам)", hint: "Шанс = ставка / цена × RTP. Это расчётная вероятность: действующая защита банка может заменить выигрыш проигрышем при нехватке средств или блокировки.", min: 75, max: 100, fmt: (v) => `${v}% · комиссия ${100 - v}%`, to: (v) => v / 100, from: (v) => Math.round(v * 100) },
];

const SettingRow = ({ s, value, onSaved }) => {
  const [v, setV] = useState(s.from(value));
  const [busy, setBusy] = useState(false);
  useEffect(() => setV(s.from(value)), [value, s]);
  const save = async () => {
    setBusy(true);
    try {
      await adminApi.bankSettings({ [s.key]: s.to(v) });
      toast.success(`${s.label}: ${s.fmt(v)}`);
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ошибка");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-1.5" data-testid={`setting-${s.key}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[13px] font-bold">{s.label}</div>
          <div className="text-[11px] text-[#8e91a3]">{s.hint}</div>
        </div>
        <div className="text-[22px] font-black text-[#ffb000] shrink-0" data-testid={`setting-${s.key}-value`}>{s.fmt(v)}</div>
      </div>
      <div className="flex items-center gap-2">
        <input type="range" min={s.min} max={s.max} step={1} value={v} onChange={(e) => setV(Number(e.target.value))} className="flex-1 accent-[#ffb000]" data-testid={`setting-${s.key}-slider`} />
        <button onClick={save} disabled={busy || s.from(value) === v} className="blox-btn-primary h-8 px-3 text-[11px] disabled:opacity-40" data-testid={`setting-${s.key}-save`}>
          Сохранить
        </button>
      </div>
    </div>
  );
};

const RtpControl = ({ settings, onSaved }) => (
  <div className="blox-panel p-4 space-y-4" data-testid="bank-rtp-panel">
    <div className="text-[13px] font-bold">Настройки выдачи</div>
    {SETTINGS.map((s) => <SettingRow key={s.key} s={s} value={settings[s.key]} onSaved={onSaved} />)}
  </div>
);

const AdjustForm = ({ onDone }) => {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (sign) => {
    const v = Number(amount) * sign;
    if (!v || note.trim().length < 2) return;
    setBusy(true);
    try {
      await adminApi.bankAdjust(v, note.trim());
      toast.success(`Банк скорректирован на ${v > 0 ? "+" : ""}${formatMoney(v)}`);
      setAmount("");
      setNote("");
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ошибка");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="blox-panel p-4 space-y-2" data-testid="bank-adjust-panel">
      <div className="text-[13px] font-bold">Ручная корректировка банка</div>
      <div className="text-[11px] text-[#8e91a3]">Только для исправлений: скин ушёл вне сайта, ошибка в сумме и т.п. Каждая правка пишется в журнал.</div>
      <div className="flex items-center gap-2 h-10 px-3 rounded-lg bg-[#0f1015]">
        <RobuxIcon size={13} />
        <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))} placeholder="Сумма RAP" className="flex-1 bg-transparent outline-none text-[13px] font-bold" data-testid="bank-adjust-amount" />
      </div>
      <input value={note} onChange={(e) => setNote(e.target.value.slice(0, 200))} placeholder="Причина (обязательно)" className="w-full h-9 px-3 rounded-lg bg-[#0f1015] outline-none text-[12px]" data-testid="bank-adjust-note" />
      <div className="flex gap-2">
        <button onClick={() => submit(1)} disabled={busy || !Number(amount) || note.trim().length < 2} className="flex-1 h-9 rounded-lg bg-[#2ecc71] text-black font-bold text-[12px] disabled:opacity-40" data-testid="bank-adjust-plus">+ Добавить</button>
        <button onClick={() => submit(-1)} disabled={busy || !Number(amount) || note.trim().length < 2} className="flex-1 h-9 rounded-lg bg-[#ff5c5c] text-white font-bold text-[12px] disabled:opacity-40" data-testid="bank-adjust-minus">− Списать</button>
      </div>
    </div>
  );
};

const PoolForm = ({ onDone }) => {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    const v = Number(amount);
    if (!v || v <= 0 || note.trim().length < 2) return;
    setBusy(true);
    try {
      await adminApi.poolTopup(v, note.trim());
      toast.success(`Пул выдачи пополнен на ${formatMoney(v)}`);
      setAmount("");
      setNote("");
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ошибка");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="blox-panel p-4 space-y-2" data-testid="bank-pool-topup">
      <div className="text-[13px] font-bold">Пополнить пул выдачи</div>
      <div className="text-[11px] text-[#8e91a3]">Бюджет на выигрыши: приз платится, только если в пуле хватает средств. Стартовый пул = RTP × ставки − выдано; здесь можно добавить вручную (рекомендуется ≤ 20% банка).</div>
      <div className="flex items-center gap-2 h-10 px-3 rounded-lg bg-[#0f1015]">
        <RobuxIcon size={13} />
        <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))} placeholder="Сумма RAP" className="flex-1 bg-transparent outline-none text-[13px] font-bold" data-testid="bank-pool-amount" />
      </div>
      <input value={note} onChange={(e) => setNote(e.target.value.slice(0, 200))} placeholder="Причина (обязательно)" className="w-full h-9 px-3 rounded-lg bg-[#0f1015] outline-none text-[12px]" data-testid="bank-pool-note" />
      <button onClick={submit} disabled={busy || !Number(amount) || Number(amount) <= 0 || note.trim().length < 2} className="w-full h-9 rounded-lg bg-[#4b9dff] text-black font-bold text-[12px] disabled:opacity-40" data-testid="bank-pool-submit">
        Пополнить пул
      </button>
    </div>
  );
};

export default function BankTab({ refreshKey = 0 }) {
  const [data, setData] = useState(null);
  const load = useCallback(() => adminApi.bank().then(setData).catch(() => toast.error("Не удалось загрузить банк")), []);
  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load, refreshKey]);

  if (!data) return <div className="blox-panel h-[160px] flex items-center justify-center text-[13px] text-[#5f6377]" data-testid="bank-loading">Загрузка…</div>;

  const { bank, pool, liabilities, net, rtp, games, settings, ledger } = data;
  const rtp24 = data.rtp_24h || null;
  const forcedTop = data.forced_top || [];
  const warnThreshold = 0.2 * (Number(liabilities?.total) || 0);
  const health = net < 0 ? "red" : net < warnThreshold ? "yellow" : "green";
  const bannerCls = {
    red: "bg-[#ff5c5c]/10 border-[#ff5c5c]/40 text-[#ff9b9b]",
    yellow: "bg-[#ffb000]/10 border-[#ffb000]/40 text-[#ffd166]",
    green: "bg-[#2ecc71]/10 border-[#2ecc71]/40 text-[#9be7b8]",
  }[health];
  return (
    <div className="space-y-4" data-testid="bank-tab">
      <div className={`rounded-lg px-3 py-2.5 text-[12px] leading-snug border ${bannerCls}`} data-testid="bank-status-banner">
        <b>Шанс = ставка / цена × {Math.round(settings.rtp_target * 100)}%. Комиссия {Math.round((1 - settings.rtp_target) * 100)}%.</b> Выплаты ограничены пулом выдачи: суммарная выдача никогда не превысит RTP × все ставки. Если пул пуст, выигрыш по роллу тихо засчитывается как проигрыш. Красный — обязательства превышают банк; жёлтый — чистая позиция &lt; 20% обязательств.
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Банк (реальные скины)" value={<>{formatMoney(bank)} <RobuxIcon size={14} /></>} tone="text-[#ffb000]" testId="bank-balance" hint="Σ депозитов − Σ выданных скинов ± правки" />
        <Stat label="Обязательства игрокам" value={<>{formatMoney(liabilities.total)} <RobuxIcon size={14} /></>} testId="bank-liabilities" hint={`балансы ${formatMoney(liabilities.balances)} · инвентари ${formatMoney(liabilities.inventory)} · на выводе ${formatMoney(liabilities.pending_withdrawals)}`} />
        <Stat label="Чистая позиция (прибыль)" value={<>{net >= 0 ? "+" : ""}{formatMoney(net)} <RobuxIcon size={14} /></>} tone={health === "green" ? "text-[#2ecc71]" : health === "yellow" ? "text-[#ffb000]" : "text-[#ff5c5c]"} testId="bank-net" hint="банк − обязательства" />
        <Stat label="Фактический RTP" value={pct(rtp.rtp)} tone={rtp.rtp <= settings.rtp_target + 0.05 ? "text-[#2ecc71]" : "text-[#ffb000]"} testId="bank-rtp-actual" hint={`потолок ${Math.round(settings.rtp_target * 100)}% — выше подняться не может · поставлено ${formatMoney(rtp.wagered)} · выдано ${formatMoney(rtp.paid)}`} />
        <Stat label="Пул выдачи" value={<>{formatMoney(pool ?? 0)} <RobuxIcon size={14} /></>} tone={(pool ?? 0) > 0 ? "text-[#4b9dff]" : "text-[#ff5c5c]"} testId="bank-pool" hint={(pool ?? 0) <= 0 ? "пуст — выигрыши временно не выплачиваются" : "доступный бюджет на выигрыши: пополняется ставками × RTP"} />
        <Stat label="RTP за 24ч" value={pct(rtp24 ? rtp24.rtp : 0)} tone={!rtp24 || rtp24.rtp <= settings.rtp_target + 0.05 ? "text-[#2ecc71]" : "text-[#ffb000]"} testId="bank-rtp-24h" hint={rtp24 ? `поставлено ${formatMoney(rtp24.wagered)} · выдано ${formatMoney(rtp24.paid)}` : "нет данных"} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Всего задепозитили" value={<>{formatMoney(data.deposits_total)} <RobuxIcon size={12} /></>} testId="bank-deposits-total" />
        <Stat label="Всего выведено скинов" value={<>{formatMoney(data.withdrawals_total)} <RobuxIcon size={12} /></>} testId="bank-withdrawals-total" />
        <Stat label="Игр / побед" value={`${games.total} / ${games.wins}`} testId="bank-games" />
        <Stat label="Принудительных проигрышей" value={games.forced_losses} tone="text-[#ff8a8a]" testId="bank-forced-losses" hint={`${games.forced_by?.bank || 0} нехватка банка · ${games.forced_by?.lock || 0} блокировка · ${games.forced_by?.pool || 0} пустой пул · ${(games.forced_by?.player || 0) + (games.forced_by?.rtp || 0)} прежние правила`} />
      </div>

      <div className="blox-panel p-4" data-testid="bank-forced-top">
        <div className="text-[13px] font-bold mb-2">Топ по форс-сливам</div>
        {forcedTop.length === 0 ? (
          <div className="text-[12px] text-[#5f6377]">Пока пусто</div>
        ) : (
          <div className="space-y-1">
            {forcedTop.map((f) => (
              <div key={f.session_id} className="flex items-center gap-3 text-[12px] px-3 py-2 rounded-md bg-[#0f1015]">
                <span className="font-bold flex-1 truncate">{f.nickname}</span>
                <span className="text-[#ff8a8a] font-bold">{f.count}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <RtpControl settings={settings} onSaved={load} />
        <PoolForm onDone={load} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <AdjustForm onDone={load} />
      </div>

      <div className="blox-panel p-4" data-testid="bank-ledger">
        <div className="text-[13px] font-bold mb-3">Журнал операций банка</div>
        {ledger.length === 0 && <div className="text-[12px] text-[#5f6377]" data-testid="bank-ledger-empty">Операций пока нет</div>}
        <div className="space-y-1">
          {ledger.map((l) => {
            const [label, cls] = KIND[l.kind] || [l.kind, ""];
            return (
              <div key={l.id} className="flex flex-wrap items-center gap-3 text-[12px] px-3 py-2 rounded-md bg-[#0f1015]" data-testid="bank-ledger-row">
                <span className="text-[#5f6377] w-28">{fmtDate(l.created_at)}</span>
                <span className={`font-bold w-28 ${cls}`}>{label}</span>
                <span className={`font-bold w-28 ${l.amount >= 0 ? "text-[#2ecc71]" : "text-[#ff8a8a]"}`}>{l.amount >= 0 ? "+" : ""}{formatMoney(l.amount)}</span>
                <span className="flex-1 min-w-[160px] text-[#b4b7c7] truncate">{l.note}</span>
                <span className="text-[#8e91a3]">банк: <b className="text-white">{formatMoney(l.bank_after)}</b></span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
