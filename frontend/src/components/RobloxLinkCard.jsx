import React, { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { UserPlusIcon } from "./icons/user-plus";
import { ExternalLinkIcon } from "./icons/external-link";
import { useAuth } from "../hooks/useAuth";
import { useLang } from "../lib/i18n";

import RobloxProfileStepper from "./RobloxProfileStepper";

export default function RobloxLinkCard() {
  const { authUser } = useAuth();
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  return (
    <>
      {authUser?.roblox_nick ? (
        <div className="rounded-lg bg-[#1c1d25] px-3 py-2 flex items-center gap-2 text-[12px]" data-testid="roblox-info">
          <div className="min-w-0 flex-1">
            <div className="text-[#7d8194] text-[10px] uppercase">Roblox</div>
            <div className="font-bold truncate" data-testid="roblox-nick">{authUser.roblox_display_name || authUser.roblox_nick}</div><div className="text-[#8e91a3]">@{authUser.roblox_nick}</div>
          </div>
          <a href={authUser.roblox_link} target="_blank" rel="noopener noreferrer" className="text-[#00a2ff] hover:text-white" title={t("profile.roblox_open")} data-testid="roblox-profile-link">
            <ExternalLinkIcon size={14} />
          </a>
          <button onClick={() => setOpen(true)} className="text-[#8e91a3] hover:text-white text-[11px] font-bold" data-testid="roblox-edit-button">
            {t("profile.roblox_edit")}
          </button>
        </div>
      ) : (
        <button onClick={() => setOpen(true)} className="h-9 rounded-lg bg-[#00a2ff] hover:bg-[#1ab0ff] text-white text-[12px] font-bold flex items-center justify-center gap-2 transition-colors" data-testid="roblox-add-button">
          <UserPlusIcon size={14} /> {t("profile.roblox_add")}
        </button>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="modal-surface border-0 text-white w-[calc(100%-1.25rem)] sm:max-w-[520px] p-0 overflow-hidden max-h-[92vh] flex flex-col gap-0" data-testid="roblox-dialog">
          <DialogHeader className="modal-head px-6 py-4 text-left">
            <DialogTitle className="text-[17px] font-bold text-left">{t("profile.roblox_title")}</DialogTitle>
          </DialogHeader>
          <div className="px-6 pt-4 pb-6 overflow-y-auto">
            <RobloxProfileStepper onSaved={() => setOpen(false)} />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
