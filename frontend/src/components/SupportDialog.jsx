import React from "react";
import { toast } from "sonner";
import { SendIcon } from "./icons/send";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { useLang } from "../lib/i18n";

export const SUPPORT_HANDLE = process.env.REACT_APP_TELEGRAM_SUPPORT_HANDLE || "@bloxgradesupport";
const SUPPORT_URL = process.env.REACT_APP_TELEGRAM_SUPPORT_URL || "https://t.me/bloxgradesupport";

export const SupportDialog = ({ request, onClose }) => {
  const { t } = useLang();
  const withdrawal = request?.kind === "withdrawal";
  const copyHandle = async () => {
    try {
      await navigator.clipboard.writeText(SUPPORT_HANDLE);
      toast.success(t("support.copied"));
    } catch { toast.error(`${t("support.copy_fail")} ${SUPPORT_HANDLE} ${t("support.copy_fail_tail")}`); }
  };
  return (
    <Dialog open={Boolean(request)} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="w-[92vw] max-w-[420px] max-h-[90dvh] overflow-y-auto bg-[#16171d] border-0 text-white p-6" aria-describedby="support-dialog-description" data-testid="support-dialog">
        <DialogHeader className="text-left">
          <div className="w-11 h-11 rounded-xl bg-[#00a2ff]/15 text-[#00a2ff] flex items-center justify-center mb-2" aria-hidden="true"><SendIcon size={22} /></div>
          <DialogTitle className="text-lg font-bold" data-testid="support-dialog-title">{withdrawal ? t("support.withdrawal") : t("support.title")}</DialogTitle>
          <DialogDescription id="support-dialog-description" className="text-[#a6a9bb] text-sm leading-relaxed" data-testid="support-dialog-description">
            {t("support.text")}
          </DialogDescription>
        </DialogHeader>
        {withdrawal && <div className="rounded-lg bg-[#2ecc71]/10 text-[#72dca0] text-sm px-3 py-2.5" role="status" data-testid="support-withdrawal-status">
          {t("support.created")} <span data-testid="support-withdrawal-count">{t("support.items")} {request.count}.</span> {t("support.contact_us")}
        </div>}
        <div className="rounded-xl bg-[#0f1015] p-4 flex flex-wrap items-center justify-between gap-3">
          <span className="font-bold text-lg" data-testid="support-telegram-handle">{SUPPORT_HANDLE}</span>
          <button type="button" onClick={copyHandle} className="text-xs text-[#00a2ff] hover:text-[#63c6ff] transition-colors" data-testid="support-copy-handle">{t("support.copy")}</button>
        </div>
        {withdrawal && <p className="text-xs text-[#8e91a3] leading-relaxed" data-testid="support-withdrawal-instructions">{t("support.dm_note")}</p>}
        <a href={SUPPORT_URL} target="_blank" rel="noopener noreferrer" className="blox-btn-primary min-h-11 px-4 py-3 flex items-center justify-center gap-2 text-sm font-bold" data-testid="support-telegram-link">
          <SendIcon size={16} /> {t("support.write")}
        </a>
      </DialogContent>
    </Dialog>
  );
};