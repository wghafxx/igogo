import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { staffApi, errText, fmtRap, StatePill } from "../../lib/staff-api";
import { Btn, Card, fmtTime } from "../admin/chat/ui";
import ItemsEditor, { emptyItem, itemsValid, toPayload } from "./ItemsEditor";
import EvidenceUploader from "./EvidenceUploader";

export default function TransfersPanel({ holdings, onChanged }) {
  const [rows, setRows] = useState([]);
  const [items, setItems] = useState([emptyItem()]);
  const [evidence, setEvidence] = useState([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => staffApi.transfers().then(setRows).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const submit = async () => {
    setBusy(true);
    try {
      await staffApi.transfer({ items: toPayload(items), evidence, note });
      toast.success("Отчёт о передаче отправлен владельцу");
      setItems([emptyItem()]); setEvidence([]); setNote("");
      load(); onChanged?.();
    } catch (e) { toast.error(errText(e, "Не удалось отправить")); }
    finally { setBusy(false); }
  };
  return (
    <div className="grid lg:grid-cols-2 gap-4" data-testid="staff-transfers">
      <Card title="Передать скины владельцу">
        <div className="space-y-3">
          <div className="text-[12px] text-[#8e91a3]">Сейчас числится у вас: <b className="text-white" data-testid="staff-holdings">{holdings?.items ?? 0} шт · {fmtRap(holdings?.value)} RAP</b>. Можно передать частично; остаток уменьшится после подтверждения владельцем и не блокирует работу.</div>
          <ItemsEditor items={items} onChange={setItems} testId="transfer-items" />
          <EvidenceUploader value={evidence} onChange={setEvidence} purpose="transfer" testId="transfer-evidence" />
          <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={2} placeholder="Комментарий" className="w-full rounded-lg bg-white/[0.05] p-3 text-[13px] outline-none" data-testid="transfer-note" />
          <Btn tone="primary" disabled={busy || !itemsValid(items) || !evidence.length} onClick={submit} data-testid="transfer-submit">Отправить отчёт о передаче</Btn>
        </div>
      </Card>
      <Card title="История передач">
        <div className="space-y-2" data-testid="transfer-history">
          {rows.length === 0 && <div className="text-[12px] text-[#6b6f84]">Пока нет передач</div>}
          {rows.map((m) => (
            <div key={m.id} className="flex items-center gap-2 text-[12px] rounded-lg bg-white/[0.03] px-3 py-2">
              <span className="flex-1">{m.items_count} шт · {fmtRap(m.value_total)} RAP</span>
              <span className="text-[#8e91a3]">{fmtTime(m.created_at)}</span>
              <StatePill state={m.status} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
