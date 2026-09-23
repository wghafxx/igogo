import React, { useEffect, useState } from "react";
import { adminApi, formatMoney } from "../../lib/api";
import CoinGrantCard from "./CoinGrantCard";

export default function PlayerCoinsPanel({ onChanged }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(null);
  const [status, setStatus] = useState("");
  useEffect(() => {
    let active = true;
    setRows([]);
    if (q.trim().length < 2) { setStatus(""); return undefined; }
    setStatus("Поиск…");
    const timer = setTimeout(async () => {
      try {
        const result = await adminApi.search(q.trim());
        if (active) { setRows(result); setStatus(result.length ? "" : "Игроки не найдены"); }
      } catch { if (active) setStatus("Не удалось найти игроков"); }
    }, 300);
    return () => { active = false; clearTimeout(timer); };
  }, [q]);
  return <div className="grid md:grid-cols-2 gap-4">
    <div className="blox-panel p-4 space-y-3 self-start">
      <h2 className="font-black">Ручное начисление монет</h2>
      <p className="text-[12px] text-[#8e91a3]">Найдите игрока по нику, Discord ID или Roblox. Начисление доступно и без чата или сыгранных игр.</p>
      <input aria-label="Найти игрока для начисления" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ник, Discord ID, Roblox…" className="w-full rounded-xl bg-white/[0.05] px-3 py-3 outline-none text-[13px]" />
      {status && <p className="text-[12px] text-[#8e91a3]">{status}</p>}
      <div className="max-h-64 overflow-y-auto space-y-1">{rows.map((u) => <button type="button" key={u.session_id} onClick={() => setSelected(u)} className={`w-full text-left rounded-xl p-3 text-[12px] ${selected?.session_id === u.session_id ? "bg-white/[0.1]" : "bg-white/[0.04] hover:bg-white/[0.08]"}`}>
        <b>{u.nickname}</b> · Discord {u.discord_id}<div className="text-[#8e91a3]">Roblox: {u.roblox_nick || "—"} · Баланс {formatMoney(u.balance)}</div>
      </button>)}</div>
    </div>
    {selected && <CoinGrantCard key={selected.session_id} user={selected} onChanged={() => { setQ(""); setRows([]); onChanged(); }} />}
  </div>;
}
