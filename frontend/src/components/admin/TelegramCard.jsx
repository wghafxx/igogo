import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Send } from "lucide-react";
import { adminApi } from "../../lib/api";

// Owner's Telegram approvals for DonationAlerts: shows webhook state and (re)binds it to this site.
export default function TelegramCard() {
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => adminApi.telegramStatus().then(setInfo).catch(() => setInfo(null)), []);
  useEffect(() => { load(); }, [load]);
  const connect = async () => {
    setBusy(true);
    try {
      const res = await adminApi.telegramSetup();
      if (res.warning) toast.warning(res.warning); else toast.success("Бот подключён — проверьте сообщение в Telegram");
      await load();
    }
    catch (e) { toast.error(e?.response?.data?.detail || "Не удалось подключить бота"); }
    finally { setBusy(false); }
  };
  const sendTest = async () => {
    setBusy(true);
    try { await adminApi.telegramTest(); toast.success("Проверочное сообщение отправлено в Telegram"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Не удалось отправить"); }
    finally { setBusy(false); }
  };
  if (!info) return null;
  const state = !info.enabled ? ["Не настроен (TELEGRAM_BOT_TOKEN / TELEGRAM_ADMIN_ID)", "text-[#ff9b9b]"]
    : info.connected ? ["Подключён к этому сайту", "text-[#61d899]"] : ["Не привязан к этому сайту", "text-[#ffcf5a]"];
  return (
    <div className="flex flex-wrap items-center gap-2 text-[12px] rounded-lg bg-white/[0.04] px-3 py-2" data-testid="admin-telegram-card">
      <Send size={14} className="text-[#00a2ff]" />
      <span className="font-bold">Telegram · DonationAlerts:</span>
      <span className={state[1]} data-testid="admin-telegram-state">{state[0]}</span>
      {info.last_error && <span className="text-[#ff9b9b] truncate max-w-[320px]" title={info.last_error}>· {info.last_error}</span>}
      {info.enabled && !info.connected && (
        <button type="button" onClick={connect} disabled={busy} className="h-7 px-3 rounded-md bg-[#00a2ff] text-white font-bold disabled:opacity-50" data-testid="admin-telegram-connect">
          {busy ? "Подключаем…" : "Подключить бота к этому сайту"}
        </button>
      )}
      {info.enabled && info.connected && (
        <button type="button" onClick={sendTest} disabled={busy} className="h-7 px-3 rounded-md bg-white/[0.08] hover:bg-white/[0.14] font-bold disabled:opacity-50 transition-colors" data-testid="admin-telegram-test">
          Проверочное сообщение
        </button>
      )}
    </div>
  );
}
