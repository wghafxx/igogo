import React from "react";
import { Plus, Trash2 } from "lucide-react";
import { fmtRap } from "../../lib/staff-api";

export const emptyItem = () => ({ name: "", qty: 1, value: "" });
export const itemsValid = (items) => items.length > 0 && items.every((i) => i.name.trim() && Number(i.qty) >= 1 && Number(i.value) > 0);
export const itemsTotal = (items) => items.reduce((a, i) => a + (Number(i.qty) || 0) * (Number(i.value) || 0), 0);
export const toPayload = (items) => items.map((i) => ({ name: i.name.trim(), qty: Math.floor(Number(i.qty)), value: Number(i.value) }));

const cell = "h-10 rounded-lg bg-white/[0.05] border border-transparent focus:border-white/15 outline-none px-3 text-[13px] text-white";

export default function ItemsEditor({ items, onChange, testId = "items-editor" }) {
  const set = (i, key, v) => onChange(items.map((row, j) => (j === i ? { ...row, [key]: v } : row)));
  return (
    <div className="space-y-2" data-testid={testId}>
      <div className="grid grid-cols-[1fr_64px_96px_32px] gap-2 text-[11px] font-semibold text-[#8e91a3] px-1">
        <span>Предмет</span><span>Кол-во</span><span>Оценка, RAP</span><span />
      </div>
      {items.map((row, i) => (
        <div key={i} className="grid grid-cols-[1fr_64px_96px_32px] gap-2">
          <input className={cell} value={row.name} maxLength={80} placeholder="Название скина" onChange={(e) => set(i, "name", e.target.value)} data-testid={`${testId}-name-${i}`} />
          <input className={cell} type="number" min={1} max={1000} value={row.qty} onChange={(e) => set(i, "qty", e.target.value)} data-testid={`${testId}-qty-${i}`} />
          <input className={cell} type="number" min={0} step="0.01" value={row.value} placeholder="0" onChange={(e) => set(i, "value", e.target.value)} data-testid={`${testId}-value-${i}`} />
          <button type="button" disabled={items.length === 1} onClick={() => onChange(items.filter((_, j) => j !== i))} className="h-10 rounded-lg text-[#8e91a3] hover:text-[#ff8a8a] disabled:opacity-30 flex items-center justify-center" data-testid={`${testId}-remove-${i}`}><Trash2 size={15} /></button>
        </div>
      ))}
      <div className="flex items-center justify-between pt-1">
        <button type="button" disabled={items.length >= 50} onClick={() => onChange([...items, emptyItem()])} className="m-chip h-9 px-3 text-[12px] font-bold inline-flex items-center gap-1.5 rounded-lg" data-testid={`${testId}-add`}><Plus size={14} /> Предмет</button>
        <div className="text-[13px]">Итого: <b data-testid={`${testId}-total`}>{fmtRap(itemsTotal(items))} RAP</b></div>
      </div>
    </div>
  );
}
