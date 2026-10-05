import React from "react";
import { toast } from "sonner";
import TelegramIcon from "./TelegramIcon";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { useLang } from "../lib/i18n";

export const SUPPORT_HANDLE = process.env.REACT_APP_TELEGRAM_SUPPORT_HANDLE || "@bloxgradesupport";
const SUPPORT_URL = process.env.REACT_APP_TELEGRAM_SUPPORT_URL || "https://t.me/bloxgradesupport";

export const SupportDialog = ({ request, onClose }) => {
  const { t } = useLang();
  const copyHandle = async () => {
    try {
      await navigator.clipboard.writeText(SUPPORT_HANDLE);
      toast.success(t("support.copied"));
    } catch { toast.error(`${t("support.copy_fail")} ${SUPPORT_HANDLE} ${t("support.copy_fail_tail")}`); }
  };
  return (
    <Dialog open={Boolean(request)} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="modal-surface w-[92vw] max-w-[440px] max-h-[90dvh] overflow-y-auto border-0 text-white p-6" data-testid="support-dialog">
        <DialogHeader className="text-left">
          <div className="w-12 h-12 rounded-xl bg-[#fdd911]/15 text-[#fdd911] flex items-center justify-center mb-2" aria-hidden="true"><TelegramIcon size={22} /></div>
          <DialogTitle className="modal-title" data-testid="support-dialog-title">{t("support.title")}</DialogTitle>
          <DialogDescription className="text-white/50 text-sm leading-relaxed" data-testid="support-dialog-description">{t("support.text")}</DialogDescription>
        </DialogHeader>
        <div className="m-box p-4 flex flex-wrap items-center justify-between gap-3">
          <span className="font-bold text-lg" data-testid="support-telegram-handle">{SUPPORT_HANDLE}</span>
          <button type="button" onClick={copyHandle} className="m-cta m-cta-ghost !w-auto !h-9 !text-[13px] !px-4" data-testid="support-copy-handle">{t("support.copy")}</button>
        </div>
        <a href={SUPPORT_URL} target="_blank" rel="noopener noreferrer" className="m-cta" data-testid="support-telegram-link">
          <TelegramIcon size={16} /> {t("support.write")}
        </a>
      </DialogContent>
    </Dialog>
  );
};
