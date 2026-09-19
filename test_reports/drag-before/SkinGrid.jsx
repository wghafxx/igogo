import React from "react";
import { Logo, RobuxIcon } from "../Logo";
import { formatMoney } from "../../lib/api";
import { rarityColor, rarityLabel } from "../../lib/rarity";
import { skinImg } from "../../lib/img";
import { useLang } from "../../lib/i18n";

const EmptySlot = () => <div className="skin-slot" aria-hidden="true" />;

export const SkinCard = React.memo(function SkinCard({ item, onClick, onSelect, selected, disabled, testId }) {
  useLang(); // Memoized cards still refresh their price/rarity labels on locale changes.
  const color = rarityColor(item.rarity);
  const interactive = Boolean(onClick || onSelect);
  const Tag = interactive ? "button" : "div";
  return (
    <Tag
      type={interactive ? "button" : undefined}
      disabled={interactive ? disabled : undefined}
      aria-pressed={interactive ? Boolean(selected) : undefined}
      aria-label={`${item.type} ${item.name}, ${formatMoney(item.price)} RAP`}
      className={`skin-slot skin-card w-full ${interactive ? "cursor-pointer disabled:cursor-wait" : ""} ${selected ? "selected" : ""}`}
      style={{ "--rarity": color }}
      onClick={onSelect ? () => onSelect(item) : onClick}
      data-testid={testId || `skin-${item.uid || item.id}`}
      data-rarity={item.rarity || "stock"}
    >
      <div className="absolute top-1.5 left-1.5 right-1.5 flex items-center justify-between text-[10px]">
        <span className="flex items-center gap-0.5 font-bold text-[#ffb000]">
          {formatMoney(item.price)} <RobuxIcon size={9} />
        </span>
        <span className="rarity-dot" title={rarityLabel(item.rarity)} />
      </div>
      {item.image && <img src={skinImg(item.image)} alt={item.name} draggable={false} width={128} height={128} loading="lazy" decoding="async" className="absolute inset-0 m-auto w-3/5 h-3/5 object-contain drop-shadow-[0_6px_10px_rgba(0,0,0,0.6)]" />}
      <div className="absolute inset-x-1 bottom-1.5 text-center">
        <div className="text-[8px] text-[#7d8194] truncate">{item.type}</div>
        <div className="text-[10px] font-bold truncate">{item.name}</div>
      </div>
    </Tag>
  );
});

export const PanelHeader = ({ title, children }) => (
  <div className="skin-panel-header">
    <div className="skin-panel-toolbar">
      {title && <div className="skin-panel-title">
        {typeof title === "string" && <Logo size={15} className="shrink-0" />}
        {title}
      </div>}
      {children}
    </div>
  </div>
);

const GRID = "grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-2";
const ROWS_PER_PAGE = 5;
export const getPageSize = () => ROWS_PER_PAGE * (window.innerWidth >= 1024 ? 5 : window.innerWidth >= 640 ? 4 : 3);

export const SkinGrid = ({ pageSize, children, overlay, testId }) => {
  const cards = React.Children.toArray(children).slice(0, pageSize);
  return (
    <div className="relative shrink-0 p-2 pt-0" data-testid={testId}>
      <div className={GRID}>
        {cards}
        {Array.from({ length: pageSize - cards.length }, (_, i) => <EmptySlot key={`empty-${i}`} />)}
      </div>
      {overlay && <div className="absolute inset-0 flex items-center justify-center p-4 text-center">{overlay}</div>}
    </div>
  );
};
