import React, { useEffect, useRef } from "react";
import { parseServerDate } from "../../lib/api";
import { useLang } from "../../lib/i18n";
import { RobuxIcon } from "../Logo";
import { ChatImage, DonationCard } from "./ChatExtras";

const timeOf = (d, lang) => parseServerDate(d).toLocaleTimeString(lang === "en" ? "en-US" : "ru-RU", { hour: "2-digit", minute: "2-digit" });

export const LinkedMessage = ({ text, own = false }) => <>{text.split(/(https?:\/\/[^\s<>"']+)/g).map((part, i) => {
  if (!/^https?:\/\//.test(part)) return part;
  const url = part.replace(/[.,!?;:)}\]]+$/, "");
  return <React.Fragment key={i}><a href={url} target="_blank" rel="noopener noreferrer" className={`font-medium underline underline-offset-2 break-all transition-colors ${own ? "text-[#075985] hover:text-[#0369a1]" : "text-[#60a5fa] hover:text-[#93c5fd]"}`}>{url}</a>{part.slice(url.length)}</React.Fragment>;
})}</>;

// mine = which sender is rendered on the right side ("user" for the site, "admin" for the panel)
export default function ChatMessages({ messages, mine = "user", className = "", testId = "chat-messages", chatId, loadImage, onPaid }) {
  const { t, lang } = useLang();
  const bottomRef = useRef(null);
  const lastMessageId = messages[messages.length - 1]?.id;
  useEffect(() => { bottomRef.current?.scrollIntoView?.({ block: "end" }); }, [lastMessageId]);
  return (
    <div className={`flex-1 min-h-0 overflow-y-auto px-3 py-3 space-y-2 ${className}`} data-testid={testId}>
      {messages.map((m) => {
        if (m.sender === "system") return (
          <div key={m.id} className="flex justify-center py-1" data-testid="chat-message-system">
            <span className="max-w-[92%] text-center text-[11px] leading-snug whitespace-pre-wrap break-words text-white/45 bg-white/[0.05] rounded-full px-3 py-1.5"><LinkedMessage text={m.text} /></span>
          </div>
        );
        const own = m.sender === mine;
        return (
          <div key={m.id} className={`flex ${own ? "justify-end" : "justify-start"} chat-pop`} data-testid={`chat-message-${m.sender}`}>
            <div className={`max-w-[82%] rounded-2xl px-3.5 py-2 text-[13px] leading-snug break-words ${own ? "chat-bubble-own rounded-br-md" : "chat-bubble rounded-bl-md"}`}>
              {m.kind === "deposit_request" && (
                <div className={`mb-1 inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-black uppercase tracking-wide ${own ? "bg-black/10" : "m-note-warn"}`}>
                  {t("chat.deposit")} · ~{Number(m.expected_rap).toFixed(0)} <RobuxIcon size={10} />
                </div>
              )}
              {m.kind === "withdrawal_request" && (
                <div className={`mb-1 inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-black uppercase tracking-wide ${own ? "bg-black/10" : "m-note-warn"}`}>
                  {t("chat.withdrawal")} · {m.count} · ~{Number(m.total).toFixed(0)} <RobuxIcon size={10} />
                </div>
              )}
              {m.kind === "image" ? <ChatImage chatId={chatId} message={m} load={loadImage} /> : <div className="whitespace-pre-wrap"><LinkedMessage text={m.text} own={own} /></div>}
              {m.kind === "da_instructions" && <DonationCard message={m} onPaid={onPaid} />}
              <div className={`mt-0.5 text-[10px] text-right ${own ? "text-black/50" : "text-white/40"}`}>{m.sender === "admin" && mine !== "admin" ? `${t("chat.operator")} · ` : ""}{timeOf(m.created_at, lang)}</div>
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
