import React from "react";
import { Logo, RobuxIcon } from "../Logo";
import { formatMoney } from "../../lib/api";
import { rarityColor } from "../../lib/rarity";
import { skinImg } from "../../lib/img";
import { useLang } from "../../lib/i18n";
import { preventGameDrag } from "../../lib/game-interactions";

const EmptySlot = () => <div className="skin-slot" aria-hidden="true" />;

export const SkinCard = React.memo(function SkinCard({ item, onClick, onSelect, selected, disabled, testId }) {
  useLang(); // Memoized cards still refresh their price/rarity labels on locale changes.
  const color = rarityColor(item.rarity);
  const interactive = Boolean(onClick || onSelect);
  const Tag = interactive ? "button" : "div";
  const id = testId || `skin-${item.uid || item.id}`;
  return (
    <Tag
      type={interactive ? "button" : undefined}
      disabled={interactive ? disabled : undefined}
      aria-pressed={interactive ? Boolean(selected) : undefined}
      aria-label={`${item.type} ${item.name}, ${formatMoney(item.price)} RAP`}
      className={`skin-slot skin-card w-full ${interactive ? "cursor-pointer disabled:cursor-wait" : ""} ${selected ? "selected" : ""}`}
      style={{ "--rarity": color }}
      onClick={onSelect ? () => onSelect(item) : onClick}
      draggable={false}
      onDragStartCapture={preventGameDrag}
      data-testid={id}
      data-rarity={item.rarity || "stock"}
    >
      <div className="skin-card-price" data-testid={`skin-card-price-${id}`}>
          {formatMoney(item.price)} <RobuxIcon size={9} />
      </div>
      {item.image && <img src={skinImg(item.image)} alt={item.name} draggable={false} width={128} height={128} loading="lazy" decoding="async" className="skin-card-image" data-testid={`skin-card-image-${id}`} />}
      <div className="skin-card-caption">
        <div className="skin-card-type" data-testid={`skin-card-type-${id}`}>{item.type}</div>
        <div className="skin-card-name" data-testid={`skin-card-name-${id}`}>{item.name}</div>
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
