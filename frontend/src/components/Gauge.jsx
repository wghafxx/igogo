import React from "react";
import { useLang } from "../lib/i18n";
import { rarityColor } from "../lib/rarity";

const CX = 150;
const CY = 150;
const R = 113; // ring center radius
const STROKE = 30;
const CIRC = 2 * Math.PI * R;
const OUTER = R + STROKE / 2; // 128

const polar = (deg, r) => {
  const rad = ((deg - 90) * Math.PI) / 180;
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
};

// Deterministic "random" ray lengths for the faint halo of thin lines outside the rim
const RAYS = Array.from({ length: 60 }, (_, i) => {
  const s = Math.sin(i * 12.9898) * 43758.5453;
  return { deg: i * 6, len: 4 + (s - Math.floor(s)) * 10 };
});

// Each half of the zone is a dash anchored at the bottom point (offset = CIRC/4) and only its length animates,
// so the zone grows from the bottom upward on both sides instead of rotating into place.
const halfDash = (half) => ({ strokeDasharray: `${(CIRC * half) / 360} ${CIRC}`, strokeDashoffset: -CIRC / 4 });

const Gauge = React.memo(function Gauge({ chance, rotation, spinning, fast, result, phrase, onSpinEnd }) {
  const { t } = useLang();
  const half = Math.max(0, Math.min(chance * 180, 179.9));
  const dash = halfDash(half);

  const ringClass = `gauge-ring ${fast ? "fast" : ""}`;
  const rare = Boolean(result && phrase && phrase.endsWith("_rare"));
  const centerColor = result === "win" ? "#3ddc84" : result === "lose" ? "#ff5c5c" : "#ffffff";
  const chanceLabel = chance <= 0.15 ? t("gauge.low") : chance <= 0.5 ? t("gauge.mid") : t("gauge.high");
  const resultLabel = phrase ? t(phrase) : result === "win" ? t("gauge.win") : t("gauge.lose");
  const pTop = CY - OUTER; // outer edge of ring at top

  return (
    <div className="relative w-[min(300px,82vw)] h-[min(300px,82vw)] mx-auto select-none" data-testid="upgrade-gauge">
      {/* Use a plain translucent disc; a live backdrop filter here re-samples
          the title/header edge during scroll and can leave a visible band. */}
      <div className="absolute inset-[6.4%] rounded-full bg-[#0f1015]/75" aria-hidden="true" data-testid="gauge-disc" />
      <svg viewBox="0 0 300 300" className="relative w-full h-full overflow-visible">
        <defs>
          <linearGradient id="zone-grad" x1="50%" y1="100%" x2="50%" y2="0%">
            <stop offset="0%" stopColor="#be4a1d" />
            <stop offset="45%" stopColor="#e8862f" />
            <stop offset="80%" stopColor="#ffbf48" />
            <stop offset="100%" stopColor="#ffe6a3" />
          </linearGradient>
          <linearGradient id="zone-glow" x1="50%" y1="100%" x2="50%" y2="0%">
            <stop offset="0%" stopColor="#be4a1d" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#ffbf48" stopOpacity="1" />
          </linearGradient>
          <filter id="zone-blur" filterUnits="userSpaceOnUse" x="-60" y="-60" width="420" height="420">
            <feGaussianBlur stdDeviation="11" />
          </filter>
          <filter id="zone-noise" x="0" y="0" width="100%" height="100%">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="7" stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
          </filter>
          <pattern id="zone-texture" patternUnits="userSpaceOnUse" width="64" height="64">
            <rect width="64" height="64" filter="url(#zone-noise)" />
          </pattern>
          <linearGradient id="rim-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#5d5f66" />
            <stop offset="1" stopColor="#35363c" />
          </linearGradient>
          <linearGradient id="arrow-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#fff2b9" />
            <stop offset="0.5" stopColor={rarityColor("gold")} />
            <stop offset="1" stopColor="#a77b21" />
          </linearGradient>
        </defs>

        {/* faint outer rays */}
        <g stroke="#d7dae3" strokeOpacity="0.16" strokeWidth="1" strokeLinecap="round">
          {RAYS.map(({ deg, len }) => {
            const a = polar(deg, OUTER + 7);
            const b = polar(deg, OUTER + 7 + len);
            return <line key={deg} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />;
          })}
        </g>

        {/* grey rim */}
        <circle cx={CX} cy={CY} r={OUTER + 1.5} fill="none" stroke="url(#rim-grad)" strokeWidth="3" />

        {/* dark translucent track */}
        <circle cx={CX} cy={CY} r={R} fill="none" stroke="rgba(0,0,0,0.35)" strokeWidth={STROKE} />

        {/* win zone: left half grows clockwise from the bottom, right half is its mirror */}
        <g data-testid="gauge-zone">
          {[1, -1].map((dir) => (
            <g key={dir} transform={dir === -1 ? `translate(${CX * 2} 0) scale(-1 1)` : undefined}>
              <g className="gauge-zone-halo">
                <circle cx={CX} cy={CY} r={R} fill="none" stroke="url(#zone-glow)" strokeWidth={STROKE + 10} strokeLinecap="round" opacity="0.6" filter="url(#zone-blur)" className="gauge-zone-arc" style={dash} />
              </g>
              <circle cx={CX} cy={CY} r={R} fill="none" stroke="url(#zone-grad)" strokeWidth={STROKE} strokeLinecap="butt" className="gauge-zone-arc" style={dash} />
              <circle cx={CX} cy={CY} r={R} fill="none" stroke="url(#zone-texture)" strokeWidth={STROKE} strokeLinecap="butt" opacity="0.14" className="gauge-zone-arc" style={dash} />
            </g>
          ))}
        </g>

        {/* inner disc */}
        <circle cx={CX} cy={CY} r={R - STROKE / 2} fill="none" stroke="rgba(0,0,0,0.55)" strokeWidth="1.5" />
        <circle cx={CX} cy={CY} r={R - STROKE / 2 - 1.5} fill="rgba(15,16,21,0.35)" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
        <circle cx={CX} cy={CY} r={R - STROKE / 2 - 9} fill="rgba(0,0,0,0.3)" />

        {/* rotating arrow: slim chevron on the ring edge, tip pointing into the wheel */}
        <g className={ringClass} style={{ transform: `rotate(${rotation}deg)` }} data-testid="gauge-pointer"
          onTransitionEnd={(event) => {
            if (event.target === event.currentTarget && event.propertyName === "transform") onSpinEnd?.();
          }}>
          <g style={{ filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.7))" }}>
            <path d={`M ${CX} ${pTop + 26} L ${CX - 11} ${pTop - 8} L ${CX} ${pTop - 2} L ${CX + 11} ${pTop - 8} Z`} fill="url(#arrow-grad)" />
            <path d={`M ${CX} ${pTop + 26} L ${CX} ${pTop - 2} L ${CX + 11} ${pTop - 8} Z`} fill="rgba(0,0,0,0.25)" />
            <path d={`M ${CX - 11} ${pTop - 8} L ${CX} ${pTop - 2} L ${CX + 11} ${pTop - 8}`} fill="none" stroke="#fff3cc" strokeOpacity="0.7" strokeWidth="1" strokeLinejoin="round" />
          </g>
        </g>
      </svg>

      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <div
          className="text-[30px] sm:text-[36px] font-black leading-none tabular-nums transition-colors duration-300"
          style={{ color: centerColor }}
          data-testid="gauge-chance"
        >
          {(chance * 100).toFixed(2)}%
        </div>
        <div className={`text-[12px] mt-1.5 text-center px-6 leading-tight transition-colors duration-300 ${rare ? "font-black text-[#ffd44d] gauge-rare" : result && !spinning ? "font-bold text-white/85" : "text-[#7d8194]"}`} data-testid="gauge-label" data-phrase={result ? phrase || undefined : undefined}>
          {spinning ? t("gauge.spinning") : result ? resultLabel : chanceLabel}
        </div>
      </div>
    </div>
  );
});

export default Gauge;
