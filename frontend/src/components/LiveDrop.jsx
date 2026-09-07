import React from "react";
import { Link } from "react-router-dom";
import { Logo } from "./Logo";
import { formatMoney } from "../lib/api";
import { RobuxIcon } from "./Logo";
import { rarityColor } from "../lib/rarity";
import Nick from "./Nick";

const FALLBACK_AVATAR = "https://cdn.discordapp.com/embed/avatars/0.png";

const DropCard = ({ d, className = "", style = {} }) => {
  const Tag = d.discord_id ? Link : "div";
  const linkProps = d.discord_id ? { to: `/users/${d.discord_id}` } : {};
  return (
    <Tag
      {...linkProps}
      className={`drop-card group ${className}`}
      style={{ ...style, "--rarity": rarityColor(d.item_rarity) }}
      data-testid="live-drop-item"
      title={d.discord_id ? `Профиль ${d.nickname}` : d.nickname}
    >
      <div className="flex items-center justify-between text-[10px] text-[#00a2ff] font-bold">
        <span className="flex items-center gap-1">
          <Logo size={10} />
          {(d.chance * 100).toFixed(2)}%
        </span>
        <span className="text-[#8e91a3] tabular-nums font-semibold flex items-center gap-0.5">
          {formatMoney(d.item_price)} <RobuxIcon size={8} />
        </span>
      </div>

      <div className="relative flex-1 min-h-0">
        <div className="drop-face drop-face-item flex items-end justify-between gap-1 h-full">
          <div className="min-w-0">
            <div className="text-[11px] font-extrabold uppercase text-white truncate">{d.item_name}</div>
            <div className="text-[9px] text-[#8e91a3] truncate">{d.item_type}</div>
          </div>
          {d.item_image ? (
            <img src={d.item_image} alt={d.item_name} className="w-11 h-11 object-contain drop-img" />
          ) : (
            <div className="w-11 h-11 flex items-center justify-center text-[#ffb000]">
              <RobuxIcon size={20} />
            </div>
          )}
        </div>

        <div className="drop-face drop-face-user flex items-center gap-2 h-full" data-testid="live-drop-user">
          <img src={d.avatar || FALLBACK_AVATAR} alt="" className="w-9 h-9 rounded-full object-cover ring-2 ring-[var(--rarity)] shrink-0" />
          <div className="min-w-0">
            <Nick gold={d.gold_nick} className="text-[11px] font-extrabold truncate block" testId="live-drop-nickname">
              {d.nickname}
            </Nick>
            <div className="text-[9px] text-[#8e91a3] truncate">{d.discord_id ? "Открыть профиль →" : "Игрок"}</div>
          </div>
        </div>
      </div>
    </Tag>
  );
};

// Horizontal strip shown under the header on phones/tablets (sidebar is hidden there)
export function LiveDropStrip({ drops }) {
  if (!drops || drops.length === 0) return null;
  return (
    <div className="lg:hidden border-b border-[#1e2029] bg-[#0f1015]" data-testid="live-drop-strip">
      <div className="px-3 pt-2 flex items-center gap-1 text-[11px] font-bold text-[#ffb000]">
        <Logo size={11} /> Лучший дроп
      </div>
      <div className="flex gap-2 overflow-x-auto px-3 py-2 no-scrollbar">
        {drops.slice(0, 20).map((d) => (
          <DropCard key={d.id} d={d} className="shrink-0 w-[190px] h-[78px] px-2.5 py-2 flex flex-col gap-1" style={{ boxShadow: `inset 0 -3px 0 ${rarityColor(d.item_rarity)}` }} />
        ))}
      </div>
    </div>
  );
}

export default function LiveDrop({ drops }) {
  return (
    <aside
      className="hidden lg:block w-[210px] shrink-0 border-r border-[#1e2029] bg-[#0f1015] h-[calc(100vh-54px)] sticky top-[54px] overflow-y-auto no-scrollbar"
      data-testid="live-drop-feed"
    >
      <div className="px-2 pt-2 pb-1 flex items-center gap-1.5 text-[11px] font-bold text-[#8e91a3] uppercase tracking-wide">
        <span className="inline-block w-2 h-2 rounded-full bg-[#2ecc71] pulse-dot" /> Live дропы
      </div>
      <div className="p-2 pt-1 space-y-2">
        {drops.map((d) => (
          <DropCard key={d.id} d={d} className="h-[82px] px-2.5 py-2 flex flex-col gap-1" style={{ boxShadow: `inset 3px 0 0 ${rarityColor(d.item_rarity)}` }} />
        ))}
      </div>
    </aside>
  );
}
