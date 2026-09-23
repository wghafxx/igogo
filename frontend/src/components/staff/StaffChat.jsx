import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Send } from "lucide-react";
import ChatMessages from "../chat/ChatMessages";
import { staffApi, errText } from "../../lib/staff-api";

export default function StaffChat({ depId, closed }) {
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => staffApi.messages(depId).then(setMessages).catch(() => {}), [depId]);
  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [load]);
  const loadImage = useCallback((_, attachmentId) => staffApi.chatAttachment(depId, attachmentId), [depId]);
  const send = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try { await staffApi.send(depId, text.trim()); setText(""); await load(); }
    catch (e) { toast.error(errText(e, "Не отправлено")); }
    finally { setBusy(false); }
  };
  return (
    <section className="flex flex-col min-h-[420px] h-full rounded-2xl bg-[#0f1015] border border-white/[0.05]" data-testid="staff-chat">
      <header className="h-11 px-4 flex items-center border-b border-white/[0.05] text-[12px] font-bold uppercase tracking-wide text-[#c9ccd6]">Чат с игроком</header>
      <ChatMessages messages={messages} mine="admin" testId="staff-chat-messages" className="px-4 py-3" chatId={depId} loadImage={loadImage} />
      <div className="p-3 border-t border-white/[0.05] flex gap-2">
        <input value={text} disabled={closed} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} maxLength={1000}
          placeholder={closed ? "Заявка закрыта" : "Написать игроку…"} className="flex-1 h-10 rounded-xl bg-white/[0.05] px-3 text-[13px] outline-none" data-testid="staff-chat-input" />
        <button type="button" onClick={send} disabled={busy || closed || !text.trim()} className="h-10 w-10 rounded-xl bg-[#ffb000] text-black flex items-center justify-center disabled:opacity-40" data-testid="staff-chat-send"><Send size={15} /></button>
      </div>
    </section>
  );
}
