import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { adminApi } from "../../lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../ui/dialog";

const errorMessage = (error, fallback) => typeof error?.response?.data?.detail === "string" ? error.response.data.detail : fallback;
const number = (value) => Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
const inputClass = "w-full h-11 px-3 mt-1.5 rounded-lg bg-[#0f1015] outline-none focus:ring-1 focus:ring-[#ffb000] text-white text-[14px]";

export default function PromosTab({ refreshKey = 0 }) {
  const [rows, setRows] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [editor, setEditor] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    try {
      const result = await adminApi.promos();
      if (id !== requestId.current) return;
      setRows(result);
      setLoadError("");
    } catch (error) {
      if (id === requestId.current) setLoadError(errorMessage(error, "Не удалось загрузить промокоды"));
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 20000);
    return () => { clearInterval(timer); requestId.current += 1; };
  }, [load, refreshKey]);

  const save = async (event) => {
    event.preventDefault();
    if (busy || !event.currentTarget.reportValidity()) return;
    setBusy(true);
    setFormError("");
    try {
      const payload = { code: editor.code.trim(), percent: Number(editor.percent) };
      if (editor.id) await adminApi.updatePromo(editor.id, payload);
      else await adminApi.createPromo(payload);
      toast.success(editor.id ? "Промокод сохранён" : "Промокод добавлен");
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

  return (
    <div className="space-y-4" data-testid="promos-tab">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-[20px] font-black">Промокоды</h2>
          <p className="text-[12px] text-[#8e91a3] mt-1 max-w-[620px]">
            Каждый человек учитывается один раз для каждого промокода — по своему Discord-аккаунту. Повторные активации и пополнения не увеличивают счётчик.
          </p>
        </div>
        <button onClick={() => { setFormError(""); setEditor({ code: "", percent: "10" }); }} className="blox-btn-primary h-10 px-4 text-[12px]" data-testid="promo-add">+ Добавить промокод</button>
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
                <th className="px-4 py-3">Бонус</th>
                <th className="px-4 py-3">Использовали, человек</th>
                <th className="px-4 py-3 text-right">Действия</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((promo) => (
                <tr key={promo.id} className="border-t border-[#15161b] hover:bg-[#0f1015]" data-testid={`promo-row-${promo.id}`}>
                  <td className="px-4 py-3 font-bold break-all min-w-[140px]">{promo.code}</td>
                  <td className="px-4 py-3 font-bold text-[#ffb000] whitespace-nowrap">+{number(promo.percent)}%</td>
                  <td className="px-4 py-3 font-bold tabular-nums" data-testid="promo-unique-users">{number(promo.unique_users)}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => { setFormError(""); setEditor({ id: promo.id, code: promo.code, percent: String(promo.percent) }); }} className="blox-chip h-8 px-3 text-[12px] text-[#b4b7c7] hover:text-white" aria-label={`Редактировать ${promo.code}`}>Редактировать</button>
                      <button onClick={() => { setFormError(""); setDeleting(promo); }} className="h-8 px-3 rounded-md bg-[#ff5c5c]/10 text-[#ff8a8a] hover:bg-[#ff5c5c]/20 text-[12px]" aria-label={`Удалить ${promo.code}`}>Удалить</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] text-[#7d8194]">Название вводится без учёта регистра. Бонус применяется к сумме после комиссии. Изменения действуют для новых заявок на пополнение; уже созданные сохраняют свой процент.</p>

      <Dialog open={Boolean(editor)} onOpenChange={(open) => { if (!open && !busy) setEditor(null); }}>
        <DialogContent className="bg-[#1e1f23] border-0 text-white max-w-[calc(100%-2rem)] sm:max-w-[440px] rounded-xl" data-testid="promo-editor">
          <DialogHeader>
            <DialogTitle>{editor?.id ? "Редактировать промокод" : "Добавить промокод"}</DialogTitle>
            <DialogDescription className="text-[#8e91a3]">При переименовании количество использовавших сохраняется.</DialogDescription>
          </DialogHeader>
          {editor && <form onSubmit={save}>
            <fieldset disabled={busy} className="space-y-4">
              <label className="block text-[12px] text-[#b4b7c7]">
                Название промокода
                <input autoFocus required maxLength={32} pattern="[A-Za-z0-9_\-]+" title="Латинские буквы, цифры, дефис и подчёркивание" value={editor.code} onChange={(e) => setEditor({ ...editor, code: e.target.value })} className={`${inputClass} uppercase`} autoComplete="off" spellCheck={false} data-testid="promo-code" />
                <span className="block mt-1 text-[11px] text-[#7d8194]">До 32 символов: латинские буквы, цифры, дефис и подчёркивание.</span>
              </label>
              <label className="block text-[12px] text-[#b4b7c7]">
                Бонус, %
                <input type="number" required min="0.01" max="50" step="0.01" value={editor.percent} onChange={(e) => setEditor({ ...editor, percent: e.target.value })} className={inputClass} data-testid="promo-percent" />
                <span className="block mt-1 text-[11px] text-[#7d8194]">От 0,01% до 50%.</span>
              </label>
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
            <DialogDescription className="text-[#8e91a3]">Промокод перестанет давать бонус в новых заявках, в том числе у уже активировавших его игроков.</DialogDescription>
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
