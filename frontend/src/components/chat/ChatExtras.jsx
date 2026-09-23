import React, { useEffect, useState } from "react";
import { Copy, ExternalLink, ImageOff } from "lucide-react";
import { toast } from "sonner";
import { useLang } from "../../lib/i18n";
import { parseServerDate } from "../../lib/api";

// Private screenshot: fetched with the auth header, shown from an object URL.
export const ChatImage = ({ chatId, message, load }) => {
  const { t } = useLang();
  const [url, setUrl] = useState(null);
  const [gone, setGone] = useState(false);
  const expired = message.expires_at && parseServerDate(message.expires_at) <= new Date();
  useEffect(() => {
    if (expired || !load) return undefined;
    let alive = true;
    let objectUrl = null;
    load(chatId, message.attachment_id)
      .then((blob) => { if (!alive) return; objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); })
      .catch(() => { if (alive) setGone(true); });
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [chatId, message.attachment_id, expired, load]);
  if (expired || gone) return <div className="flex items-center gap-2 text-[12px] opacity-70" data-testid="chat-image-expired"><ImageOff size={14} /> {t("chat.image_expired")}</div>;
  if (!url) return <div className="w-48 h-32 rounded-xl bg-black/20 animate-pulse" data-testid="chat-image-loading" />;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" data-testid="chat-image-link">
      <img src={url} alt={t("chat.screenshot")} className="max-w-[240px] max-h-[260px] rounded-xl object-contain bg-black/20" data-testid="chat-image" />
    </a>
  );
};

// DonationAlerts steps: open link + one-time "I paid" button (server also refuses a second press).
export const DonationCard = ({ message, onPaid }) => {
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const [claimed, setClaimed] = useState(Boolean(message.paid_claimed));
  useEffect(() => { if (message.paid_claimed) setClaimed(true); }, [message.paid_claimed]);
  const paid = async () => {
    if (busy || claimed || !onPaid) return;
    setBusy(true);
    try { await onPaid(message.deposit_id); setClaimed(true); toast.success(t("da.paid_sent")); }
    catch (e) { if (e?.response?.status === 409) setClaimed(true); toast.error(e?.response?.data?.detail || t("common.error")); }
    finally { setBusy(false); }
  };
  return (
    <div className="mt-2 flex flex-col gap-2" data-testid="donation-card">
      {message.phrase && (
        <button type="button" onClick={() => navigator.clipboard?.writeText(message.phrase).then(() => toast.success(t("da.copied")), () => {})}
          className="text-left rounded-xl bg-black/25 px-3 py-2 hover:bg-black/35 transition-colors" data-testid="donation-phrase">
          <span className="block text-[10px] uppercase tracking-wide opacity-60">{t("da.phrase_label")}</span>
          <span className="flex items-center justify-between gap-2 font-bold text-[14px]">«{message.phrase}» <Copy size={14} className="shrink-0 opacity-70" /></span>
        </button>
      )}
      {message.url && (
        <a href={message.url} target="_blank" rel="noopener noreferrer" className="m-chip !h-10 flex items-center justify-center gap-2 font-bold" data-testid="donation-open-link">
          <ExternalLink size={14} /> {t("da.open")}
        </a>
      )}
      {onPaid && (
        <button type="button" onClick={paid} disabled={busy || claimed} className="m-cta !h-11 !text-[14px] disabled:opacity-50" data-testid="donation-paid-button">
          {claimed ? t("da.paid_done") : busy ? t("da.paid_busy") : t("da.paid")}
        </button>
      )}
    </div>
  );
};
