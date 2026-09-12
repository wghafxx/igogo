import React from "react";
import { Logo, RobuxIcon } from "../Logo";
import { formatMoney } from "../../lib/api";
import { rarityColor, rarityLabel } from "../../lib/rarity";

const EmptySlot = () => <div className="skin-slot" aria-hidden="true" />;

export const SkinCard = ({ item, onClick, selected, disabled, testId }) => {
  const color = rarityColor(item.rarity);
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      disabled={onClick ? disabled : undefined}
      aria-pressed={onClick ? Boolean(selected) : undefined}
      aria-label={`${item.type} ${item.name}, ${formatMoney(item.price)} RAP`}
      className={`skin-slot skin-card w-full ${onClick ? "cursor-pointer disabled:cursor-wait" : ""} ${selected ? "selected" : ""}`}
      style={{ "--rarity": color }}
      onClick={onClick}
      data-testid={testId || `skin-${item.uid || item.id}`}
      data-rarity={item.rarity || "stock"}
    >
      <div className="absolute top-1.5 left-1.5 right-1.5 flex items-center justify-between text-[10px]">
        <span className="flex items-center gap-0.5 font-bold text-[#ffb000]">
          {formatMoney(item.price)} <RobuxIcon size={9} />
        </span>
        <span className="rarity-dot" title={rarityLabel(item.rarity)} />
      </div>
      {item.image && <img src={item.image} alt={item.name} className="absolute inset-0 m-auto w-3/5 h-3/5 object-contain drop-shadow-[0_6px_10px_rgba(0,0,0,0.6)]" />}
      <div className="absolute inset-x-1 bottom-1.5 text-center">
        <div className="text-[8px] text-[#7d8194] truncate">{item.type}</div>
        <div className="text-[10px] font-bold truncate">{item.name}</div>
      </div>
    </Tag>
  );
};

export const PanelHeader = ({ title, children, compact = false }) => (
  <div className={`${compact ? "min-h-[52px]" : "min-h-[104px]"} px-3 py-2 flex flex-wrap items-center gap-2 sm:gap-3`}>
    {typeof title === "string" && <div className="w-8 h-8 rounded-md bg-[#00a2ff] flex items-center justify-center shrink-0">
      <Logo size={16} className="[&_path]:fill-white" />
    </div>}
    {title && <div className="font-bold text-[14px] whitespace-nowrap">{title}</div>}
    {children}
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
