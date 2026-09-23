import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Check, XCircle, MessagesSquare, LogIn } from "lucide-react";
import { adminApi, formatMoney } from "../../lib/api";
import ChatMessages from "../chat/ChatMessages";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../ui/dialog";
import ChatSidebar from "./chat/ChatSidebar";
import { PlayerCard, DepositCard, WithdrawCard } from "./chat/PlayerPanel";
import { Avatar, StatusPill, Btn, fmtTime } from "./chat/ui";
import CommandComposer from "./chat/CommandComposer";
import CoinGrantCard from "./CoinGrantCard";
import { usePolling } from "../../hooks/usePolling";

const Conversation = ({ detail, busy, text, setText, onSend, onAccept, onClose }) => {
  const chat = detail.chat;
  return (
    <section className="flex flex-col min-h-0 min-w-0 rounded-2xl bg-[#0f1015] border border-white/[0.05]" data-testid="admin-chat-window">
      <header className="h-[68px] px-4 flex items-center gap-3 border-b border-white/[0.05] shrink-0">
        <Avatar src={chat.avatar} name={chat.nickname} size={40} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2"><span className={`inline-block w-2 h-2 rounded-full shrink-0 ${chat.online ? "bg-[#2ecc71] shadow-[0_0_6px_#2ecc71]" : "bg-[#5f6377]"}`} /><span className="text-[14px] font-black truncate" data-testid="admin-chat-nick">{chat.nickname}</span>{chat.guest && <span className="text-[10px] text-[#8e91a3] bg-white/[0.06] rounded px-1">гость</span>}<StatusPill status={chat.status} testId="admin-chat-status" /></div>
          <div className="text-[11px] text-[#6b6f84]">{chat.online ? <span className="text-[#7ee2a8] font-bold">онлайн</span> : "не в сети"} · активность {fmtTime(chat.updated_at)}{chat.waiting_seconds != null && <span className="text-[#ffcf5a] font-bold"> · ждёт ответа {Math.max(1, Math.floor(chat.waiting_seconds / 60))} мин</span>}</div>
        </div>
        {chat.status === "open" && <Btn tone="success" onClick={onAccept} disabled={busy} data-testid="admin-chat-accept-button"><Check size={15} /> Принять</Btn>}
        {chat.status !== "closed" && <Btn tone="danger" onClick={onClose} disabled={busy} data-testid="admin-chat-close-button"><XCircle size={15} /> Закрыть</Btn>}
      </header>
      <ChatMessages messages={detail.messages} mine="admin" testId="admin-chat-messages" className="px-4 py-4" chatId={detail.chat?.id} loadImage={adminApi.chatAttachment} />
      <CommandComposer text={text} setText={setText} busy={busy} onSend={onSend} placeholder={chat.status === "open" ? "Ответить или выбрать команду по /…" : "Написать игроку или выбрать команду по /…"} />
    </section>
  );
};

const Empty = ({ hasSelection }) => (
  <section className="rounded-2xl bg-[#0f1015] border border-white/[0.05] flex flex-col items-center justify-center gap-3 text-center p-8" data-testid="admin-chat-window">
    <span className="w-16 h-16 rounded-2xl bg-white/[0.04] text-[#6b6f84] flex items-center justify-center"><MessagesSquare size={28} /></span>
    <div className="text-[15px] font-bold">{hasSelection ? "Загрузка…" : "Выберите чат"}</div>
    <p className="text-[12px] text-[#8e91a3] max-w-[320px] leading-relaxed">Слева — обращения игроков. Пополнение и вывод скинов делаются в карточке игрока справа от диалога.</p>
  </section>
);

export default function ChatsTab({ refreshKey, onSummary }) {
  const [status, setStatus] = useState("open");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState({ hasMore: false, total: 0, pages: 1 });
  const [found, setFound] = useState([]);
  const [counts, setCounts] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [cancelW, setCancelW] = useState(null);
  const [cancelReason, setCancelReason] = useState("");
  const selectedRef = useRef(null);
  selectedRef.current = selected;
  const listSeq = useRef(0);
  const searchSeq = useRef(0);
  const pagesRef = useRef(1);

  // Typing only updates the box; the list query follows 300 ms after the last keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(q.trim()), 300);
    return () => clearTimeout(timer);
  }, [q]);
  useEffect(() => { pagesRef.current = 1; }, [status, query]);

  const loadList = useCallback(async () => {
    const seq = ++listSeq.current;
    try {
      const chunks = [];
      for (let i = 0; i < pagesRef.current; i += 1) {
        const res = await adminApi.chats(status, query, chunks.reduce((n, c) => n + c.items.length, 0));
        chunks.push(res);
        if (!res.has_more) break;
      }
      if (seq !== listSeq.current) return;
      const last = chunks[chunks.length - 1];
      setRows(chunks.flatMap((c) => c.items));
      setPage({ hasMore: Boolean(last?.has_more), total: last?.total || 0 });
    } catch {
      if (seq === listSeq.current) toast.error("Не удалось загрузить чаты");
    }
  }, [status, query]);
  const loadSummary = useCallback(() => adminApi.chatSummary().then((s) => { setCounts(s); onSummary?.(s); }).catch(() => {}), [onSummary]);
  const loadDetail = useCallback(async (id) => {
    if (!id) return;
    try {
      const data = await adminApi.chatMessages(id);
      if (selectedRef.current === id) setDetail(data);
    } catch (e) {
      if (e?.response?.status === 404) { setSelected(null); setDetail(null); }
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList, refreshKey]);
  useEffect(() => { loadSummary(); }, [loadSummary, refreshKey]);
  useEffect(() => {
    const seq = ++searchSeq.current;
    if (query.length < 2) { setFound([]); return; }
    adminApi.search(query).then((r) => { if (seq === searchSeq.current) setFound(r); }).catch(() => { if (seq === searchSeq.current) setFound([]); });
  }, [query]);
  useEffect(() => { setDetail(null); setText(""); loadDetail(selected); }, [selected, loadDetail]);
  usePolling(async () => { await Promise.all([loadList(), loadSummary(), selectedRef.current ? loadDetail(selectedRef.current) : null]); }, 4000);

  const loadMore = () => { pagesRef.current += 1; loadList(); };
  const refresh = () => { loadDetail(selected); loadList(); loadSummary(); };
  const act = async (fn, msg) => {
    if (busy) return false;
    setBusy(true);
    try { await fn(); if (msg) toast.success(msg); await Promise.all([loadList(), loadSummary(), loadDetail(selected)]); return true; } catch (e) { toast.error(e?.response?.data?.detail || "Ошибка"); return false; } finally { setBusy(false); }
  };
  const send = () => text.trim() && act(async () => { await adminApi.chatSend(selected, text.trim()); setText(""); });
  const chat = detail?.chat;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)_380px] gap-4 h-[calc(100vh-190px)] min-h-[640px]" data-testid="admin-chats-tab">
      <ChatSidebar q={q} setQ={setQ} status={status} setStatus={setStatus} rows={rows} found={found} selected={selected} onPick={setSelected} counts={counts} hasMore={page.hasMore} total={page.total} onMore={loadMore} onOpenUser={(id) => { setStatus("all"); setSelected(id); }} />
      {chat ? <Conversation detail={detail} busy={busy} text={text} setText={setText} onSend={send} onAccept={() => act(() => adminApi.chatAccept(chat.id), "Чат принят")} onClose={() => act(() => adminApi.chatClose(chat.id), "Чат закрыт")} /> : <Empty hasSelection={Boolean(selected)} />}
      <aside className="min-h-0 overflow-y-auto space-y-4 pr-0.5" data-testid="admin-chat-actions">
        {chat && detail.user && (
          <>
            <PlayerCard user={detail.user} />
            <DepositCard key={chat.id} chatId={chat.id} user={detail.user} deposits={detail.deposits} onChanged={refresh} />
            <CoinGrantCard key={detail.user.session_id} user={detail.user} onChanged={refresh} />
            <WithdrawCard chatId={chat.id} withdrawals={detail.withdrawals} total={detail.withdrawals_total} onChanged={refresh} onCancel={(w) => { setCancelReason(w.cancellation_reason || ""); setCancelW(w); }} />
          </>
        )}
        {chat && !detail.user && (
          <div className="rounded-2xl bg-[#13141a] border border-white/[0.05] p-5 text-center space-y-2" data-testid="admin-chat-guest-note">
            <span className="mx-auto w-12 h-12 rounded-xl bg-white/[0.04] text-[#6b6f84] flex items-center justify-center"><LogIn size={22} /></span>
            <div className="text-[13px] font-bold">Гость</div>
            <p className="text-[12px] text-[#8e91a3] leading-relaxed">Пополнение и вывод станут доступны, когда игрок войдёт через Discord.</p>
          </div>
        )}
        {!chat && <div className="rounded-2xl border border-dashed border-white/[0.08] h-40 flex items-center justify-center text-[12px] text-[#6b6f84]">Карточка игрока</div>}
      </aside>

      <Dialog open={Boolean(cancelW)} onOpenChange={(open) => { if (!open && !busy) setCancelW(null); }}>
        <DialogContent className="bg-[#16171d] border border-white/[0.06] text-white max-w-[calc(100%-2rem)] sm:max-w-[440px] rounded-2xl" data-testid="admin-cancel-withdrawal-dialog">
          <DialogHeader>
            <DialogTitle>Отменить вывод</DialogTitle>
            <DialogDescription className="text-[#8e91a3]">{cancelW?.item?.name} · {formatMoney(cancelW?.item?.price)} RAP. Скин вернётся в инвентарь, игрок увидит причину в чате и профиле.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap gap-2">
            {["Долгое ожидание", "Roblox-профиль не принимает трейды", "Не удалось связаться с игроком"].map((r) => <button key={r} type="button" onClick={() => setCancelReason(r)} disabled={busy || cancelW?.status === "cancelling"} className={`h-8 px-3 rounded-lg text-[12px] font-bold transition-colors ${cancelReason === r ? "bg-white text-black" : "bg-white/[0.06] text-[#a4a7b8] hover:text-white"}`} data-testid="admin-withdrawal-long-wait">{r}</button>)}
          </div>
          <textarea value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} disabled={busy || cancelW?.status === "cancelling"} maxLength={1000} rows={3} placeholder="Причина для игрока…" className="w-full bg-white/[0.05] rounded-xl p-3 text-[13px] outline-none focus:ring-1 focus:ring-[#ff5c5c] resize-y" data-testid="admin-withdrawal-cancel-reason" />
          <div className="flex gap-2">
            <Btn onClick={() => setCancelW(null)} disabled={busy}>Назад</Btn>
            <Btn tone="danger" className="flex-1 !bg-[#ff5c5c] !text-white hover:!bg-[#ff7373]" disabled={busy || !cancelReason.trim()} onClick={async () => { if (await act(() => adminApi.withdrawalCancel(cancelW.id, cancelReason.trim()), "Вывод отменён, скин возвращён")) setCancelW(null); }} data-testid="admin-withdrawal-cancel-confirm">{busy ? "Отмена…" : "Отменить и вернуть скин"}</Btn>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
