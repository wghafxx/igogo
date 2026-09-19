import React from "react";
import { Search, X, ExternalLink, MessageSquare } from "lucide-react";
import { formatMoney } from "../../../lib/api";
import { Avatar, STATUS, fmtTime, Btn } from "./ui";

const FILTERS = [["open", "Новые"], ["active", "В работе"], ["closed", "Закрытые"], ["all", "Все"]];

const waitLabel = (sec) => {
  const m = Math.floor(sec / 60);
  if (m < 1) return "ждёт <1 мин";
  if (m < 60) return `ждёт ${m} мин`;
  const h = Math.floor(m / 60);
  return h < 48 ? `ждёт ${h} ч` : `ждёт ${Math.floor(h / 24)} дн`;
};
const waitTone = (sec) => (sec >= 3600 ? "text-[#ff8a8a]" : sec >= 900 ? "text-[#ffcf5a]" : "text-[#8e91a3]");

const ChatItem = ({ c, selected, onPick }) => {
  const s = STATUS[c.status] || STATUS.closed;
  const preview = c.last_message ? `${c.last_message.sender === "admin" ? "Вы: " : ""}${c.last_message.text}` : "Без сообщений";
  return (
    <button onClick={() => onPick(c.id)} className={`w-full text-left flex items-start gap-3 px-3 py-3 rounded-xl transition-colors ${selected ? "bg-white/[0.08]" : "hover:bg-white/[0.04]"}`} data-testid={`admin-chat-item-${c.id}`}>
      <Avatar src={c.avatar} name={c.nickname} size={42} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${c.online ? "bg-[#2ecc71] shadow-[0_0_6px_#2ecc71]" : "bg-[#5f6377]"}`} title={c.online ? "Онлайн" : "Не в сети"} data-testid={c.online ? "admin-chat-online" : "admin-chat-offline"} />
          <span className="text-[13px] font-bold truncate">{c.nickname}</span>
          {c.guest && <span className="text-[10px] text-[#8e91a3] bg-white/[0.06] rounded px-1">гость</span>}
          <span className="ml-auto text-[10px] text-[#6b6f84] shrink-0">{fmtTime(c.updated_at)}</span>
        </span>
        <span className="mt-0.5 flex items-center gap-2">
          <span className={`text-[12px] truncate ${c.admin_unread > 0 ? "text-white font-semibold" : "text-[#8e91a3]"}`}>{preview}</span>
          {c.admin_unread > 0 && <span className="ml-auto h-5 min-w-5 px-1.5 rounded-full bg-[#ffb000] text-black text-[10px] font-black flex items-center justify-center shrink-0" data-testid="admin-chat-unread">{c.admin_unread}</span>}
        </span>
        <span className="mt-1 flex items-center gap-2 text-[11px]">
          <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} title={s.label} />
          {c.waiting_seconds != null && <span className={`font-bold ${waitTone(c.waiting_seconds)}`} data-testid="admin-chat-waiting">{waitLabel(c.waiting_seconds)}</span>}
          {c.balance != null && <span className="ml-auto text-[#7ee2a8] font-bold tabular-nums" data-testid="admin-chat-list-balance">{formatMoney(c.balance)} RAP</span>}
        </span>
      </span>
    </button>
  );
};

const PlayerHit = ({ u, onOpen }) => (
  <div className="flex items-start gap-3 px-3 py-3 rounded-xl bg-white/[0.03]" data-testid={`admin-search-user-${u.session_id}`}>
    <Avatar src={u.avatar} name={u.nickname} size={36} />
    <div className="min-w-0 flex-1 space-y-1">
      <div className="flex items-center gap-2 text-[13px]"><span className="font-bold truncate">{u.nickname}</span><span className="text-[11px] text-[#6b6f84] font-mono">{u.discord_id}</span></div>
      <div className="text-[11px] text-[#a4a7b8] flex flex-wrap gap-x-3">
        <span>Баланс <b className="text-[#7ee2a8]">{formatMoney(u.balance)}</b></span>
        <span>Скинов <b className="text-white">{u.skins_count}</b></span>
        {u.pending_withdrawals > 0 && <span className="text-[#ffcf5a]">вывод {u.pending_withdrawals} шт</span>}
      </div>
      <div className="text-[11px] text-[#a4a7b8] truncate">
        {u.roblox_link ? <a href={u.roblox_link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[#9fd6ff] hover:text-white">Roblox: {u.roblox_nick} <ExternalLink size={10} /></a> : <span className="text-[#ff9b9b]">Roblox не привязан</span>}
      </div>
      {u.chat_id ? <Btn size="sm" onClick={() => onOpen(u.chat_id)} data-testid="admin-search-open-chat"><MessageSquare size={12} /> Открыть чат</Btn> : <span className="text-[11px] text-[#6b6f84]">Чата ещё нет</span>}
    </div>
  </div>
);

export default function ChatSidebar({ q, setQ, status, setStatus, rows, found, selected, onPick, onOpenUser, counts }) {
  return (
    <aside className="flex flex-col min-h-0 rounded-2xl bg-[#0f1015] border border-white/[0.05]" data-testid="admin-chat-sidebar">
      <div className="p-3 space-y-3 border-b border-white/[0.05]">
        <div className="flex items-center gap-2 h-11 px-3 rounded-xl bg-white/[0.05] focus-within:bg-white/[0.08] transition-colors">
          <Search size={15} className="text-[#8e91a3] shrink-0" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ник, Discord ID, Roblox-ник или ссылка" className="flex-1 min-w-0 bg-transparent outline-none text-[13px] placeholder:text-[#6b6f84]" data-testid="admin-chat-search" />
          {q && <button onClick={() => setQ("")} className="text-[#8e91a3] hover:text-white" aria-label="Очистить" data-testid="admin-chat-search-clear"><X size={14} /></button>}
        </div>
        <div className="grid grid-cols-4 gap-1 p-1 rounded-xl bg-white/[0.04]">
          {FILTERS.map(([k, label]) => (
            <button key={k} onClick={() => setStatus(k)} className={`h-8 rounded-lg text-[11px] font-bold transition-colors flex items-center justify-center gap-1 ${status === k ? "bg-[#ffb000] text-black" : "text-[#8e91a3] hover:text-white"}`} data-testid={`admin-chats-${k}`}>
              {label}{k === "open" && counts?.open > 0 && <span className={`text-[10px] ${status === k ? "text-black/60" : "text-[#ffb000]"}`}>{counts.open}</span>}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-1" data-testid="admin-chat-list">
        {found.length > 0 && (
          <div className="space-y-1 pb-2 mb-1 border-b border-white/[0.05]" data-testid="admin-search-results">
            <div className="px-3 pt-1 pb-1 text-[10px] font-bold uppercase tracking-wider text-[#6b6f84]">Игроки · {found.length}</div>
            {found.map((u) => <PlayerHit key={u.session_id} u={u} onOpen={onOpenUser} />)}
          </div>
        )}
        {rows.length === 0 && <div className="h-[140px] flex flex-col items-center justify-center gap-2 text-[12px] text-[#6b6f84]" data-testid="admin-chats-empty"><MessageSquare size={20} /> Чатов нет</div>}
        {rows.map((c) => <ChatItem key={c.id} c={c} selected={selected === c.id} onPick={onPick} />)}
      </div>
    </aside>
  );
}
