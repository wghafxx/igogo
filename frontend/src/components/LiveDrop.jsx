import React from "react";
import { Link } from "react-router-dom";
import { Logo } from "./Logo";
import { formatMoney } from "../lib/api";
import { RobuxIcon } from "./Logo";
import { rarityColor } from "../lib/rarity";
import Nick from "./Nick";
import { useLang } from "../lib/i18n";

const FALLBACK_AVATAR = "https://cdn.discordapp.com/embed/avatars/0.png";

export const BestDropCard = ({ drop }) => {
  const { t } = useLang();
  const Tag = drop?.discord_id ? Link : "div";
  return (
    <Tag
      {...(drop?.discord_id ? { to: `/users/${drop.discord_id}` } : {})}
      className="group relative block h-[88px] overflow-hidden rounded-lg border border-[#ffd43b]/20 bg-[linear-gradient(160deg,#252622_15%,#37331b_58%,#72600c_100%)] shadow-[inset_3px_0_0_#e9c51b] transition-colors hover:border-[#ffd43b]/60"
      data-testid="best-hour-drop"
      title={drop ? `${t("live.best_hour")} · ${drop.item_type} | ${drop.item_name} · ${formatMoney(drop.item_price)} RAP · ${drop.nickname}` : t("live.best_hour")}
    >
      <svg viewBox="0 0 100 100" className="pointer-events-none absolute -right-1 -bottom-1 h-[88px] w-[88px] text-[#f4cf19]" aria-hidden="true">
        <path d="M50 6 92 34 92 58 50 30 8 58 8 34Z" fill="currentColor" opacity=".18" />
        <path d="M50 37 92 65 92 89 50 61 8 89 8 65Z" fill="currentColor" opacity=".5" />
        <path d="M50 68 92 96 92 120 50 92 8 120 8 96Z" fill="currentColor" opacity=".14" />
      </svg>
      <div className="absolute inset-x-2 top-2 z-10 flex items-center justify-between gap-1">
        {drop && <span className="flex items-center gap-0.5 rounded bg-black/25 px-1 py-0.5 text-[8px] font-bold leading-none text-[#f4e5a0]">
          <Logo size={9} className="[&_path]:fill-[#f4cf19]" />
          {(Number(drop.display_chance ?? drop.chance) * 100).toFixed(2)}%
        </span>}
        <span className="text-[8px] font-bold uppercase tracking-wide text-[#e5d58d]">{t("live.best_hour")}</span>
      </div>
      {drop ? (
        <>
          <div className="absolute right-1 top-4 flex h-[70px] w-[84px] items-center justify-center">
            {drop.item_image ? <img src={drop.item_image} alt={drop.item_name} className="h-full w-full object-contain drop-shadow-[0_4px_6px_#0008] transition-transform duration-300 group-hover:scale-110" /> : <RobuxIcon size={30} />}
          </div>
          <div className="absolute bottom-2 left-2.5 right-[78px] z-10 min-w-0">
            <div className="mb-1 flex items-center gap-1 text-[12px] font-black tabular-nums leading-none text-[#ffe259]" data-testid="best-hour-price">{formatMoney(drop.item_price)} <RobuxIcon size={10} /></div>
            <div className="truncate text-[11px] font-black uppercase leading-tight text-white">{drop.item_name}</div>
            <div className="mt-0.5 truncate text-[9px] leading-tight text-[#c9c2a1]">{drop.item_type}</div>
          </div>
        </>
      ) : <div className="absolute inset-x-3 bottom-3 pr-9 text-[11px] leading-relaxed text-[#c9c2a1]">{t("live.no_hour_wins")}</div>}
    </Tag>
  );
};

const DropCard = ({ t, d, className = "", style = {} }) => {
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
          {(Number(d.display_chance ?? d.chance) * 100).toFixed(2)}%
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
            <div className="text-[9px] text-[#8e91a3] truncate">{d.discord_id ? t("live.open_profile") : t("live.player")}</div>
          </div>
        </div>
      </div>
    </Tag>
  );
};

// Horizontal strip shown under the header on phones/tablets (sidebar is hidden there)
export function LiveDropStrip({ drops, bestDrop }) {
  const { t } = useLang();
  return (
    <div className="lg:hidden border-b border-[#1e2029] bg-[#0f1015]" data-testid="live-drop-strip">
      <div className="px-3 pt-2"><BestDropCard drop={bestDrop} /></div>
      <div className="px-3 pt-2 flex items-center gap-1 text-[11px] font-bold text-[#ffb000]">
        <Logo size={11} /> {t("live.title")}
      </div>
      <div className="flex gap-2 overflow-x-auto px-3 py-2 no-scrollbar">
        {(drops || []).slice(0, 20).map((d) => (
          <DropCard key={d.id} t={t} d={d} className="shrink-0 w-[190px] h-[78px] px-2.5 py-2 flex flex-col gap-1" style={{ boxShadow: `inset 0 -3px 0 ${rarityColor(d.item_rarity)}` }} />
        ))}
      </div>
    </div>
  );
}

export default function LiveDrop({ drops, bestDrop }) {
  const { t } = useLang();
  return (
    <aside
      className="hidden lg:flex flex-col w-[210px] shrink-0 border-r border-[#1e2029] bg-[#0f1015] h-[calc(100vh-54px)] sticky top-[54px] overflow-hidden"
      data-testid="live-drop-feed"
    >
      <div className="p-2 pb-1 shrink-0"><BestDropCard drop={bestDrop} /></div>
      <div className="px-2 pt-2 pb-1 flex items-center gap-1.5 text-[11px] font-bold text-[#8e91a3] uppercase tracking-wide">
        <span className="inline-block w-2 h-2 rounded-full bg-[#2ecc71] pulse-dot" /> {t("live.title")}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto no-scrollbar p-2 pt-1 space-y-2">
        {drops.map((d) => (
          <DropCard key={d.id} t={t} d={d} className="h-[82px] px-2.5 py-2 flex flex-col gap-1" style={{ boxShadow: `inset 3px 0 0 ${rarityColor(d.item_rarity)}` }} />
        ))}
      </div>
    </aside>
  );
}
