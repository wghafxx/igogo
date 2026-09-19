import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Logo } from "../components/Logo";
import { LockIcon } from "../components/icons/lock";
import { RefreshCWIcon } from "../components/icons/refresh-cw";
import { adminApi, getAdminToken, setAdminToken, parseServerDate } from "../lib/api";
import BankTab from "../components/admin/BankTab";
import PlayersTab from "../components/admin/PlayersTab";
import RainTab from "../components/admin/RainTab";
import PromosTab from "../components/admin/PromosTab";
import ChatsTab from "../components/admin/ChatsTab";
import QuickCommandsTab from "../components/admin/QuickCommandsTab";
import { DepositReceipt } from "../components/DepositReceipt";
import { DepositStatus } from "../components/DepositStatus";

const fmtDate = (d) => parseServerDate(d).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

const PAYMENT_TABS = ["xrocket", "cryptobot"];
const WORDS = 10;
const splitWords = (text) => text.trim().split(/[\s,;]+/).filter(Boolean);

const AdminLogin = ({ onDone }) => {
  const [words, setWords] = useState(Array(WORDS).fill(""));
  const [busy, setBusy] = useState(false);
  const refs = useRef([]);
  const filled = words.every((w) => w.trim().length > 0);

  const setWord = (i, v) => setWords((ws) => ws.map((w, j) => (j === i ? v.replace(/\s/g, "") : w)));
  const onPaste = (i, e) => {
    const parts = splitWords(e.clipboardData.getData("text"));
    if (parts.length < 2) return;
    e.preventDefault();
    setWords((ws) => ws.map((w, j) => (j >= i && parts[j - i] !== undefined ? parts[j - i] : w)));
    refs.current[Math.min(WORDS - 1, i + parts.length - 1)]?.focus();
  };
  const onKey = (i, e) => {
    if (e.key === "Enter") return filled ? submit() : refs.current[i + 1]?.focus();
    if (e.key === " " && words[i]) {
      e.preventDefault();
      refs.current[i + 1]?.focus();
    }
    if (e.key === "Backspace" && !words[i] && i > 0) refs.current[i - 1]?.focus();
  };

  const submit = async () => {
    if (!filled || busy) return;
    setBusy(true);
    try {
      const { token } = await adminApi.login(words.map((w) => w.trim()));
      setAdminToken(token);
      onDone();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Неверная сид-фраза");
      setWords(Array(WORDS).fill(""));
      refs.current[0]?.focus();
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="min-h-screen bg-[#0d0e12] text-white flex items-center justify-center px-4" data-testid="admin-login-page">
      <div className="blox-panel w-full max-w-[520px] p-7 space-y-5">
        <div className="flex items-center gap-2">
          <Logo size={30} />
          <span className="font-black uppercase tracking-wide text-[18px]">BLOXGRADE</span>
          <span className="ml-auto text-[10px] uppercase tracking-widest text-[#5f6377]">admin</span>
        </div>
        <div>
          <div className="text-[20px] font-black">Админ-панель</div>
          <div className="text-[12px] text-[#8e91a3] mt-1">Введите все {WORDS} слов сид-фразы по порядку. Можно вставить всю фразу целиком в любое поле.</div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2" data-testid="admin-seed-grid">
          {words.map((w, i) => (
            <div key={i} className="flex items-center gap-1.5 h-11 px-2.5 rounded-lg bg-[#0f1015] focus-within:ring-1 focus-within:ring-[#00a2ff]">
              <span className="text-[10px] text-[#5f6377] w-4 text-right">{i + 1}</span>
              <input
                ref={(el) => (refs.current[i] = el)}
                type="password"
                value={w}
                onChange={(e) => setWord(i, e.target.value)}
                onPaste={(e) => onPaste(i, e)}
                onKeyDown={(e) => onKey(i, e)}
                autoComplete="off"
                spellCheck={false}
                autoFocus={i === 0}
                className="flex-1 min-w-0 bg-transparent outline-none text-[13px] font-mono"
                data-testid={`admin-seed-word-${i + 1}`}
              />
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={submit} disabled={busy || !filled} className="blox-btn-primary h-11 flex-1 text-[14px] disabled:opacity-40" data-testid="admin-login-button">
            <LockIcon size={15} className="inline mr-1.5 -mt-0.5" /> Войти
          </button>
          <button onClick={() => { setWords(Array(WORDS).fill("")); refs.current[0]?.focus(); }} className="blox-chip h-11 px-4 text-[12px] font-bold text-[#9a9db0] hover:text-white" data-testid="admin-seed-clear">
            Очистить
          </button>
        </div>
        <div className="text-[11px] text-[#5f6377]">Введено {words.filter((x) => x.trim()).length} из {WORDS}. После 5 неверных попыток вход блокируется на 15 минут.</div>
      </div>
    </div>
  );
};

export default function AdminPage() {
  const [authed, setAuthed] = useState(Boolean(getAdminToken()));
  const [tab, setTab] = useState("chats");
  const [rows, setRows] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [chatSummary, setChatSummary] = useState(null);
  const currentTab = useRef("");
  currentTab.current = tab;

  const load = useCallback(async () => {
    try {
      if (!PAYMENT_TABS.includes(tab)) return;
      const result = await adminApi.deposits(tab);
      if (currentTab.current === tab) setRows(result);
    } catch (e) {
      if (e?.response?.status === 403) {
        setAdminToken(null);
        setAuthed(false);
      } else toast.error("Не удалось загрузить платежи");
    }
  }, [tab]);

  useEffect(() => {
    if (!authed) return;
    setRows([]);
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [authed, load]);

  useEffect(() => {
    if (!authed) return;
    const poll = () => adminApi.chatSummary().then(setChatSummary).catch(() => {});
    poll();
    const timer = setInterval(poll, 10000);
    return () => clearInterval(timer);
  }, [authed, tab]);

  useEffect(() => {
    if (!authed) return;
    const check = () => adminApi.session().catch((e) => {
      if (e?.response?.status === 403) { setAdminToken(null); setAuthed(false); }
    });
    check();
    const timer = setInterval(check, 30000);
    return () => clearInterval(timer);
  }, [authed]);

  if (!authed) return <AdminLogin onDone={() => setAuthed(true)} />;

  return (
    <div className="min-h-screen bg-[#0d0e12] text-white" data-testid="admin-page">
      <header className="h-[54px] flex items-center justify-between px-4 border-b border-[#15161b] bg-[#0f1015] sticky top-0 z-40">
        <div className="flex items-center gap-2">
          <Logo size={30} />
          <span className="hidden sm:inline font-black uppercase tracking-wide text-[20px]">BLOXGRADE</span>
          <span className="text-[10px] uppercase tracking-widest text-[#ffb000] bg-[#ffb000]/15 rounded px-2 py-0.5 ml-2">admin</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { load(); setRefreshKey((v) => v + 1); }} className="blox-chip w-9 h-9 flex items-center justify-center text-[#9a9db0] hover:text-white" title="Обновить" data-testid="admin-refresh-button">
            <RefreshCWIcon size={15} />
          </button>
          <button onClick={async () => { try { await adminApi.logout(); } catch (_) {} setAdminToken(null); setAuthed(false); }} className="blox-chip h-9 px-3 text-[12px] font-bold text-[#9a9db0] hover:text-white" data-testid="admin-logout-button">
            Выйти
          </button>
        </div>
      </header>

      <main className={`${tab === "chats" ? "max-w-[1600px]" : "max-w-[1100px]"} mx-auto px-4 py-6 space-y-4`}>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-1 rounded-lg bg-[#0f1015] p-1">
            {[
              ["chats", "Чаты · пополнение и вывод"],
              ["commands", "Быстрые команды"],
              ["xrocket", "Платежи xRocket"],
              ["cryptobot", "Платежи CryptoBot"],
              ["bank", "Банк"],
              ["players", "Игроки"],
              ["promos", "Промокоды"],
              ["rain", "Удача"],
            ].map(([k, label]) => (
              <button key={k} onClick={() => setTab(k)} className={`h-8 px-3 rounded-md text-[12px] font-bold transition-colors inline-flex items-center gap-1.5 ${tab === k ? "bg-[#ffb000] text-black" : "text-[#8e91a3] hover:text-white"}`} data-testid={`admin-tab-${k}`}>
                {label}
                {k === "chats" && chatSummary && (chatSummary.open + chatSummary.unread) > 0 && <span className={`h-4 min-w-4 px-1 rounded-full text-[10px] font-black flex items-center justify-center ${tab === k ? "bg-black text-[#ffb000]" : "bg-[#00a2ff] text-white"}`} data-testid="admin-chats-badge">{chatSummary.open + chatSummary.unread}</span>}
              </button>
            ))}
          </div>
          {tab === "chats" && <div className="text-[12px] text-[#8e91a3]">Пополнение скинами и вывод делаются прямо в чате игрока. Поиск — по нику, Discord ID, Roblox-нику или ссылке.</div>}
        </div>

        {tab === "chats" && <ChatsTab refreshKey={refreshKey} />}
        {tab === "commands" && <QuickCommandsTab refreshKey={refreshKey} />}
        {tab === "bank" && <BankTab refreshKey={refreshKey} />}
        {tab === "players" && <PlayersTab refreshKey={refreshKey} />}
        {tab === "rain" && <RainTab refreshKey={refreshKey} />}
        {tab === "promos" && <PromosTab refreshKey={refreshKey} />}

        {PAYMENT_TABS.includes(tab) && (
        <div className="space-y-3" data-testid="admin-list">
          {rows.length === 0 && <div className="blox-panel h-[160px] flex items-center justify-center text-[13px] text-[#5f6377]" data-testid="admin-empty">Пусто</div>}
          {rows.map((d) => (
            <div key={d.id} className="blox-panel px-4 py-3 flex flex-wrap items-center gap-3 text-[12px]" data-testid="admin-history-row">
              <span className="font-bold w-40 truncate">{d.nickname}</span>
              <span className="text-[#8e91a3] w-36">Discord {d.discord_id}</span>
              <span className="flex-1 min-w-[200px] text-[#b4b7c7] truncate">{d.description}</span>
              <DepositStatus status={d.status} />
              <DepositReceipt deposit={d} compact testId={`admin-deposit-receipt-${d.id}`} />
              <span className="text-[#5f6377] w-24 text-right">{fmtDate(d.resolved_at || d.created_at)}</span>
            </div>
          ))}
        </div>
        )}
      </main>
    </div>
  );
}
