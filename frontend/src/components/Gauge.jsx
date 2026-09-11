import React from "react";
import { useLang } from "../lib/i18n";

const CX = 150;
const CY = 150;
const R = 116; // ring center radius
const STROKE = 26;

const polar = (deg, r = R) => {
  const rad = ((deg - 90) * Math.PI) / 180;
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
};

const arcPath = (from, to, r = R) => {
  if (to - from >= 359.9) to = from + 359.9;
  const s = polar(from, r);
  const e = polar(to, r);
  const large = to - from > 180 ? 1 : 0;
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`;
};

const edge = (deg) => {
  const a = polar(deg, R - STROKE / 2);
  const b = polar(deg, R + STROKE / 2);
  return { x1: a.x, y1: a.y, x2: b.x, y2: b.y };
};

// Static wheel: the win-strip sits at the bottom; the pointer starts at the bottom and spins.
export default function Gauge({ chance, rotation, spinning, fast, result, cashback, onSpinEnd }) {
  const { t } = useLang();
  const half = Math.min(chance * 180, 179.9);
  const zoneFrom = 180 - half;
  const zoneTo = 180 + half;

  const ticks = [];
  for (let a = 0; a < 360; a += 5) {
    const major = a % 30 === 0;
    const p1 = polar(a, R - STROKE / 2 - 4);
    const p2 = polar(a, R - STROKE / 2 - (major ? 14 : 8));
    ticks.push(
      <line key={a} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke={major ? "#3b3e4d" : "#272934"} strokeWidth={major ? 2 : 1.2} strokeLinecap="round" />
    );
  }

  const ringClass = `gauge-ring ${fast ? "fast" : ""}`;
  const centerColor = result === "win" ? "#2ecc71" : result === "lose" ? "#ff5c5c" : "#ffffff";
  const chanceLabel = chance <= 0.15 ? t("gauge.low") : chance <= 0.5 ? t("gauge.mid") : t("gauge.high");
  const pTop = CY - R - STROKE / 2; // outer edge of ring at top

  return (
    <div className="relative w-[min(300px,82vw)] h-[min(300px,82vw)] mx-auto select-none" data-testid="upgrade-gauge">
      <svg viewBox="0 0 300 300" className="w-full h-full overflow-visible">
        <defs>
          <linearGradient id="zone-grad" gradientUnits="userSpaceOnUse" x1={CX - R} y1={CY} x2={CX + R} y2={CY}>
            <stop offset="0" stopColor="#ff7a00" />
            <stop offset="0.5" stopColor="#ffb800" />
            <stop offset="1" stopColor="#00a2ff" />
          </linearGradient>
          <radialGradient id="disc-grad" cx="0.5" cy="0.45" r="0.6">
            <stop offset="0" stopColor="#1d1e27" />
            <stop offset="1" stopColor="#101116" />
          </radialGradient>
          <linearGradient id="rim-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#2b2d39" />
            <stop offset="1" stopColor="#171820" />
          </linearGradient>
          <linearGradient id="pointer-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#ffffff" />
            <stop offset="1" stopColor="#c9cddb" />
          </linearGradient>
          <filter id="zone-glow" filterUnits="userSpaceOnUse" x="-50" y="-50" width="400" height="400">
            <feGaussianBlur stdDeviation="7" />
          </filter>
          <filter id="soft-shadow" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="2" stdDeviation="2.5" floodColor="#000" floodOpacity="0.6" />
          </filter>
        </defs>

        {/* outer rim */}
        <circle cx={CX} cy={CY} r={R + STROKE / 2 + 5} fill="none" stroke="url(#rim-grad)" strokeWidth="6" />
        <circle cx={CX} cy={CY} r={R + STROKE / 2 + 1.5} fill="none" stroke="#0a0b0e" strokeWidth="2" />

        {/* static ring */}
        <g>
          <circle cx={CX} cy={CY} r={R} fill="none" stroke="#1b1c24" strokeWidth={STROKE} />
          {half > 0.3 && (
            <>
              {half > 5 && <path d={arcPath(zoneFrom + 4, zoneTo - 4)} stroke="url(#zone-grad)" strokeWidth={STROKE + 10} fill="none" opacity="0.45" strokeLinecap="butt" filter="url(#zone-glow)" />}
              <path d={arcPath(zoneFrom, zoneTo)} stroke="url(#zone-grad)" strokeWidth={STROKE} fill="none" strokeLinecap="butt" />
            </>
          )}
          {half > 0.3 && half < 179 && (
            <>
              <line {...edge(zoneFrom)} stroke="#ffffff" strokeWidth="2" opacity="0.9" />
              <line {...edge(zoneTo)} stroke="#ffffff" strokeWidth="2" opacity="0.9" />
            </>
          )}
          {ticks}
        </g>

        {/* inner rim + center disc */}
        <circle cx={CX} cy={CY} r={R - STROKE / 2 - 1} fill="none" stroke="#0a0b0e" strokeWidth="2" />
        <circle cx={CX} cy={CY} r={R - STROKE / 2 - 18} fill="url(#disc-grad)" stroke="#23242e" strokeWidth="1.5" />

        {/* rotating pointer: a thin needle so the exact landing point is unambiguous */}
        <g className={ringClass} style={{ transform: `rotate(${rotation}deg)` }} data-testid="gauge-pointer"
          onTransitionEnd={(event) => {
            if (event.target === event.currentTarget && event.propertyName === "transform") onSpinEnd?.();
          }}>
          <g filter="url(#soft-shadow)">
            <line x1={CX} y1={pTop - 2} x2={CX} y2={pTop + STROKE + 2} stroke="#ffffff" strokeWidth="2" strokeLinecap="round" />
            <path d={`M ${CX} ${pTop + 4} L ${CX - 5} ${pTop - 7} Q ${CX} ${pTop - 12} ${CX + 5} ${pTop - 7} Z`} fill="url(#pointer-grad)" />
            <circle cx={CX} cy={pTop - 5.5} r="2" fill="#00a2ff" />
          </g>
        </g>
      </svg>

      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <div
          className="text-[32px] sm:text-[38px] font-black leading-none tabular-nums transition-colors duration-300"
          style={{ color: centerColor }}
          data-testid="gauge-chance"
        >
          {(chance * 100).toFixed(2)}%
        </div>
        <div className="text-[12px] text-[#7d8194] mt-1.5" data-testid="gauge-label">
          {spinning ? t("gauge.spinning") : result === "win" ? t("gauge.win") : result === "lose" ? (Number(cashback) > 0 ? `${t("gauge.cashback")} +${Number(cashback)}` : t("gauge.lose")) : chanceLabel}
        </div>
      </div>
    </div>
  );
}
