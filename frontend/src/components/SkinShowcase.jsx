import React from "react";
import { REEL_FINAL, REEL_FLY, REEL_START, rarityColor } from "../lib/rarity";

const SideCard = ({ image, side }) => (
  <div className={`reel-side reel-side-${side}`} aria-hidden="true">
    <img src={image} alt="" className="reel-side-img" draggable={false} />
  </div>
);

const Caption = ({ item }) => (
  <div className="reel-caption">
    <div className="reel-caption-type">{item.type}</div>
    <div className="reel-caption-name">{item.name}</div>
  </div>
);

export default function SkinShowcase({ size = "md", className = "" }) {
  const strip = [...REEL_FLY, ...REEL_FLY, ...REEL_FLY];
  return (
    <div
      className={`reel reel-${size} ${className}`}
      style={{ "--start": rarityColor(REEL_START.rarity), "--final": rarityColor(REEL_FINAL.rarity) }}
      data-testid="skin-showcase"
    >
      <SideCard image={REEL_FLY[1].image} side="left" />
      <SideCard image={REEL_FLY[2].image} side="right" />

      <div className="reel-frame">
        <div className="reel-card">
          <div className="reel-glow" />

          <div className="reel-item reel-start" data-testid="reel-start-item">
            <img src={REEL_START.image} alt={REEL_START.name} className="reel-img" draggable={false} />
            <Caption item={REEL_START} />
          </div>

          <div className="reel-strip" data-testid="reel-strip">
            {strip.map((s, i) => (
              <img key={`${s.id}-${i}`} src={s.image} alt="" className="reel-strip-img" draggable={false} />
            ))}
          </div>

          <div className="reel-item reel-final" data-testid="reel-final-item">
            <img src={REEL_FINAL.image} alt={REEL_FINAL.name} className="reel-img" draggable={false} />
            <Caption item={REEL_FINAL} />
          </div>

          <div className="reel-flash" />
        </div>
      </div>
    </div>
  );
}
