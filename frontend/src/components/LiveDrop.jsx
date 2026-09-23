import React, { useRef } from "react";
import "animate.css";
import { Link } from "../lib/router";
import { Logo } from "./Logo";
import { formatMoney } from "../lib/api";
import { RobuxIcon } from "./Logo";
import { rarityColor } from "../lib/rarity";
import { skinImg } from "../lib/img";
import Nick from "./Nick";
import { useLang } from "../lib/i18n";
import { useMediaQuery } from "../hooks/useMediaQuery";

const FALLBACK_AVATAR = "https://cdn.discordapp.com/embed/avatars/0.png";
const DESKTOP = "(min-width: 1024px)";

export const BestDropCard = ({ drop }) => {
  const { t } = useLang();
  const Tag = drop?.discord_id ? Link : "div";
  return (
    <Tag
      {...(drop?.discord_id ? { to: `/users/${drop.discord_id}` } : {})}
      className="drop-card best-drop-card group h-[80px]"
      style={{ "--rarity": "#f4cf19" }}
      data-testid="best-hour-drop"
      title={drop ? `${t("live.best_hour")} · ${drop.item_type} | ${drop.item_name} · ${formatMoney(drop.item_price)} RAP · ${drop.nickname}` : t("live.best_hour")}
    >
      <div className="drop-thumb">
        {drop?.item_image ? (
          <img src={skinImg(drop.item_image)} alt={drop.item_name} className="drop-img" width={76} height={50} decoding="async" draggable={false} />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-[#f4cf19]"><RobuxIcon size={26} /></div>
        )}
      </div>
      <div className="relative min-w-0 flex-1 h-full flex flex-col justify-center gap-[3px]">
        <div className="flex items-center gap-1 text-[8px] font-bold uppercase tracking-wider leading-none text-[#e5d58d] whitespace-nowrap">
          <Logo size={8} className="[&_path]:fill-[#f4cf19]" />
          {t("live.best_hour")}
        </div>
        {drop ? (
          <>
            <div className="truncate text-[12px] font-extrabold uppercase leading-none text-white [text-shadow:1px_1px_2px_rgba(0,0,0,.35)]">{drop.item_name}</div>
            <div className="truncate text-[10px] leading-none text-[#c9c2a1]">{drop.item_type}</div>
            <div className="flex items-center gap-1 whitespace-nowrap text-[10px] font-bold leading-none text-[#ffe259] tabular-nums" data-testid="best-hour-price">
              {formatMoney(drop.item_price)} <RobuxIcon size={9} />
            </div>
          </>
        ) : (
          <div className="text-[10px] leading-snug text-[#c9c2a1]">{t("live.no_hour_wins")}</div>
        )}
      </div>
    </Tag>
  );
};

const DropCard = React.memo(function DropCard({ t, d, className = "", fresh = false }) {
  const Tag = d.discord_id ? Link : "div";
  const linkProps = d.discord_id ? { to: `/users/${d.discord_id}` } : {};
  return (
    <Tag
      {...linkProps}
      className={`drop-card group ${fresh ? "animate__animated animate__fadeInLeft drop-fresh" : ""} ${className}`}
      style={{ "--rarity": rarityColor(d.item_rarity) }}
      data-testid="live-drop-item"
      title={d.discord_id ? `${t("drop.profile_of")} ${d.nickname}` : d.nickname}
    >
      <div className="drop-thumb">
        {d.item_image ? (
          <img src={skinImg(d.item_image)} alt={d.item_name} className="drop-img" width={76} height={50} loading="lazy" decoding="async" draggable={false} />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-[#ffb000]"><RobuxIcon size={26} /></div>
        )}
      </div>

      <div className="relative min-w-0 flex-1 h-full">
        <div className="drop-face drop-face-item flex flex-col justify-center">
          <div className="truncate text-[12px] font-extrabold uppercase leading-tight text-white [text-shadow:1px_1px_2px_rgba(0,0,0,.35)]">{d.item_name}</div>
          <div className="truncate text-[10px] leading-tight text-[#b3b6c4]">{d.item_type}</div>
          <div className="mt-0.5 flex items-center gap-1 text-[9px] font-bold text-[#c9ccd6]"><Logo size={9} className="[&_path]:fill-[#8e91a3]" />{(Number(d.display_chance ?? d.chance) * 100).toFixed(2)}%</div>
        </div>

        <div className="drop-face drop-face-user flex items-center gap-2" data-testid="live-drop-user">
          <img src={d.avatar || FALLBACK_AVATAR} alt="" width={32} height={32} loading="lazy" decoding="async" className="w-8 h-8 rounded-full object-cover ring-2 ring-[var(--rarity)] shrink-0" />
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
});

// Remembers which drop ids were present when data first arrived so only newly arrived drops animate in.
const useFreshDrops = (drops) => {
  const seen = useRef(null);
  if (seen.current === null && drops?.length) seen.current = new Set(drops.map((d) => d.id));
  return (d) => seen.current !== null && !seen.current.has(d.id);
};

// Horizontal strip shown under the header on phones/tablets (sidebar is hidden there)
export function LiveDropStrip({ drops, bestDrop }) {
  const { t } = useLang();
  const isFresh = useFreshDrops(drops);
  const desktop = useMediaQuery(DESKTOP);
  if (desktop) return null;
  return (
    <div className="lg:hidden border-b border-[#1e2029]/70 bg-[#0f1015]/90" data-testid="live-drop-strip">
      <div className="flex overflow-x-auto no-scrollbar">
        <div className="shrink-0 w-[220px]"><BestDropCard drop={bestDrop} /></div>
        <div className="flex divide-x divide-white/10 border-l border-white/10">
          {(drops || []).slice(0, 20).map((d) => (
            <DropCard key={d.id} t={t} d={d} fresh={isFresh(d)} className="shrink-0 w-[220px] h-[72px]" />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LiveDrop({ drops, bestDrop }) {
  const { t } = useLang();
  const isFresh = useFreshDrops(drops);
  const desktop = useMediaQuery(DESKTOP);
  if (!desktop) return null;
  return (
    <aside
      className="blox-glass hidden lg:flex flex-col w-[210px] shrink-0 border-r border-[#1e2029]/70 bg-[#0f1015]/75 h-[calc(100vh-72px)] sticky top-[72px] overflow-hidden"
      data-testid="live-drop-feed"
    >
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden no-scrollbar">
        <BestDropCard drop={bestDrop} />
        <div className="flex flex-col divide-y divide-white/10 border-y border-white/10">
          {drops.map((d) => (
            <DropCard key={d.id} t={t} d={d} fresh={isFresh(d)} className="h-[72px]" />
          ))}
        </div>
      </div>
    </aside>
  );
}
