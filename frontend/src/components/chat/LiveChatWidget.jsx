import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { X, Send, RotateCcw, LogOut, Paperclip } from "lucide-react";
import supportCat from "../../assets/support-cat.webp";
import "animate.css";
import { useLang } from "../../lib/i18n";
import { useLiveChat } from "../../hooks/useLiveChat";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../lib/api";
import ChatMessages from "./ChatMessages";

const STATUS = { open: ["chat.waiting", "bg-[#ffe44d]"], active: ["chat.active", "bg-[#61d899]"], closed: ["chat.closed", "bg-white/30"] };

const useCountdown = (until) => {
  const [left, setLeft] = useState(() => Math.max(0, Math.ceil((until - Date.now()) / 1000)));
  useEffect(() => {
    const tick = () => setLeft(Math.max(0, Math.ceil((until - Date.now()) / 1000)));
    tick();
    if (!until || until <= Date.now()) return undefined;
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [until]);
  return left;
};
const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

const AttachButton = ({ onAttach, disabled }) => {
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const pick = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || busy) return;
    setBusy(true);
    try { await onAttach(file); toast.success(t("chat.screenshot_sent")); }
    catch (err) { toast.error(err?.response?.data?.detail || (err?.message === "too large" ? t("chat.screenshot_too_big") : t("chat.screenshot_error"))); }
    finally { setBusy(false); }
  };
  return (
    <>
      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={pick} data-testid="chat-attach-input" />
      <button type="button" onClick={() => fileRef.current?.click()} disabled={busy || disabled} className="m-iconbtn shrink-0 disabled:opacity-40" aria-label={t("chat.attach")} title={t("chat.attach_hint")} data-testid="chat-attach-button">
        <Paperclip size={16} className={busy ? "animate-pulse" : ""} />
      </button>
    </>
  );
};

const Composer = ({ onSend, onAttach, disabled, autoFocus }) => {
  const { t } = useLang();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);
  const submit = async () => {
    if (!text.trim() || busy || disabled) return;
    inputRef.current?.focus({ preventScroll: true });
    setBusy(true);
    try { await onSend(text); setText(""); } catch (e) { toast.error(e?.response?.data?.detail || t("chat.send_error")); } finally { setBusy(false); }
  };
  return (
    <div className="chat-foot p-3 flex items-end gap-2 shrink-0">
      <div className="m-input m-input-sm flex-1 !h-auto min-h-[48px] py-2 items-end">
        {onAttach && <AttachButton onAttach={onAttach} disabled={disabled} />}
        <textarea ref={inputRef} readOnly={busy} autoFocus={autoFocus} value={text} onChange={(e) => setText(e.target.value.slice(0, 2000))} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }} rows={1} placeholder={t("chat.placeholder")} className="flex-1 min-w-0 max-h-32 resize-none bg-transparent outline-none text-[14px] font-medium placeholder:text-white/30 placeholder:font-normal leading-[22px] py-[5px]" data-testid="chat-input" />
        <button onClick={submit} onMouseDown={(e) => e.preventDefault()} disabled={busy || !text.trim() || disabled} className="m-iconbtn shrink-0" data-active={text.trim() ? "true" : "false"} aria-label={t("chat.send")} data-testid="chat-send-button">
          <Send size={16} />
        </button>
      </div>
    </div>
  );
};

const CooldownNote = ({ label, until, testId }) => {
  const left = useCountdown(until);
  if (!left) return null;
  return <span className="text-[11px] text-white/40 tabular-nums" data-testid={testId}>{label} {mmss(left)}</span>;
};

export default function LiveChatWidget() {
  const { t } = useLang();
  const chat = useLiveChat();
  const { authUser } = useAuth();
  const [busy, setBusy] = useState(false);
  const left = useCountdown(chat.cooldownUntil);
  const status = chat.chat ? STATUS[chat.chat.status] : null;
  const closed = chat.chat?.status === "closed";
  const act = async (fn, ok) => {
    if (busy) return;
    setBusy(true);
    try { await fn(); toast.success(t(ok)); } catch (e) { toast.error(e?.response?.status === 429 ? t("chat.cooldown_toast") : (e?.response?.data?.detail || t("common.error"))); } finally { setBusy(false); }
  };
  return (
    <>
      {chat.open && (
        <div className="chat-surface fixed z-[60] bottom-24 right-3 sm:right-6 w-[calc(100vw-24px)] sm:w-[440px] h-[min(680px,calc(100vh-120px))] flex flex-col overflow-hidden animate__animated animate__fadeInUp animate__faster" data-testid="live-chat-panel">
          <div className="modal-head relative h-[72px] px-5 flex items-center gap-3 shrink-0">
            <span className="relative w-12 h-12 rounded-2xl m-box overflow-hidden shrink-0"><img src={supportCat} alt="" className="w-full h-full object-cover" draggable={false} /><span className={`absolute bottom-0.5 right-0.5 w-3 h-3 rounded-full border-2 border-[#1a1b1f] ${status ? status[1] : "bg-[#61d899]"}`} data-testid="live-chat-presence" /></span>
            <div className="min-w-0 flex-1">
              <div className="modal-title truncate" data-testid="live-chat-title">{t("chat.support")}</div>
              <div className="text-[12px] text-white/50 flex items-center gap-1.5 truncate" data-testid="live-chat-status">
                {status ? t(status[0]) : t("chat.online")}
              </div>
            </div>
            {chat.chat && !closed && (
              <button onClick={() => act(chat.close, "chat.ended")} disabled={busy || left > 0} title={left > 0 ? `${t("chat.end_in")} ${mmss(left)}` : t("chat.end")} className="m-chip !h-9 flex items-center gap-1.5 font-medium disabled:opacity-40" data-testid="live-chat-end">
                <LogOut size={13} /> <span className="hidden sm:inline">{t("chat.end")}</span>
              </button>
            )}
            <button onClick={() => chat.setOpen(false)} className="modal-close !static" aria-label="close" data-testid="live-chat-close"><X size={18} /></button>
          </div>
          {chat.error && <div className="mx-4 mt-3 rounded-[10px] m-note-err px-3 py-2 text-[12px] flex items-center justify-between" role="alert"><span>{t("common.error")}</span><button onClick={chat.retry} className="underline" data-testid="chat-retry">{t("common.retry")}</button></div>}
          {chat.chat ? (
            <>
              <ChatMessages messages={chat.messages} mine="user" chatId={chat.chat.id} loadImage={api.chatAttachment} onPaid={authUser ? chat.markPaid : undefined} />
              {closed ? (
                <div className="chat-foot p-4 space-y-3 shrink-0" data-testid="live-chat-closed">
                  <p className="m-hint !text-[12px] !text-white/50">{t("chat.closed_hint")}</p>
                  <button onClick={() => act(chat.reopen, "chat.reopened")} disabled={busy || left > 0} className="m-cta !text-[15px]" data-testid="live-chat-reopen">
                    <RotateCcw size={15} /> {left > 0 ? `${t("chat.reopen_in")} ${mmss(left)}` : t("chat.reopen")}
                  </button>
                </div>
              ) : left > 0 && <div className="px-4 py-1.5 text-center"><CooldownNote label={t("chat.end_in")} until={chat.cooldownUntil} testId="live-chat-cooldown" /></div>}
            </>
          ) : (
            <>
              <div className="flex-1 min-h-0" />
            </>
          )}
          {!closed && <Composer onSend={chat.send} onAttach={authUser && chat.chat ? chat.attach : undefined} autoFocus />}
        </div>
      )}
      <button
        onClick={() => chat.setOpen(!chat.open)}
        className="blox-btn-dark chat-toggle fixed z-[60] bottom-5 right-3 sm:right-6 h-[56px] px-5 sm:min-w-[170px] justify-center !rounded-full flex items-center gap-2.5 text-[14px] hover:scale-105 active:scale-95"
        aria-label={t("chat.support")}
        data-testid="live-chat-toggle"
      >
        {chat.open ? <X size={22} /> : <img src={supportCat} alt="" className="w-8 h-8 rounded-full object-cover -ml-1" draggable={false} />}
        <span className="hidden sm:inline">{t("chat.support")}</span>
        {!chat.open && chat.unread > 0 && <span className="absolute -top-1 -right-1 h-6 min-w-6 px-1.5 rounded-full bg-[var(--control-accent)] text-[var(--control-ink)] text-[11px] font-black flex items-center justify-center border-2 border-[#0d0e12] animate__animated animate__heartBeat animate__infinite animate__slow" data-testid="live-chat-unread">{chat.unread}</span>}
      </button>
    </>
  );
}
