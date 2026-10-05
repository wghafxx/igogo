import React, { useState } from "react";
import { toast } from "sonner";
import { XCircle } from "lucide-react";
import { DEPOSIT_REJECTION_REASONS } from "../../lib/api";
import { staffApi, errText } from "../../lib/staff-api";
import { Btn } from "../admin/chat/ui";

const OTHER = "__other";

// Same reasons as the owner's panel plus a free-text option.
export default function StaffRejectControl({ chatId, depositId, onDone, testId = "staff-reject" }) {
  const [reason, setReason] = useState("");
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);
  const value = reason === OTHER ? custom.trim() : reason;
  const submit = async () => {
    if (!value || busy) return;
    setBusy(true);
    try { await staffApi.chatReject(chatId, depositId, value); toast.success("Заявка отклонена"); onDone(); }
    catch (e) { toast.error(errText(e, "Не удалось отклонить")); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-2" data-testid={testId}>
      <div className="flex gap-2">
        <select value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy} className="flex-1 h-9 px-2 rounded-lg bg-black/30 text-[12px] outline-none" data-testid={`${testId}-reason`}>
          <option value="">Причина отклонения…</option>
          {Object.entries(DEPOSIT_REJECTION_REASONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          <option value={OTHER}>Другая причина…</option>
        </select>
        <Btn tone="danger" size="sm" className="h-9" onClick={submit} disabled={busy || !value} data-testid={`${testId}-button`}><XCircle size={13} /> Отклонить</Btn>
      </div>
      {reason === OTHER && <input value={custom} onChange={(e) => setCustom(e.target.value)} maxLength={300} placeholder="Напишите причину для игрока" className="w-full h-9 px-3 rounded-lg bg-black/30 text-[12px] outline-none" data-testid={`${testId}-custom`} />}
    </div>
  );
}
