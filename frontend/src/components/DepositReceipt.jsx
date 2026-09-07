import React from "react";
import { formatMoney } from "../lib/api";
import { rarityColor } from "../lib/rarity";

export const DepositReceipt = ({ deposit, testId, compact = false }) => {
  if (!deposit || !["confirmed", "processing"].includes(deposit.status)) return null;
  const skins = deposit.issued_skins || [];
  const balance = deposit.balance_credited ?? deposit.credited ?? deposit.amount ?? 0;
  return (
    <div className="w-full space-y-2 text-[11px] text-[#b4b7c7]" data-testid={testId}>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <span data-testid={`${testId}-skins-total`}>Скины: <b className="text-[#ffb000]">{skins.length} шт. · {formatMoney(deposit.skins_total || 0)} RAP</b></span>
        <span data-testid={`${testId}-balance`}>На баланс: <b className="text-[#2ecc71]">{formatMoney(balance)} RAP</b></span>
        <span data-testid={`${testId}-total`}>Всего: <b>{formatMoney(deposit.credited ?? deposit.amount)} RAP</b></span>
      </div>
      {skins.length > 0 && <div className={`grid gap-2 ${compact ? "grid-cols-2 sm:grid-cols-5" : "grid-cols-2 sm:grid-cols-3"}`}>
        {skins.map((skin) => (
          <div key={skin.uid || skin.id} className="rounded-lg bg-[#15161c] p-2 min-w-0 border-b-2" style={{ borderColor: rarityColor(skin.rarity) }} data-testid={`${testId}-skin-${skin.uid || skin.id}`}>
            {skin.image && <img src={skin.image} alt={`${skin.type} ${skin.name}`} className="w-full aspect-[2/1] object-contain" />}
            <div className="text-[9px] text-[#7d8194] truncate">{skin.type}</div>
            <div className="font-bold truncate">{skin.name}</div>
            <div className="text-[#ffb000]">{formatMoney(skin.price)} RAP</div>
          </div>
        ))}
      </div>}
    </div>
  );
};