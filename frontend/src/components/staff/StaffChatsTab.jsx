import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { LogIn, MessagesSquare } from "lucide-react";
import { staffApi, errText } from "../../lib/staff-api";
import { Conversation } from "../admin/ChatsTab";
import ChatSidebar from "../admin/chat/ChatSidebar";
import { PlayerCard } from "../admin/chat/PlayerPanel";
import { usePolling } from "../../hooks/usePolling";
import StaffDepositCard from "./StaffDepositCard";

// Same console as the owner's chats: free chats + chats taken by this staff member. No withdrawals.
export default function StaffChatsTab() {
  const [status, setStatus] = useState("open");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState({ hasMore: false, total: 0 });
  const [counts, setCounts] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const selectedRef = useRef(null);
  selectedRef.current = selected;

  useEffect(() => { const t = setTimeout(() => setQuery(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const loadList = useCallback(() => staffApi.chats(status, query).then((r) => { setRows(r.items); setPage({ hasMore: r.has_more, total: r.total }); }).catch(() => {}), [status, query]);
  const loadSummary = useCallback(() => staffApi.chatSummary().then(setCounts).catch(() => {}), []);
  const loadDetail = useCallback(async (id) => {
    if (!id) return;
    try { const d = await staffApi.chatDetail(id); if (selectedRef.current === id) setDetail(d); }
    catch (e) { if (e?.response?.status === 404) { setSelected(null); setDetail(null); } }
  }, []);
  useEffect(() => { loadList(); loadSummary(); }, [loadList, loadSummary]);
  useEffect(() => { setDetail(null); setText(""); loadDetail(selected); }, [selected, loadDetail]);
  usePolling(() => Promise.all([loadList(), loadSummary(), selectedRef.current ? loadDetail(selectedRef.current) : null]), 4000);

  const refresh = () => Promise.all([loadList(), loadSummary(), loadDetail(selected)]);
  const act = async (fn, msg) => {
    if (busy) return;
    setBusy(true);
    try { await fn(); if (msg) toast.success(msg); await refresh(); } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const chat = detail?.chat;
  const conv = chat && { ...detail, chat: { ...chat, status: detail.mine ? chat.status : "open" } };
  return (
    <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)_380px] gap-4 h-[calc(100vh-150px)] min-h-[640px]" data-testid="staff-chats-tab">
      <ChatSidebar q={q} setQ={setQ} status={status} setStatus={setStatus} rows={rows} found={[]} selected={selected} onPick={setSelected} counts={counts} hasMore={page.hasMore} total={page.total} onMore={() => {}} onOpenUser={setSelected} />
      {conv ? <Conversation detail={conv} busy={busy} text={text} setText={setText} acceptLabel={detail.mine ? "Принять" : "Взять в работу"} canClose={detail.mine}
        loadImage={staffApi.chatFile} loadCommands={staffApi.commands}
        onSend={() => text.trim() && act(async () => { await staffApi.chatSend(chat.id, text.trim()); setText(""); })}
        onAccept={() => act(() => staffApi.chatAccept(chat.id), "Чат ваш")} onClose={() => act(() => staffApi.chatClose(chat.id), "Чат закрыт")} />
        : <section className="rounded-2xl bg-[#0f1015] border border-white/[0.05] flex flex-col items-center justify-center gap-3 p-8 text-center" data-testid="staff-chat-empty">
          <MessagesSquare size={28} className="text-[#6b6f84]" /><div className="text-[15px] font-bold">{selected ? "Загрузка…" : "Выберите чат"}</div>
          <p className="text-[12px] text-[#8e91a3] max-w-[320px]">Свободные чаты и чаты, которые вы ведёте. Берите в работу сколько угодно.</p>
        </section>}
      <aside className="min-h-0 overflow-y-auto space-y-4 pr-0.5" data-testid="staff-chat-actions">
        {chat && detail.user && <><PlayerCard user={detail.user} /><StaffDepositCard detail={detail} onChanged={refresh} /></>}
        {chat && !detail.user && <div className="rounded-2xl bg-[#13141a] border border-white/[0.05] p-5 text-center text-[12px] text-[#8e91a3]" data-testid="staff-chat-guest-note"><LogIn size={20} className="mx-auto mb-2" />Гость: пополнение станет доступно после входа через Discord.</div>}
        {!chat && <div className="rounded-2xl border border-dashed border-white/[0.08] h-40 flex items-center justify-center text-[12px] text-[#6b6f84]">Карточка игрока</div>}
      </aside>
    </div>
  );
}
