import React from "react";
import { Check, Lock, Wallet, Sparkles, Gift } from "lucide-react";
import { formatMoney } from "../../lib/api";
import { skinImg } from "../../lib/img";

const TEXT = {
  ru: { step: "Подарок", from: "Пополнение от", rap: "RAP", pct: "+15% к пополнению", once: "один раз", activate: "Активировать", topup: "Пополнить", claim: "Забрать", claimed: "Получено", closed: "Закрыто", locked: "Откроется после подарка", waiting: "Ждём пополнение", ready: "Готов к получению", inactive: "Нажмите «Активировать», затем пополните", hint_pct: "От суммы после комиссии 20%" },
  en: { step: "Gift", from: "Top-up from", rap: "RAP", pct: "+15% to top-up", once: "one time", activate: "Activate", topup: "Top up", claim: "Claim", claimed: "Claimed", closed: "Locked", locked: "Unlocks after gift", waiting: "Waiting for top-up", ready: "Ready to claim", inactive: "Press “Activate”, then top up", hint_pct: "Of the amount after the 20% fee" },
};

const Reward = ({ gift, t }) => gift.kind === "percent" ? (
  <div className="bonus-reward bonus-reward-pct" data-testid={`bonus-gift-${gift.id}-reward`}>
    <span className="text-[34px] font-black leading-none text-[#ffcf5a]">+{Math.round((gift.pct ?? 0.15) * 100)}%</span>
    <span className="text-[11px] text-[#a4a7b8] mt-1">{t.hint_pct}</span>
  </div>
) : (
  <div className="bonus-reward" data-testid={`bonus-gift-${gift.id}-reward`}>
    {gift.item?.image ? <img src={skinImg(gift.item.image)} alt={gift.item.name} className="h-[74px] w-auto object-contain drop-shadow-[0_8px_18px_rgba(0,0,0,0.6)]" /> : <Gift size={40} className="text-[#ffcf5a]" />}
    <span className="text-[12px] font-bold mt-1 text-center truncate max-w-full">{gift.item ? `${gift.item.type} | ${gift.item.name}` : "—"}</span>
    {gift.item && <span className="text-[11px] text-[#ffcf5a] tabular-nums">{formatMoney(gift.item.price)} RAP</span>}
  </div>
);

const Action = ({ gift, t, busy, onActivate, onClaim, onTopUp, index }) => {
  if (gift.status === "claimed") return <div className="bonus-status text-[#7ee2a8]" data-testid={`bonus-gift-${gift.id}-claimed`}><Check size={15} /> {t.claimed}{gift.kind === "percent" && gift.amount ? ` · +${formatMoney(gift.amount)}` : ""}</div>;
  if (gift.status === "locked") return <div className="bonus-status text-[#6b6f84]"><Lock size={14} /> {t.closed}</div>;
  if (gift.status === "inactive") return <button type="button" disabled={busy} onClick={onActivate} className="bonus-btn bonus-btn-gold" data-testid="bonus-gift-g1-activate"><Sparkles size={15} /> {t.activate}</button>;
  if (gift.status === "claimable") return <button type="button" disabled={busy} onClick={() => onClaim(gift.id)} className="bonus-btn bonus-btn-gold bonus-pulse" data-testid={`bonus-gift-${gift.id}-claim`}><Gift size={15} /> {t.claim}{gift.amount && gift.kind === "percent" ? ` +${formatMoney(gift.amount)} RAP` : ""}</button>;
  return <button type="button" onClick={onTopUp} className="bonus-btn" data-testid={`bonus-gift-${gift.id}-topup`}><Wallet size={15} /> {t.topup}</button>;
};

export default function GiftCard({ gift, index, lang, busy, onActivate, onClaim, onTopUp }) {
  const t = TEXT[lang] || TEXT.ru;
  const label = { claimable: t.ready, waiting: t.waiting, inactive: t.inactive, claimed: t.claimed, locked: `${t.locked} ${index}` }[gift.status];
  return (
    <article className={`bonus-gift fade-up ${gift.status}`} style={{ animationDelay: `${index * 70}ms` }} data-testid={`bonus-gift-${gift.id}`} data-status={gift.status}>
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] uppercase tracking-[0.14em] font-bold text-[#8e91a3]">{t.step} {index + 1}</span>
        <span className="self-start rounded-full bg-[#ffb000]/10 border border-[#ffb000]/25 px-2.5 py-0.5 text-[11px] font-bold text-[#ffcf5a] whitespace-nowrap" data-testid={`bonus-gift-${gift.id}-min`}>{t.from} {Math.round(gift.min_rap)} {t.rap}</span>
      </div>
      <Reward gift={gift} t={t} />
      <div className="text-[11px] text-[#8e91a3] text-center min-h-[16px]" data-testid={`bonus-gift-${gift.id}-status`}>{label}{gift.kind === "percent" ? ` · ${t.once}` : ""}</div>
      <Action gift={gift} t={t} busy={busy} index={index} onActivate={onActivate} onClaim={onClaim} onTopUp={onTopUp} />
    </article>
  );
}
