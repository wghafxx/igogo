import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { adminApi, parseServerDate } from "../../lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../ui/dialog";

const errorMessage = (error, fallback) => typeof error?.response?.data?.detail === "string" ? error.response.data.detail : fallback;
const number = (value) => Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
const payrollRub = (rap) => Math.round((Number(rap) || 0) * 25) / 100;
const dateInput = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const periodParams = ({ from, to }) => {
  const params = {};
  if (from) params.date_from = new Date(`${from}T00:00:00`).toISOString();
  if (to) {
    const end = new Date(`${to}T00:00:00`);
    end.setDate(end.getDate() + 1);
    params.date_to = end.toISOString();
  }
  return params;
};
const inputClass = "w-full h-11 px-3 mt-1.5 rounded-lg bg-[#0f1015] outline-none focus:ring-1 focus:ring-[#ffb000] text-white text-[14px]";
const promoKind = (promo) => promo?.type === "rap_fixed" ? "rap_fixed" : "deposit_percent";
const fmtDate = (d) => {
  try {
    return parseServerDate(d).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
};
const toLocalInput = (d) => {
  try {
    const dt = parseServerDate(d);
    const pad = (n) => String(n).padStart(2, "0");
    return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
  } catch {
    return "";
  }
};

const newEditor = () => ({ code: "", type: "deposit_percent", is_media: false, percent: "10", media_percent: "0", amount_rap: "100", max_uses: "100", expires_at: "" });
const editorFromRow = (promo) => promoKind(promo) === "rap_fixed"
  ? {
    id: promo.id, code: promo.code, type: "rap_fixed",
    amount_rap: String(promo.amount_rap ?? ""), max_uses: String(promo.max_uses ?? ""),
    expires_at: promo.expires_at ? toLocalInput(promo.expires_at) : "",
    used_count: Number(promo.used_count ?? promo.unique_users ?? 0),
  }
  : { id: promo.id, code: promo.code, type: "deposit_percent", is_media: Boolean(promo.is_media), percent: String(promo.percent), media_percent: String(promo.media_percent || 0) };

export default function PromosTab({ refreshKey = 0 }) {
  const [rows, setRows] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [editor, setEditor] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [range, setRange] = useState({ from: "", to: "" });
  const [rangeError, setRangeError] = useState("");
  const [params, setParams] = useState({});
  const [periodLabel, setPeriodLabel] = useState("Всё время");
  const requestId = useRef(0);
  const activeParams = useRef(params);
  activeParams.current = params;

  const load = useCallback(async () => {
    if (params !== activeParams.current) return;
    const id = ++requestId.current;
    try {
      const result = await adminApi.promos(params);
      if (id !== requestId.current || params !== activeParams.current) return;
      setRows(result);
      setLoadError("");
    } catch (error) {
      if (id === requestId.current && params === activeParams.current) setLoadError(errorMessage(error, "Не удалось загрузить промокоды"));
    }
  }, [params]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 20000);
    return () => { clearInterval(timer); requestId.current += 1; };
  }, [load, refreshKey]);

  const applyRange = (next) => {
    if (next.from && next.to && next.from > next.to) {
      setRangeError("Дата начала не может быть позже даты окончания");
      return;
    }
    // Invalidate an in-flight request before displaying another payroll period.
    requestId.current += 1;
    setRows(null);
    setLoadError("");
    setRangeError("");
    setRange(next);
    const nextParams = periodParams(next);
    activeParams.current = nextParams;
    setParams(nextParams);
    setPeriodLabel(next.from || next.to ? `${next.from || "Начало истории"} — ${next.to || "Сегодня"}` : "Всё время");
  };

  const exportCsv = () => {
    const cell = (value) => {
      const text = String(value);
      return `"${(/^[=+@-]/.test(text) ? "'" : "") + text.replace(/"/g, '""')}"`;
    };
    const lines = [["Промокод", "Период", "Пополнено RAP", "Скинами RAP", "Деньгами RAP", "Пополнений", "Пополнили человек", "Эквивалент ₽ (1 RAP = 0,25 ₽)", "Ставка медиа %", "Начислено медиа ₽", "Медиапромокод"],
      ...rows.filter((p) => promoKind(p) === "deposit_percent").map((p) => [p.code, periodLabel,
        p.deposited_rap || 0, p.skin_deposited_rap || 0, p.cash_deposited_rap || 0, p.deposit_count || 0, p.depositors || 0, payrollRub(p.deposited_rap), p.media_percent || 0, p.media_payout_rub || 0, p.is_media ? "Да" : "Нет"])];
    const url = URL.createObjectURL(new Blob(["\uFEFF", lines.map((line) => line.map(cell).join(";")).join("\r\n")], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `promo-deposits-${dateInput(new Date())}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const save = async (event) => {
    event.preventDefault();
    if (busy || !event.currentTarget.reportValidity()) return;
    setBusy(true);
    setFormError("");
    try {
      let payload;
      let response;
      if ((editor.type || "deposit_percent") === "rap_fixed") {
        payload = {
          code: editor.code.trim(), type: "rap_fixed",
          amount_rap: Number(editor.amount_rap), max_uses: Number(editor.max_uses),
        };
        if (editor.expires_at) payload.expires_at = new Date(editor.expires_at).toISOString();
        if (editor.id) response = await adminApi.updatePromo(editor.id, payload);
        else response = await adminApi.createPromo(payload);
      } else {
        payload = { code: editor.code.trim(), percent: Number(editor.percent), is_media: editor.is_media,
          media_percent: editor.is_media ? Number(editor.media_percent) : 0 };
        if (editor.id) response = await adminApi.updatePromo(editor.id, payload);
        else response = await adminApi.createPromo(payload);
      }
      if (response?.warning) {
        if (typeof toast.warning === "function") toast.warning(response.warning, { duration: 8000 });
        else toast.success(response.warning, { duration: 8000 });
      } else {
        toast.success(editor.id ? "Промокод сохранён" : "Промокод добавлен");
      }
      setEditor(null);
      await load();
    } catch (error) {
      setFormError(errorMessage(error, "Не удалось сохранить промокод"));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (busy) return;
    setBusy(true);
    setFormError("");
    try {
      await adminApi.deletePromo(deleting.id);
      toast.success("Промокод удалён");
      setDeleting(null);
      await load();
    } catch (error) {
      setFormError(errorMessage(error, "Не удалось удалить промокод"));
    } finally {
      setBusy(false);
    }
  };

  const deletingIsRap = deleting && promoKind(deleting) === "rap_fixed";

  return (
    <div className="space-y-4" data-testid="promos-tab">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-[20px] font-black">Промокоды</h2>
          <p className="text-[12px] text-[#8e91a3] mt-1 max-w-[620px]">
            Пополнено RAP — фактически подтверждённые пополнения до комиссии, без промобонусов и подарков. Все повторные пополнения тоже входят в сумму.
          </p>
          <p className="text-[11px] text-[#7d8194] mt-1 max-w-[620px]">
            Активировали — уникальные Discord-аккаунты за всё время. Для расчёта выплат выберите период пополнений по дате подтверждения; даты указаны в вашем часовом поясе.
          </p>
          <p className="text-[11px] text-[#7d8194] mt-1">Курс для расчёта зарплаты: 1 RAP = 0,25 ₽. Рублёвый эквивалент показывает оборот, а не сумму вознаграждения.</p>
          <p className="text-[11px] text-[#7d8194] mt-1">Медиапромокоды отмечены отдельно. Старт: игроку +7,5%, медиа 13% подтверждённых пополнений. Вознаграждение считается по текущей ставке кода.</p>
        </div>
        <button onClick={() => { setFormError(""); setEditor(newEditor()); }} className="blox-btn-primary h-10 px-4 text-[12px]" data-testid="promo-add">+ Добавить промокод</button>
      </div>

      <div className="blox-panel p-4 space-y-3">
        <div className="flex flex-wrap justify-between items-center gap-2">
          <p className="text-[12px] text-[#b4b7c7]" data-testid="promo-period-label">Показано: <span className="text-white font-bold">{periodLabel}</span></p>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => applyRange({ from: "", to: "" })} className="blox-chip h-8 px-3 text-[12px]" data-testid="promo-all-time">Всё время</button>
            <button onClick={() => {
              const today = new Date();
              applyRange({ from: dateInput(new Date(today.getFullYear(), today.getMonth(), 1)), to: dateInput(today) });
            }} className="blox-chip h-8 px-3 text-[12px]" data-testid="promo-this-month">Этот месяц</button>
            <button onClick={exportCsv} disabled={!rows || Boolean(loadError)} className="blox-chip h-8 px-3 text-[12px] disabled:opacity-40" data-testid="promo-export">Скачать CSV</button>
          </div>
        </div>
        <form onSubmit={(event) => { event.preventDefault(); applyRange(range); }} className="flex flex-wrap items-end gap-3">
          <label className="text-[12px] text-[#b4b7c7]">С даты
            <input type="date" value={range.from} onChange={(event) => setRange({ ...range, from: event.target.value })} className={`${inputClass} [color-scheme:dark]`} data-testid="promo-date-from" />
          </label>
          <label className="text-[12px] text-[#b4b7c7]">По дату включительно
            <input type="date" value={range.to} onChange={(event) => setRange({ ...range, to: event.target.value })} className={`${inputClass} [color-scheme:dark]`} data-testid="promo-date-to" />
          </label>
          <button type="submit" className="blox-btn-primary h-11 px-4 text-[12px]" data-testid="promo-period-apply">Применить</button>
        </form>
        {rangeError && <p role="alert" className="text-[12px] text-[#ff8a8a]">{rangeError}</p>}
      </div>

      {loadError && <div role="alert" className="rounded-lg bg-[#ff5c5c]/10 p-3 text-[13px] text-[#ff8a8a]">{loadError} <button onClick={load} className="underline ml-2">Повторить</button></div>}
      {!rows && !loadError && <div className="blox-panel p-10 text-center text-[13px] text-[#8e91a3]">Загрузка…</div>}
      {rows?.length === 0 && <div className="blox-panel p-10 text-center text-[13px] text-[#8e91a3]">Промокодов пока нет. Добавьте первый.</div>}
      {rows?.length > 0 && (
        <div className="blox-panel overflow-x-auto">
          <table className="w-full text-[13px]" data-testid="promos-table">
            <thead className="text-[10px] uppercase tracking-wider text-[#7d8194] text-left">
              <tr>
                <th className="px-4 py-3">Промокод</th>
                <th className="px-4 py-3">Награда</th>
                <th className="px-4 py-3">Активировали, человек</th>
                <th className="px-4 py-3">Пополнено, RAP</th>
                <th className="px-4 py-3">Пополнений</th>
                <th className="px-4 py-3">Пополнили, человек</th>
                <th className="px-4 py-3">Медиа, ₽</th>
                <th className="px-4 py-3 text-right">Действия</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((promo) => {
                const isRap = promoKind(promo) === "rap_fixed";
                const used = Number(promo.used_count ?? promo.unique_users ?? 0);
                return (
                  <tr key={promo.id} className="border-t border-[#15161b] hover:bg-[#0f1015]" data-testid={`promo-row-${promo.id}`}>
                    <td className="px-4 py-3 font-bold break-all min-w-[140px]">
                      {promo.code}
                      {promo.is_media && !isRap && <span className="block mt-1 text-[10px] uppercase tracking-wider text-[#4b9dff]" data-testid="promo-media-badge">Медиапромокод</span>}
                      {isRap && promo.expires_at && (
                        <span className="block text-[11px] font-normal text-[#7d8194]">до {fmtDate(promo.expires_at)}</span>
                      )}
                      {isRap && (
                        <span className="inline-block mt-1 text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 bg-[#2ecc71]/15 text-[#2ecc71]">RAP-подарок</span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-bold text-[#ffb000] whitespace-nowrap">
                      {isRap ? (
                        <>
                          {`${number(promo.amount_rap)} RAP`}
                          <span className="block text-[11px] font-normal text-[#7d8194]">
                            бюджет до {number(Number(promo.amount_rap || 0) * Number(promo.max_uses || 0))} RAP · 1 человеку — 1 раз
                          </span>
                        </>
                      ) : `+${number(promo.percent)}%`}
                    </td>
                    <td className="px-4 py-3 font-bold tabular-nums" data-testid="promo-unique-users">
                      {isRap ? `${number(used)} / ${number(promo.max_uses)}` : number(promo.unique_users)}
                    </td>
                    <td className="px-4 py-3 tabular-nums whitespace-nowrap" data-testid="promo-deposited-rap">
                      {isRap ? <span className="text-[#7d8194]">—</span> : <>
                        <span className="font-black text-[16px] text-[#2ecc71]">{number(promo.deposited_rap || 0)}</span>
                        <span className="block text-[11px] text-[#b4b7c7]" data-testid="promo-deposited-rub">{number(payrollRub(promo.deposited_rap))} ₽ для расчёта</span>
                        <span className="block text-[11px] text-[#7d8194]">Скинами {number(promo.skin_deposited_rap || 0)} · деньгами {number(promo.cash_deposited_rap || 0)}</span>
                      </>}
                    </td>
                    <td className="px-4 py-3 font-bold tabular-nums" data-testid="promo-deposit-count">{isRap ? "—" : number(promo.deposit_count || 0)}</td>
                    <td className="px-4 py-3 font-bold tabular-nums" data-testid="promo-depositors">{isRap ? "—" : number(promo.depositors || 0)}</td>
                    <td className="px-4 py-3 whitespace-nowrap tabular-nums" data-testid="promo-media-payout">
                      {isRap || !promo.is_media ? "—" : <>
                        <span className="font-black text-[#ffb000]">{number(promo.media_payout_rub || 0)} ₽</span>
                        <span className="block text-[11px] text-[#7d8194]">{number(promo.media_percent || 0)}% от пополнений</span>
                      </>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <button onClick={() => { setFormError(""); setEditor(editorFromRow(promo)); }} className="blox-chip h-8 px-3 text-[12px] text-[#b4b7c7] hover:text-white" aria-label={`Редактировать ${promo.code}`}>Редактировать</button>
                        <button onClick={() => { setFormError(""); setDeleting(promo); }} className="h-8 px-3 rounded-md bg-[#ff5c5c]/10 text-[#ff8a8a] hover:bg-[#ff5c5c]/20 text-[12px]" aria-label={`Удалить ${promo.code}`}>Удалить</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] text-[#7d8194]">Пополнения относятся к промокоду, сохранённому в заявке; смена кода игроком не переносит прошлые суммы. Переименование сохраняет историю; пересоздание удалённого кода — новая акция. Старые заявки без сохранённого ID промокода или фактической суммы RAP не включаются. Экономический сброс удаляет историю пополнений — перед ним скачайте CSV для расчёта выплат.</p>
      <p className="text-[11px] text-[#7d8194]">Бонус применяется после комиссии скинов; уже созданные заявки сохраняют свой процент. RAP-подарок увеличивает обычный баланс и обязательства в Банке, но не считается пополнением.</p>

      <Dialog open={Boolean(editor)} onOpenChange={(open) => { if (!open && !busy) setEditor(null); }}>
        <DialogContent className="bg-[#1e1f23] border-0 text-white max-w-[calc(100%-2rem)] sm:max-w-[440px] rounded-xl" data-testid="promo-editor">
          <DialogHeader>
            <DialogTitle>{editor?.id ? "Редактировать промокод" : "Добавить промокод"}</DialogTitle>
            <DialogDescription className="text-[#8e91a3]">При переименовании количество использовавших сохраняется. Смена типа запрещена.</DialogDescription>
          </DialogHeader>
          {editor && <form onSubmit={save}>
            <fieldset disabled={busy} className="space-y-4">
              <label className="block text-[12px] text-[#b4b7c7]">
                Тип промокода
                <select
                  value={editor.type || "deposit_percent"}
                  disabled={Boolean(editor.id)}
                  onChange={(e) => setEditor({ ...editor, type: e.target.value })}
                  className={inputClass}
                  data-testid="promo-type"
                >
                  <option value="deposit_percent">Процент к депозиту</option>
                  <option value="rap_fixed">Мгновенный RAP-подарок</option>
                </select>
                {editor.id
                  ? <span className="block mt-1 text-[11px] text-[#7d8194]">Тип менять нельзя — создайте новый код.</span>
                  : <span className="block mt-1 text-[11px] text-[#7d8194]">Подарок: 1 человеку — 1 раз, бюджет виден ниже.</span>}
              </label>
              <label className="block text-[12px] text-[#b4b7c7]">
                Название промокода
                <input autoFocus required maxLength={32} pattern="[A-Za-z0-9_\-]+" title="Латинские буквы, цифры, дефис и подчёркивание" value={editor.code} onChange={(e) => setEditor({ ...editor, code: e.target.value })} className={`${inputClass} uppercase`} autoComplete="off" spellCheck={false} data-testid="promo-code" />
                <span className="block mt-1 text-[11px] text-[#7d8194]">До 32 символов: латинские буквы, цифры, дефис и подчёркивание.</span>
              </label>
              {(editor.type || "deposit_percent") === "deposit_percent" ? (<>
                <label className="flex items-center gap-2 text-[12px] text-[#b4b7c7]">
                  <input type="checkbox" checked={Boolean(editor.is_media)} onChange={(e) => setEditor({ ...editor,
                    is_media: e.target.checked, ...(e.target.checked ? { percent: "7.5", media_percent: "13" } : { media_percent: "0" }) })} data-testid="promo-is-media" />
                  Медиапромокод
                </label>
                <label className="block text-[12px] text-[#b4b7c7]">
                  Бонус игроку, %
                  <input type="number" required min="0.01" max="50" step="0.01" value={editor.percent} onChange={(e) => setEditor({ ...editor, percent: e.target.value })} className={inputClass} data-testid="promo-percent" />
                  <span className="block mt-1 text-[11px] text-[#7d8194]">От 0,01% до 50%.</span>
                </label>
                {editor.is_media && <><label className="block text-[12px] text-[#b4b7c7]">
                  Вознаграждение медиа, %
                  <input type="number" required min="0" max="100" step="0.01" value={editor.media_percent} onChange={(e) => setEditor({ ...editor, media_percent: e.target.value })} className={inputClass} data-testid="promo-media-percent" />
                  <span className="block mt-1 text-[11px] text-[#7d8194]">Подтверждённые пополнения × ставка × 0,25 ₽. Ноль — без оплаты медиа.</span>
                </label>
                <div className="rounded-lg bg-[#ffb000]/10 px-3 py-2.5 text-[12px] text-[#e8ce91]" data-testid="promo-media-terms">
                  При 100 000 RAP пополнений: {number(Math.round(100000 * Number(editor.media_percent || 0) / 100 * 25) / 100)} ₽ медиа.
                  <span className="block text-[11px] mt-1">Это расчёт вознаграждения; перечисление денег выполняется отдельно. Ставка применяется ко всему выбранному периоду — сохраните CSV перед изменением условий.</span>
                </div>
                </>}
              </>) : (
                <>
                  <label className="block text-[12px] text-[#b4b7c7]">
                    Сумма подарка, RAP
                    <input
                      type="number" required min="0.01" max="100000" step="0.01"
                      value={editor.amount_rap}
                      disabled={Boolean(editor.id && Number(editor.used_count || 0) > 0)}
                      onChange={(e) => setEditor({ ...editor, amount_rap: e.target.value })}
                      className={inputClass} data-testid="promo-amount"
                    />
                    <span className="block mt-1 text-[11px] text-[#7d8194]">
                      {editor.id && Number(editor.used_count || 0) > 0
                        ? "Сумма заморожена после первой брони и не меняется."
                        : "От 0,01 до 100 000 RAP, максимум два знака."}
                    </span>
                  </label>
                  <label className="block text-[12px] text-[#b4b7c7]">
                    Лимит выдач (max_uses)
                    <input type="number" required min="1" max="100000" step="1" value={editor.max_uses} onChange={(e) => setEditor({ ...editor, max_uses: e.target.value })} className={inputClass} data-testid="promo-max-uses" />
                    <span className="block mt-1 text-[11px] text-[#7d8194]">Обязательный конечный лимит: 1–100 000. Уменьшать ниже выданных нельзя.</span>
                  </label>
                  <label className="block text-[12px] text-[#b4b7c7]">
                    Срок действия (необязательно)
                    <input type="datetime-local" value={editor.expires_at || ""} onChange={(e) => setEditor({ ...editor, expires_at: e.target.value })} className={inputClass} data-testid="promo-expires" />
                    <span className="block mt-1 text-[11px] text-[#7d8194]">Пусто — бессрочно. Уже зарезервированные завершаются по сохранённым условиям.</span>
                  </label>
                  <div className="rounded-lg bg-[#2ecc71]/10 px-3 py-2.5 text-[12px] text-[#9be7b8] leading-snug" data-testid="promo-budget">
                    Бюджет акции: {number(Number(editor.amount_rap || 0) * Number(editor.max_uses || 0))} RAP
                    <span className="block text-[11px] text-[#7d8194]">1 человеку — 1 раз по Discord. Выдачи растят обязательства и режут чистую позицию в Банке, банк и пул не трогают.</span>
                  </div>
                </>
              )}
              {formError && <p role="alert" className="text-[12px] text-[#ff8a8a]">{formError}</p>}
              <div className="flex gap-2 pt-1">
                <button type="button" onClick={() => setEditor(null)} className="blox-chip h-10 px-4 text-[12px] text-[#9a9db0]">Отмена</button>
                <button type="submit" className="blox-btn-primary h-10 flex-1 text-[12px] disabled:opacity-40" data-testid="promo-save">{busy ? "Сохранение…" : "Сохранить"}</button>
              </div>
            </fieldset>
          </form>}
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deleting)} onOpenChange={(open) => { if (!open && !busy) setDeleting(null); }}>
        <DialogContent className="bg-[#1e1f23] border-0 text-white max-w-[calc(100%-2rem)] sm:max-w-[440px] rounded-xl" data-testid="promo-delete-dialog">
          <DialogHeader>
            <DialogTitle>Удалить {deleting?.code}?</DialogTitle>
            <DialogDescription className="text-[#8e91a3]">
              {deletingIsRap
                ? "Новые активации заблокируются, выданное не отзовётся, уже зарезервированные завершатся по сохранённым условиям."
                : "Промокод перестанет давать бонус в новых заявках, в том числе у уже активировавших его игроков."}
            </DialogDescription>
          </DialogHeader>
          {formError && <p role="alert" className="text-[12px] text-[#ff8a8a]">{formError}</p>}
          <div className="flex gap-2">
            <button onClick={() => setDeleting(null)} disabled={busy} className="blox-chip h-10 px-4 text-[12px] text-[#9a9db0] disabled:opacity-40">Отмена</button>
            <button onClick={remove} disabled={busy} className="flex-1 h-10 rounded-lg bg-[#ff5c5c] hover:bg-[#ff7373] text-white font-bold text-[12px] disabled:opacity-40" data-testid="promo-delete-confirm">{busy ? "Удаление…" : "Удалить промокод"}</button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
