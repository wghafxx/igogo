import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { UserPlusIcon } from "./icons/user-plus";
import { LinkIcon } from "./icons/link";
import { ExternalLinkIcon } from "./icons/external-link";
import { api } from "../lib/api";
import { useAuth } from "../hooks/useAuth";

export default function RobloxLinkCard() {
  const { authUser, setAuthUser } = useAuth();
  const [open, setOpen] = useState(false);
  const [nick, setNick] = useState(authUser?.roblox_nick || "");
  const [link, setLink] = useState(authUser?.roblox_link || "");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) { setNick(authUser?.roblox_nick || ""); setLink(authUser?.roblox_link || ""); }
  }, [open, authUser?.roblox_nick, authUser?.roblox_link]);

  const save = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const u = await api.saveRoblox({ roblox_nick: nick.trim(), roblox_link: link.trim() });
      setAuthUser(u);
      setOpen(false);
      toast.success("Roblox-профиль сохранён");
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Проверьте ник (3–20 символов) и ссылку на профиль");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {authUser?.roblox_nick ? (
        <div className="rounded-lg bg-[#1c1d25] px-3 py-2 flex items-center gap-2 text-[12px]" data-testid="roblox-info">
          <div className="min-w-0 flex-1">
            <div className="text-[#7d8194] text-[10px] uppercase">Roblox</div>
            <div className="font-bold truncate" data-testid="roblox-nick">{authUser.roblox_nick}</div>
          </div>
          <a href={authUser.roblox_link} target="_blank" rel="noopener noreferrer" className="text-[#00a2ff] hover:text-white" title="Открыть профиль" data-testid="roblox-profile-link">
            <ExternalLinkIcon size={14} />
          </a>
          <button onClick={() => setOpen(true)} className="text-[#8e91a3] hover:text-white text-[11px] font-bold" data-testid="roblox-edit-button">
            Изменить
          </button>
        </div>
      ) : (
        <button onClick={() => setOpen(true)} className="h-9 rounded-lg bg-[#00a2ff] hover:bg-[#1ab0ff] text-white text-[12px] font-bold flex items-center justify-center gap-2 transition-colors" data-testid="roblox-add-button">
          <UserPlusIcon size={14} /> Добавить ник Roblox
        </button>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-[#1e1f23] border-0 text-white sm:max-w-[460px] p-0 overflow-hidden rounded-2xl" data-testid="roblox-dialog">
          <DialogHeader className="px-6 py-4 border-b border-[#2a2b31]">
            <DialogTitle className="text-[17px] font-bold text-left">Roblox-профиль</DialogTitle>
          </DialogHeader>
          <div className="px-6 pt-4 pb-6 space-y-4">
            <div className="rounded-lg bg-[#00a2ff]/10 border border-[#00a2ff]/40 px-3 py-2.5 text-[12px] text-[#b4d9ff] leading-relaxed" data-testid="roblox-help">
              Где взять ссылку: откройте свой профиль в Roblox → раздел <b>Друзья</b> → нажмите на иконку <b>QR-кода</b>. Там будет ваш QR-код и <b>ссылка на профиль</b> — скопируйте её и вставьте сюда.
            </div>
            <label className="block space-y-1.5">
              <span className="text-[12px] text-[#8e91a3]">Ник в Roblox</span>
              <input value={nick} onChange={(e) => setNick(e.target.value)} placeholder="Например: Builderman" className="w-full h-11 px-3 rounded-lg bg-[#0f1015] outline-none text-[13px] font-bold focus:ring-1 focus:ring-[#00a2ff]" data-testid="roblox-nick-input" />
            </label>
            <label className="block space-y-1.5">
              <span className="text-[12px] text-[#8e91a3]">Ссылка на профиль (Profile link)</span>
              <div className="flex items-center gap-2 h-11 px-3 rounded-lg bg-[#0f1015] focus-within:ring-1 focus-within:ring-[#00a2ff]">
                <LinkIcon size={14} className="text-[#7d8194] shrink-0" />
                <input value={link} maxLength={400} onChange={(e) => setLink(e.target.value)} placeholder="https://www.roblox.com/share?code=..." className="flex-1 min-w-0 bg-transparent outline-none text-[13px]" data-testid="roblox-link-input" />
              </div>
            </label>
            <button onClick={save} disabled={busy || nick.trim().length < 3 || link.trim().length < 10} className="w-full h-11 rounded-lg bg-[#00a2ff] hover:bg-[#1ab0ff] disabled:opacity-40 text-white font-bold text-[14px] transition-colors" data-testid="roblox-save-button">
              Сохранить
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
