import React, { useCallback, useEffect, useState } from "react";
import { Logo } from "../components/Logo";
import DiscordButton from "../components/DiscordButton";
import { useAuth } from "../hooks/useAuth";
import { staffApi } from "../lib/staff-api";
import ShiftBar from "../components/staff/ShiftBar";
import StatsGrid from "../components/staff/StatsGrid";
import TransfersPanel from "../components/staff/TransfersPanel";
import RequestWorkspace from "../components/staff/RequestWorkspace";
import { QueueList, MineList } from "../components/staff/RequestLists";

const TABS = [["queue", "Очередь"], ["mine", "Мои заявки"], ["transfers", "Передачи"], ["stats", "Статистика"]];

const Gate = ({ children }) => (
  <div className="min-h-screen bg-[#0d0e12] text-white flex items-center justify-center px-4" data-testid="staff-gate">
    <div className="blox-panel w-full max-w-[440px] p-7 space-y-4 text-center">{children}</div>
  </div>
);

export default function StaffPage() {
  const { authUser, loading, login } = useAuth();
  const [me, setMe] = useState(null);
  const [denied, setDenied] = useState(false);
  const [tab, setTab] = useState("queue");
  const [queue, setQueue] = useState([]);
  const [mine, setMine] = useState({ active: [], done: [] });
  const [open, setOpen] = useState(null);

  const loadMe = useCallback(() => staffApi.me().then((d) => { setMe(d); setDenied(false); }).catch((e) => {
    if ([401, 403].includes(e?.response?.status)) setDenied(true);
  }), []);
  const loadLists = useCallback(() => Promise.all([
    staffApi.queue().then(setQueue).catch(() => {}),
    staffApi.requests().then(setMine).catch(() => {}),
  ]), []);

  useEffect(() => {
    if (!authUser) return undefined;
    loadMe(); loadLists();
    const t = setInterval(() => { loadMe(); loadLists(); }, 8000);
    return () => clearInterval(t);
  }, [authUser, loadMe, loadLists]);

  const shiftOpen = Boolean(me?.shift);
  useEffect(() => {
    if (!shiftOpen) return undefined;
    const beat = () => staffApi.shiftAction("heartbeat").catch(() => {});
    beat();
    const t = setInterval(beat, 30000);
    return () => clearInterval(t);
  }, [shiftOpen]);

  if (loading) return <Gate><div className="text-[13px] text-[#8e91a3]">Загрузка…</div></Gate>;
  if (!authUser) return <Gate><div className="text-[18px] font-black">Кабинет сотрудника</div><div className="text-[12px] text-[#8e91a3]">Войдите через Discord-аккаунт, добавленный владельцем.</div><DiscordButton onClick={login} className="w-full" data-testid="staff-login-button">Войти через Discord</DiscordButton></Gate>;
  if (denied) return <Gate><div className="text-[18px] font-black" data-testid="staff-denied">Нет доступа</div><div className="text-[12px] text-[#8e91a3]">Этот аккаунт не является активным сотрудником.</div></Gate>;
  if (!me) return <Gate><div className="text-[13px] text-[#8e91a3]">Загрузка…</div></Gate>;

  const openRequest = (id) => { setOpen(id); setTab("mine"); loadLists(); };
  return (
    <div className="min-h-screen bg-[#0d0e12] text-white" data-testid="staff-page">
      <header className="min-h-[54px] flex flex-wrap items-center gap-3 justify-between px-4 py-2 border-b border-[#15161b] bg-[#0f1015] sticky top-0 z-40">
        <div className="flex items-center gap-2">
          <Logo size={30} />
          <span className="hidden sm:inline font-black uppercase tracking-wide text-[20px]">BLOXGRADE</span>
          <span className="text-[10px] uppercase tracking-widest text-[#00a2ff] bg-[#00a2ff]/15 rounded px-2 py-0.5 ml-2">staff</span>
          <span className="text-[12px] text-[#8e91a3] ml-2 hidden md:inline" data-testid="staff-receiver">приём на @{me.staff.roblox_nick}</span>
        </div>
        <ShiftBar shift={me.shift} onChange={(shift) => setMe((m) => ({ ...m, shift }))} />
      </header>
      <main className="max-w-[1500px] mx-auto px-4 py-6 space-y-4">
        <div className="flex flex-wrap items-center gap-1 rounded-lg bg-[#0f1015] p-1 w-fit">
          {TABS.map(([k, label]) => (
            <button key={k} onClick={() => { setTab(k); setOpen(null); }} className={`h-8 px-3 rounded-md text-[12px] font-bold transition-colors ${tab === k ? "bg-[#ffb000] text-black" : "text-[#8e91a3] hover:text-white"}`} data-testid={`staff-tab-${k}`}>
              {label}{k === "queue" && queue.length > 0 && ` · ${queue.length}`}{k === "mine" && mine.active.length > 0 && ` · ${mine.active.length}`}
            </button>
          ))}
        </div>
        {open ? <RequestWorkspace depId={open} onBack={() => { setOpen(null); loadLists(); }} /> : <>
          {tab === "queue" && <QueueList rows={queue} onClaimed={(id) => (id ? openRequest(id) : loadLists())} />}
          {tab === "mine" && <MineList data={mine} onOpen={setOpen} />}
          {tab === "transfers" && <TransfersPanel holdings={me.today.holdings} onChanged={loadMe} />}
          {tab === "stats" && <StatsGrid stats={me.today} testId="staff-today-stats" />}
        </>}
      </main>
    </div>
  );
}
