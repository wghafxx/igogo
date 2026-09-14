import React, { useEffect, useRef, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, Check, X } from "lucide-react";
import { toast } from "sonner";
import { api, formatMoney, NOTIFICATIONS_CHANGED, parseServerDate, rejectionReasonText } from "../lib/api";
import { useLang } from "../lib/i18n";
import AnimButton from "./AnimButton";
import { BellIcon } from "./icons/bell";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

export default function Notifications() {
  const { t, lang } = useLang();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [marking, setMarking] = useState(false);
  const readThrough = useRef(0);
  const refresh = useRef(() => {});
  const unread = items.filter((item) => !item.read).length;

  useEffect(() => {
    let alive = true;
    let running = false;
    let queued = false;
    const fetchItems = async () => {
      if (document.hidden) return;
      if (running) { queued = true; return; }
      running = true;
      try {
        const data = await api.notifications();
        if (alive) {
          setItems(data.items.map((item) => ({ ...item, read: item.read || parseServerDate(item.created_at).getTime() <= readThrough.current })));
          setError(false);
        }
      } catch {
        if (alive) setError(true);
      } finally {
        running = false;
        if (alive) {
          setLoading(false);
          if (queued) { queued = false; fetchItems(); }
        }
      }
    };
    refresh.current = fetchItems;
    fetchItems();
    const timer = window.setInterval(fetchItems, 15000);
    window.addEventListener("focus", fetchItems);
    window.addEventListener(NOTIFICATIONS_CHANGED, fetchItems);
    document.addEventListener("visibilitychange", fetchItems);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", fetchItems);
      window.removeEventListener(NOTIFICATIONS_CHANGED, fetchItems);
      document.removeEventListener("visibilitychange", fetchItems);
    };
  }, []);

  const markRead = async () => {
    if (!items.length || marking) return;
    const cutoff = items[0].created_at;
    setMarking(true);
    try {
      await api.readNotifications(cutoff);
      readThrough.current = Math.max(readThrough.current, parseServerDate(cutoff).getTime());
      setItems((current) => current.map((item) => ({ ...item, read: item.read || parseServerDate(item.created_at).getTime() <= readThrough.current })));
    } catch {
      toast.error(t("notifications.read_failed"));
    } finally {
      setMarking(false);
    }
  };

  return <Popover open={open} onOpenChange={(value) => { setOpen(value); if (value) refresh.current(); }}>
    <PopoverTrigger asChild>
      <AnimButton icon={BellIcon} size={18} className="relative w-8 sm:w-9 h-9 flex items-center justify-center text-[#9a9db0] hover:text-white transition-colors" aria-label={`${t("header.notifications")}${unread ? `: ${unread} ${t("notifications.unread")}` : ""}`} title={t("header.notifications")} data-testid="notifications-button">
        {unread > 0 && <span className="absolute top-0.5 right-0 min-w-3.5 h-3.5 px-0.5 rounded-full bg-[#00a2ff] text-white text-[9px] leading-[14px] font-bold" data-testid="notifications-badge">{unread}</span>}
      </AnimButton>
    </PopoverTrigger>
    <PopoverContent align="end" sideOffset={8} className="w-[360px] max-w-[calc(100vw-24px)] bg-[#16171d] border border-[#262833] rounded-xl text-white p-0 shadow-xl" data-testid="notifications-popover">
      <div className="px-4 py-3 border-b border-[#262833] flex items-center justify-between gap-2">
        <span className="font-bold text-sm">{t("header.notifications")}</span>
        {unread > 0 && <button type="button" onClick={markRead} disabled={marking} className="text-[11px] text-[#00a2ff] hover:text-white disabled:opacity-50" data-testid="notifications-read-all">{t("notifications.read_all")}</button>}
      </div>
      {error && <div className="px-4 py-3 text-[12px] text-[#ff8a8a]" role="status">{t("notifications.load_failed")} <button type="button" className="text-[#00a2ff]" onClick={() => refresh.current()}>{t("skins.retry")}</button></div>}
      {items.length === 0 && !error && <div className="px-4 py-8 text-center text-sm text-[#8e91a3]">{t(loading ? "skins.loading" : "header.no_notifications")}</div>}
      <ul className="max-h-[min(440px,65vh)] overflow-y-auto divide-y divide-[#262833]" aria-label={t("header.notifications")}>
        {items.map((item) => {
          const cancelled = /_(cancelled|rejected|expired)$/.test(item.type);
          const success = /_(confirmed|done)$/.test(item.type);
          const Icon = cancelled ? X : success ? Check : item.type.startsWith("deposit_") ? ArrowDownLeft : ArrowUpRight;
          const color = cancelled ? "text-[#ff8a8a] bg-[#ff8a8a]/10" : success ? "text-[#72dca0] bg-[#72dca0]/10" : "text-[#00a2ff] bg-[#00a2ff]/10";
          return <li key={item.id} className={`flex gap-3 px-4 py-3 ${item.read ? "" : "bg-[#00a2ff]/[0.04]"}`} data-testid="notification-item" data-read={item.read}>
            <span className={`w-8 h-8 rounded-lg shrink-0 flex items-center justify-center ${color}`}><Icon size={16} aria-hidden="true" /></span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2"><span className="text-[12px] font-bold">{t(`notifications.${item.type}`)}</span>{!item.read && <span className="ml-auto w-1.5 h-1.5 shrink-0 rounded-full bg-[#00a2ff]" />}</div>
              {item.item_name && <div className="text-[12px] mt-1 break-words">{item.item_name}</div>}
              {item.amount != null && <div className="text-[12px] mt-1 font-medium text-[#ffb000]">{item.type === "deposit_confirmed" ? "+" : ""}{formatMoney(item.amount)} RAP</div>}
              {item.reason && <div className="text-[11px] mt-1 text-[#ff8a8a] whitespace-pre-wrap break-words">{t("withdrawals.reason")}: {rejectionReasonText(item.reason, t)}</div>}
              {item.type === "withdrawal_cancelled" && <div className="text-[11px] mt-1 text-[#8e91a3]">{t("withdrawals.returned")}</div>}
              <time dateTime={item.created_at} className="block mt-1.5 text-[10px] text-[#8e91a3]">{parseServerDate(item.created_at).toLocaleString(lang === "en" ? "en-US" : "ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</time>
            </div>
          </li>;
        })}
      </ul>
    </PopoverContent>
  </Popover>;
}
