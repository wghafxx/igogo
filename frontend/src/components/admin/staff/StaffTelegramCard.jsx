import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Send } from "lucide-react";
import { adminStaffApi, errText } from "../../../lib/staff-api";

export default function StaffTelegramCard() {
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => adminStaffApi.telegram().then(setInfo).catch(() => setInfo(null)), []);
  useEffect(() => { load(); }, [load]);
  const run = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); await load(); } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  if (!info) return null;
  const [label, cls] = !info.enabled ? ["Не настроен (STAFF_TG_BOT_TOKEN / STAFF_TG_OWNER_ID / STAFF_TG_WEBHOOK_SECRET)", "text-[#ff9b9b]"]
    : info.connected ? ["Подключён к этому сайту", "text-[#61d899]"] : ["Не привязан к этому сайту", "text-[#ffcf5a]"];
  return (
    <div className="flex flex-wrap items-center gap-2 text-[12px] rounded-lg bg-white/[0.04] px-3 py-2" data-testid="staff-telegram-card">
      <Send size={14} className="text-[#00a2ff]" />
      <span className="font-bold">Telegram · проверка заявок сотрудников:</span>
      <span className={cls} data-testid="staff-telegram-state">{label}</span>
      {info.outbox_pending > 0 && <span className="text-[#ffcf5a]">· в очереди {info.outbox_pending}</span>}
      {info.last_error && <span className="text-[#ff9b9b] truncate max-w-[300px]" title={info.last_error}>· {info.last_error}</span>}
      {info.enabled && !info.connected && <button type="button" disabled={busy} onClick={() => run(adminStaffApi.telegramSetup, "Бот подключён")} className="h-7 px-3 rounded-md bg-[#00a2ff] text-white font-bold disabled:opacity-50" data-testid="staff-telegram-connect">Подключить бота к этому сайту</button>}
      {info.enabled && <button type="button" disabled={busy} onClick={() => run(adminStaffApi.telegramTest, "Проверочное сообщение отправлено")} className="h-7 px-3 rounded-md bg-white/[0.08] font-bold disabled:opacity-50" data-testid="staff-telegram-test">Проверочное сообщение</button>}
    </div>
  );
}
