import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { RobuxIcon } from "../Logo";
import { adminApi, formatMoney, parseServerDate } from "../../lib/api";
import PinConfirmDialog from "./PinConfirmDialog";

const fmtDate = (d) => parseServerDate(d).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const pct = (v) => `${(Number(v) * 100).toFixed(1)}%`;

const KIND = {
  deposit: ["Депозит", "text-[#2ecc71]"],
  withdrawal: ["Вывод скина", "text-[#ff8a8a]"],
  adjust: ["Корректировка", "text-[#ffb000]"],
  settings: ["Настройка", "text-[#8e91a3]"],
  pool: ["Пул выдачи", "text-[#4b9dff]"],
  reset: ["Сброс банка", "text-[#ff5c5c]"],
};

const Stat = ({ label, value, tone = "", testId, hint }) => (
  <div className="blox-panel p-4" data-testid={testId}>
    <div className="text-[10px] uppercase tracking-wider text-[#7d8194]">{label}</div>
    <div className={`text-[20px] font-black mt-1 flex items-center gap-1.5 ${tone}`}>{value}</div>
    {hint && <div className="text-[11px] text-[#5f6377] mt-0.5">{hint}</div>}
  </div>
);

const SETTINGS = [
  { key: "rtp_target", label: "RTP (доля возврата игрокам)", hint: "Показ игроку: шанс = ставка / цена. Реальная победа: ставка / цена × RTP. Защита банка может заменить выигрыш проигрышем при нехватке средств или блокировки.", min: 75, max: 100, fmt: (v) => `${v}% · комиссия ${100 - v}%`, to: (v) => v / 100, from: (v) => Math.round(v * 100) },
];

const SettingRow = ({ s, value, onSaved, askPin }) => {
  const [v, setV] = useState(s.from(value));
  useEffect(() => setV(s.from(value)), [value, s]);
  const save = () => askPin({
    title: "Подтвердите смену RTP",
    description: `Текущее значение: ${s.fmt(s.from(value))}.\nНовое значение: ${s.fmt(v)}.\n\nИзменение вступит в силу для всех следующих прокрутов. Введите PIN-код.`,
    confirmLabel: "Изменить RTP",
    onConfirm: async (pin) => {
      try {
        await adminApi.bankSettings({ [s.key]: s.to(v) }, pin);
        toast.success(`${s.label}: ${s.fmt(v)}`);
        onSaved();
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Ошибка");
        throw e;
      }
    },
  });
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
        <button onClick={save} disabled={s.from(value) === v} className="blox-btn-primary h-8 px-3 text-[11px] disabled:opacity-40" data-testid={`setting-${s.key}-save`}>
          Сохранить
        </button>
      </div>
    </div>
  );
};

const RtpControl = ({ settings, onSaved, askPin }) => (
  <div className="blox-panel p-4 space-y-4" data-testid="bank-rtp-panel">
    <div className="text-[13px] font-bold">Настройки выдачи</div>
    {SETTINGS.map((s) => <SettingRow key={s.key} s={s} value={settings[s.key]} onSaved={onSaved} askPin={askPin} />)}
  </div>
);

const AdjustForm = ({ onDone, askPin }) => {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const submit = (sign) => {
    const v = Number(amount) * sign;
    if (!v || note.trim().length < 2) return;
    askPin({
      title: v > 0 ? "Добавить в банк" : "Списать из банка",
      description: `Сумма: ${v > 0 ? "+" : ""}${formatMoney(v)} RAP.\nПричина: ${note.trim()}.\n\nВведите PIN-код для подтверждения.`,
      confirmLabel: v > 0 ? "Добавить" : "Списать",
      onConfirm: async (pin) => {
        try {
          await adminApi.bankAdjust(v, note.trim(), pin);
          toast.success(`Банк скорректирован на ${v > 0 ? "+" : ""}${formatMoney(v)}`);
          setAmount("");
          setNote("");
          onDone();
        } catch (e) {
          toast.error(e?.response?.data?.detail || "Ошибка");
          throw e;
        }
      },
    });
  };
  return (
    <div className="blox-panel p-4 space-y-2" data-testid="bank-adjust-panel">
      <div className="text-[13px] font-bold">Ручная корректировка банка</div>
      <div className="text-[11px] text-[#8e91a3]">Только для исправлений: скин ушёл вне сайта, ошибка в сумме и т.п. Каждая правка пишется в журнал. Требуется PIN-код.</div>
      <div className="flex items-center gap-2 h-10 px-3 rounded-lg bg-[#0f1015]">
        <RobuxIcon size={13} />
        <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))} placeholder="Сумма RAP" className="flex-1 bg-transparent outline-none text-[13px] font-bold" data-testid="bank-adjust-amount" />
      </div>
      <input value={note} onChange={(e) => setNote(e.target.value.slice(0, 200))} placeholder="Причина (обязательно)" className="w-full h-9 px-3 rounded-lg bg-[#0f1015] outline-none text-[12px]" data-testid="bank-adjust-note" />
      <div className="flex gap-2">
        <button onClick={() => submit(1)} disabled={!Number(amount) || note.trim().length < 2} className="flex-1 h-9 rounded-lg bg-[#2ecc71] text-black font-bold text-[12px] disabled:opacity-40" data-testid="bank-adjust-plus">+ Добавить</button>
        <button onClick={() => submit(-1)} disabled={!Number(amount) || note.trim().length < 2} className="flex-1 h-9 rounded-lg bg-[#ff5c5c] text-white font-bold text-[12px] disabled:opacity-40" data-testid="bank-adjust-minus">− Списать</button>
      </div>
    </div>
  );
};

const PoolForm = ({ onDone, pool, askPin }) => {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const submit = (sign) => {
    const v = Number(amount);
    if (!v || v <= 0 || note.trim().length < 2) return;
    askPin({
      title: sign > 0 ? "Пополнить пул выдачи" : "Уменьшить пул выдачи",
      description: `Сумма: ${sign > 0 ? "+" : "−"}${formatMoney(v)} RAP.\nПричина: ${note.trim()}.\n\nВведите PIN-код для подтверждения.`,
      confirmLabel: sign > 0 ? "Пополнить" : "Уменьшить",
      onConfirm: async (pin) => {
        try {
          await adminApi.poolTopup(sign * v, note.trim(), pin);
          toast.success(`Пул выдачи ${sign > 0 ? "пополнен" : "уменьшен"} на ${formatMoney(v)}`);
          setAmount("");
          setNote("");
          onDone();
        } catch (e) {
          toast.error(e?.response?.data?.detail || "Ошибка");
          throw e;
        }
      },
    });
  };
  return (
    <div className="blox-panel p-4 space-y-2" data-testid="bank-pool-topup">
      <div className="text-[13px] font-bold">Изменить пул выдачи</div>
      <div className="text-[11px] text-[#8e91a3]">Можно добавить или убрать бюджет на выигрыши. Для уменьшения доступно {formatMoney(pool)} RAP свободного пула. Резерв активной «Удачи» возвращается кнопкой её закрытия. Требуется PIN-код.</div>
      <div className="flex items-center gap-2 h-10 px-3 rounded-lg bg-[#0f1015]">
        <RobuxIcon size={13} />
        <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))} placeholder="Сумма RAP" className="flex-1 bg-transparent outline-none text-[13px] font-bold" data-testid="bank-pool-amount" />
      </div>
      <input value={note} onChange={(e) => setNote(e.target.value.slice(0, 200))} placeholder="Причина (обязательно)" className="w-full h-9 px-3 rounded-lg bg-[#0f1015] outline-none text-[12px]" data-testid="bank-pool-note" />
      <div className="flex gap-2">
        <button onClick={() => submit(1)} disabled={!Number(amount) || Number(amount) <= 0 || note.trim().length < 2} className="flex-1 h-9 rounded-lg bg-[#4b9dff] text-black font-bold text-[12px] disabled:opacity-40" data-testid="bank-pool-submit">
          + Пополнить
        </button>
        <button onClick={() => submit(-1)} disabled={!Number(amount) || Number(amount) <= 0 || Number(amount) > pool || note.trim().length < 2} className="flex-1 h-9 rounded-lg bg-[#ff5c5c] text-white font-bold text-[12px] disabled:opacity-40" data-testid="bank-pool-decrease">
          − Уменьшить
        </button>
      </div>
    </div>
  );
};

const ResetPanel = ({ data, onDone, askPin }) => {
  const reset = () => askPin({
    danger: true,
    title: "Сбросить ВЕСЬ банк до заводских настроек?",
    description: `Будет обнулено: банк ${formatMoney(data.bank)} → 0, пул выдачи ${formatMoney(data.pool ?? 0)} → 0, комиссия ${formatMoney(data.commission_profit ?? 0)} → 0, журнал операций и итоги «всего задепозитили / выведено» → 0.\n\nНЕ затрагивается: игры и «всего апгрейдов», игроки, их балансы и инвентари, заявки.\n\nДействие необратимо. Введите PIN-код.`,
    confirmLabel: "Сбросить банк",
    onConfirm: async (pin) => {
      try {
        const r = await adminApi.bankReset(pin);
        toast.success(`Банк сброшен: банк ${formatMoney(r.bank)}, пул ${formatMoney(r.pool)}, комиссия ${formatMoney(r.commission_profit)}`);
        onDone();
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Ошибка");
        throw e;
      }
    },
  });
  return (
    <div className="blox-panel p-4 space-y-2 border border-[#ff5c5c]/40" data-testid="bank-reset-panel">
      <div className="text-[13px] font-bold text-[#ff8a8a]">Полный сброс банка</div>
      <div className="text-[11px] text-[#8e91a3]">Обнуляет банк, пул выдачи, комиссию и журнал — банк стартует с нуля. Счётчик игр/апгрейдов и данные игроков остаются. Требуется PIN-код.</div>
      <button onClick={reset} className="w-full h-9 rounded-lg bg-[#ff5c5c] hover:bg-[#ff7676] text-white font-bold text-[12px] transition-colors" data-testid="bank-reset-button">
        Сбросить весь банк до 0
      </button>
    </div>
  );
};

export default function BankTab({ refreshKey = 0 }) {
  const [data, setData] = useState(null);
  const [pinRequest, setPinRequest] = useState(null);
  const load = useCallback(() => adminApi.bank().then(setData).catch(() => toast.error("Не удалось загрузить банк")), []);
  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load, refreshKey]);

  if (!data) return <div className="blox-panel h-[160px] flex items-center justify-center text-[13px] text-[#5f6377]" data-testid="bank-loading">Загрузка…</div>;

  const { bank, pool, liabilities, net, rtp, games, settings, ledger, gifts_total, gifts_count } = data;
  const commission = Number(data.commission_profit ?? 0);
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
        <b>Показ: шанс = ставка / цена. Реально: × {Math.round(settings.rtp_target * 100)}% (комиссия {Math.round((1 - settings.rtp_target) * 100)}%).</b> Выплаты ограничены пулом выдачи. Если пул пуст, выигрыш по роллу тихо засчитывается как проигрыш. Комиссия 20% с пополнений скинами исключена из банка для выплат. Красный — обязательства превышают доступный банк; жёлтый — свободный остаток &lt; 20% обязательств.
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Банк всего" value={<>{formatMoney(bank)} <RobuxIcon size={14} /></>} tone="text-[#ffb000]" testId="bank-balance" hint="Σ депозитов − Σ выданных скинов ± правки; включая защищённую комиссию" />
        <Stat label="Чистая прибыль — комиссия 20%" value={<>{formatMoney(commission)} <RobuxIcon size={14} /></>} tone="text-[#2ecc71]" testId="bank-commission-profit" hint="Только комиссия с пополнений скинами. Не расходуется на выплаты игрокам, удачу и бонусы." />
        <Stat label="Банк для игроков" value={<>{formatMoney(data.available_bank ?? bank - commission)} <RobuxIcon size={14} /></>} testId="bank-available" hint="банк всего − защищённая комиссия 20%" />
        <Stat label="Обязательства игрокам" value={<>{formatMoney(liabilities.total)} <RobuxIcon size={14} /></>} testId="bank-liabilities" hint={`балансы ${formatMoney(liabilities.balances)} · инвентари ${formatMoney(liabilities.inventory)} · на выводе ${formatMoney(liabilities.pending_withdrawals)}`} />
        <Stat label="Свободный остаток" value={<>{net >= 0 ? "+" : ""}{formatMoney(net)} <RobuxIcon size={14} /></>} tone={health === "green" ? "text-[#2ecc71]" : health === "yellow" ? "text-[#ffb000]" : "text-[#ff5c5c]"} testId="bank-net" hint="банк для игроков − обязательства" />
        <Stat label="Фактический RTP" value={pct(rtp.rtp)} tone={rtp.rtp <= settings.rtp_target + 0.05 ? "text-[#2ecc71]" : "text-[#ffb000]"} testId="bank-rtp-actual" hint={`потолок ${Math.round(settings.rtp_target * 100)}% — выше подняться не может · поставлено ${formatMoney(rtp.wagered)} · выдано ${formatMoney(rtp.paid)}`} />
        <Stat label="Пул выдачи" value={<>{formatMoney(pool ?? 0)} <RobuxIcon size={14} /></>} tone={(pool ?? 0) > 0 ? "text-[#4b9dff]" : "text-[#ff5c5c]"} testId="bank-pool" hint={(pool ?? 0) <= 0 ? "пуст — выигрыши временно не выплачиваются" : "доступный бюджет на выигрыши: пополняется ставками × RTP"} />
        <Stat label="Подарки выдано" value={<>{formatMoney(gifts_total ?? 0)} <RobuxIcon size={14} /></>} tone={(gifts_total ?? 0) > 0 ? "text-[#2ecc71]" : ""} testId="bank-gifts-total" hint={`${gifts_count ?? 0} выдач · растут обязательства и режут чистую позицию, банк и пул не трогают`} />
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
        <RtpControl settings={settings} onSaved={load} askPin={setPinRequest} />
        <PoolForm onDone={load} pool={Number(pool ?? 0)} askPin={setPinRequest} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <AdjustForm onDone={load} askPin={setPinRequest} />
        <ResetPanel data={data} onDone={load} askPin={setPinRequest} />
      </div>
      <PinConfirmDialog request={pinRequest} onClose={() => setPinRequest(null)} />

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
