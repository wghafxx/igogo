import React from "react";
import { toast } from "sonner";
import { SendIcon } from "./icons/send";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { useLang } from "../lib/i18n";

export const SUPPORT_HANDLE = process.env.REACT_APP_TELEGRAM_SUPPORT_HANDLE || "@bloxgradesupport";
export const WITHDRAWAL_ACCOUNT = "ysrent1";
const SUPPORT_URL = process.env.REACT_APP_TELEGRAM_SUPPORT_URL || "https://t.me/bloxgradesupport";

export const SupportDialog = ({ request, onClose }) => {
  const { t } = useLang();
  const withdrawal = request?.kind === "withdrawal";
  const handle = withdrawal ? WITHDRAWAL_ACCOUNT : SUPPORT_HANDLE;
  const copyHandle = async () => {
    try {
      await navigator.clipboard.writeText(handle);
      toast.success(t(withdrawal ? "support.nick_copied" : "support.copied"));
    } catch { toast.error(withdrawal ? `${t("support.nick_copy_fail")} ${handle}` : `${t("support.copy_fail")} ${handle} ${t("support.copy_fail_tail")}`); }
  };
  return (
    <Dialog open={Boolean(request)} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="w-[92vw] max-w-[420px] max-h-[90dvh] overflow-y-auto bg-[#16171d] border-0 text-white p-6" data-testid="support-dialog">
        <DialogHeader className="text-left">
          <div className="w-11 h-11 rounded-xl bg-[#00a2ff]/15 text-[#00a2ff] flex items-center justify-center mb-2" aria-hidden="true"><SendIcon size={22} /></div>
          <DialogTitle className="text-lg font-bold" data-testid="support-dialog-title">{withdrawal ? t("support.withdrawal") : t("support.title")}</DialogTitle>
          <DialogDescription className="text-[#a6a9bb] text-sm leading-relaxed" data-testid="support-dialog-description">
            {t(withdrawal ? "support.trade_intro" : "support.text")}
          </DialogDescription>
        </DialogHeader>
        {withdrawal && <div className="rounded-lg bg-[#2ecc71]/10 text-[#72dca0] text-sm px-3 py-2.5" role="status" data-testid="support-withdrawal-status">
          {t("support.queued")} <span data-testid="support-withdrawal-count">{t("support.items")} {request.count}.</span>
        </div>}
        {withdrawal && <ol className="list-decimal pl-5 space-y-2 text-sm text-[#c9ccd8] leading-relaxed" data-testid="support-withdrawal-instructions">
          <li>{t("support.trade_join")} <b className="text-white">{WITHDRAWAL_ACCOUNT}</b>.</li>
          <li>{t("support.trade_send")}</li>
          <li>{t("support.trade_receive")}</li>
        </ol>}
        <div className="rounded-xl bg-[#0f1015] p-4 flex flex-wrap items-center justify-between gap-3">
          <div>{withdrawal && <div className="text-[11px] text-[#8e91a3] mb-1">{t("support.trade_account")}</div>}<span className="font-bold text-lg" data-testid={withdrawal ? "support-withdrawal-account" : "support-telegram-handle"}>{handle}</span></div>
          <button type="button" onClick={copyHandle} className="text-xs text-[#00a2ff] hover:text-[#63c6ff] transition-colors" data-testid="support-copy-handle">{t("support.copy")}</button>
        </div>
        {withdrawal && <a href="/profile?tab=withdrawals" onClick={onClose} className="blox-btn-primary min-h-11 px-4 py-3 flex items-center justify-center text-sm font-bold" data-testid="support-withdrawal-history">{t("support.view_withdrawals")}</a>}
        <a href={SUPPORT_URL} target="_blank" rel="noopener noreferrer" className={withdrawal ? "text-xs text-[#8e91a3] hover:text-[#00a2ff] flex items-center justify-center gap-2 py-1" : "blox-btn-primary min-h-11 px-4 py-3 flex items-center justify-center gap-2 text-sm font-bold"} data-testid="support-telegram-link">
          <SendIcon size={16} /> {t(withdrawal ? "support.help" : "support.write")}
        </a>
      </DialogContent>
    </Dialog>
  );
};
