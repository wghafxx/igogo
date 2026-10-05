import React from "react";
import { BadgeCheck, CalendarClock, Gamepad2, Headset, Check } from "lucide-react";
import { formatMoney, parseServerDate } from "../../lib/api";

const TEXT = {
  ru: {
    title: "Еженедельный бонус", sub: "за Display Name «bloxgrade» в Roblox", per: "каждую неделю",
    rules: ["Поменяйте Display Name в Roblox на bloxgrade и укажите его в профиле сайта.", "Сыграйте минимум 10 игр за неделю (с понедельника).", "Напишите в поддержку: мы проверим, что аккаунт ваш и вы играете с него, и откроем кнопку.", "Без доказательств, что аккаунт ваш, бонус не выдаётся."],
    name: "Display Name", games: "Игр за неделю", access: "Доступ от поддержки", yes: "есть", no: "нет", claim: "Получить", claimed: "Получено на этой неделе", support: "Запросить доступ в поддержке", next: "Новая неделя", notyet: "Выполните условия",
  },
  en: {
    title: "Weekly bonus", sub: "for the “bloxgrade” Roblox Display Name", per: "every week",
    rules: ["Change your Roblox Display Name to bloxgrade and set it in your site profile.", "Play at least 10 games in the week (from Monday).", "Message support: we verify the account is yours and you play from it, then unlock the button.", "No proof that the account is yours — no bonus."],
    name: "Display Name", games: "Games this week", access: "Support access", yes: "yes", no: "no", claim: "Claim", claimed: "Claimed this week", support: "Request access from support", next: "New week", notyet: "Meet the conditions",
  },
};

const Check3 = ({ ok, label, value, testId }) => (
  <div className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-[12px] ${ok ? "bg-[#2ecc71]/10 text-[#7ee2a8]" : "bg-white/[0.04] text-[#a4a7b8]"}`} data-testid={testId}>
    <span className="inline-flex items-center gap-2">{ok ? <Check size={14} /> : <span className="w-3.5 h-3.5 rounded-full border border-current opacity-60" />}{label}</span>
    <b className="tabular-nums">{value}</b>
  </div>
);

export default function WeeklyCard({ weekly, amount, lang, busy, authed, onClaim, onSupport }) {
  const t = TEXT[lang] || TEXT.ru;
  const w = weekly || { amount: amount ?? 20, min_games: 10, games: 0 };
  return (
    <section className="bonus-weekly fade-up" style={{ animationDelay: "320ms" }} data-testid="bonus-weekly">
      <div className="flex flex-wrap items-start gap-4">
        <div className="flex-1 min-w-[220px]">
          <div className="text-[11px] uppercase tracking-[0.14em] font-bold text-[#8e91a3] inline-flex items-center gap-1.5"><CalendarClock size={13} /> {t.per}</div>
          <h2 className="text-[22px] font-black mt-1">{t.title}</h2>
          <p className="text-[13px] text-[#a4a7b8]">{t.sub}</p>
        </div>
        <div className="text-right"><div className="text-[40px] font-black leading-none text-[#ffcf5a] tabular-nums" data-testid="bonus-weekly-amount">+{formatMoney(w.amount)}</div><div className="text-[11px] text-[#8e91a3] mt-1">RAP</div></div>
      </div>
      <ol className="mt-4 space-y-1.5 text-[12px] text-[#b4b7c7] list-decimal pl-5" data-testid="bonus-weekly-rules">{t.rules.map((r) => <li key={r}>{r}</li>)}</ol>
      {authed && weekly && <div className="mt-4 grid sm:grid-cols-3 gap-2">
        <Check3 ok={w.name_ok} label={t.name} value={w.display_name || "—"} testId="bonus-weekly-name" />
        <Check3 ok={w.games >= w.min_games} label={<><Gamepad2 size={13} /> {t.games}</>} value={`${Math.min(w.games, 999)} / ${w.min_games}`} testId="bonus-weekly-games" />
        <Check3 ok={w.access} label={<><BadgeCheck size={13} /> {t.access}</>} value={w.access ? t.yes : t.no} testId="bonus-weekly-access" />
      </div>}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {authed && weekly?.claimed && <div className="bonus-status text-[#7ee2a8]" data-testid="bonus-weekly-claimed"><Check size={15} /> {t.claimed} · {t.next}: {parseServerDate(w.resets_at).toLocaleDateString(lang === "en" ? "en-GB" : "ru-RU")}</div>}
        {authed && weekly && !weekly.claimed && w.access && <button type="button" disabled={busy || !w.can_claim} onClick={onClaim} className={`bonus-btn bonus-btn-gold ${w.can_claim ? "bonus-pulse" : ""}`} data-testid="bonus-weekly-claim">{w.can_claim ? `${t.claim} +${formatMoney(w.amount)} RAP` : t.notyet}</button>}
        {authed && weekly && !w.access && <button type="button" disabled={busy} onClick={onSupport} className="bonus-btn" data-testid="bonus-weekly-support"><Headset size={15} /> {t.support}</button>}
      </div>
    </section>
  );
}
