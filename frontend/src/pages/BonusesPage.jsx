import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../hooks/useAuth";
import { useSessionCtx } from "../hooks/useSessionCtx";
import { openLiveChat } from "../lib/events";
import GiftCard from "../components/bonuses/GiftCard";
import WeeklyCard from "../components/bonuses/WeeklyCard";
import { formatMoney } from "../lib/api";

const PREVIEW = [
  { id: "g1", kind: "percent", min_rap: 500, status: "inactive" },
  { id: "g2", kind: "skin", min_rap: 200, status: "locked", item: { name: "Glove Case", type: "Case", price: 43, image: "https://bloxstrike.net/items/bloxstrike-live/123594181073716.png" } },
  { id: "g3", kind: "skin", min_rap: 500, status: "locked", item: { name: "Railgun", type: "AWP", price: 152, image: "https://bloxstrike.net/items/bloxstrike-live/124999883032205.png" } },
  { id: "g4", kind: "skin", min_rap: 2000, status: "locked", item: { name: "Aniki", type: "AK-47", price: 299, image: "https://bloxstrike.net/items/bloxstrike-live/83000635050744.png" } },
];
const TEXT = {
  ru: { kicker: "Подарки BLOXGRADE", title: "Бонусы", sub: "Пополняйте и открывайте подарки по цепочке: каждый следующий доступен после получения предыдущего и нового пополнения.", login: "Войти через Discord", req: "Хочу получить доступ к еженедельному бонусу: Display Name в Roblox поменял на bloxgrade." },
  en: { kicker: "BLOXGRADE gifts", title: "Bonuses", sub: "Top up and unlock gifts in order: each next gift opens after claiming the previous one and a new top-up.", login: "Log in with Discord", req: "I want access to the weekly bonus: my Roblox Display Name is now bloxgrade." },
};
const RULES = {
  ru: (x) => [`Перед выводом любых скинов нужно отыграть бонусы: сделать ставок в апгрейдах на сумму бонусов × ${x}.`, "Подарочные скины нельзя вывести или продать — их можно поставить в апгрейд, выигранный скин уже обычный.", "Один Roblox-аккаунт — один набор бонусов. Мультиаккаунты блокируются.", "Засчитываются игры со ставкой от 1 RAP."],
  en: (x) => [`Before withdrawing any skins, wager your bonuses: upgrade stakes totalling bonuses × ${x}.`, "Gift skins can't be withdrawn or sold — stake them in an upgrade; a won skin is a normal skin.", "One Roblox account — one set of bonuses. Multi-accounts are blocked.", "Only games with a stake of 1 RAP or more count."],
};

const WagerBar = ({ wager, lang }) => {
  const pctDone = wager.required ? Math.min(100, (wager.wagered / wager.required) * 100) : 100;
  return (
    <section className="bonus-weekly fade-up" data-testid="bonus-wager">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[13px]">
        <b>{lang === "en" ? "Bonus wagering" : "Отыгрыш бонусов"}</b>
        <span className="tabular-nums text-[#a4a7b8]" data-testid="bonus-wager-progress">{formatMoney(wager.wagered)} / {formatMoney(wager.required)} RAP</span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-white/[0.06] overflow-hidden"><div className="h-full rounded-full bg-[#ffb000] transition-[width] duration-500" style={{ width: `${pctDone}%` }} /></div>
      <div className={`mt-2 text-[12px] ${wager.left > 0 ? "text-[#ffcf5a]" : "text-[#7ee2a8]"}`} data-testid="bonus-wager-left">{wager.left > 0 ? (lang === "en" ? `Withdrawals open after ${formatMoney(wager.left)} RAP more in upgrades` : `Вывод откроется после ставок ещё на ${formatMoney(wager.left)} RAP`) : (lang === "en" ? "Wagering complete — withdrawals available" : "Бонусы отыграны — вывод доступен")}</div>
    </section>
  );
};

const errText = (e, lang) => (typeof e?.response?.data?.detail === "string" ? e.response.data.detail : lang === "en" ? "Error" : "Ошибка");

export default function BonusesPage() {
  const { lang } = useLang();
  const t = TEXT[lang] || TEXT.ru;
  const { authUser, openAuth } = useAuth();
  const { setTopUpOpen, refreshUser } = useSessionCtx();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => (authUser ? api.bonuses().then(setData).catch(() => {}) : setData(null)), [authUser]);
  useEffect(() => { load(); }, [load]);
  const run = async (fn, ok) => {
    if (busy) return;
    setBusy(true);
    try { setData(await fn()); if (ok) toast.success(ok); refreshUser(); } catch (e) { toast.error(errText(e, lang)); } finally { setBusy(false); }
  };
  const support = async () => {
    try { const chat = await api.createChat({ kind: "support", text: t.req }); openLiveChat(chat.id); } catch (e) { toast.error(errText(e, lang)); }
  };
  const gifts = data?.gifts || PREVIEW;
  const topUp = () => (authUser ? setTopUpOpen(true) : openAuth());
  return (
    <div className="max-w-[1180px] mx-auto pb-10" data-testid="bonuses-page">
      <header className="bonus-hero fade-up">
        <img src="/brand/gift.webp" alt="" className="bonus-hero-gift" width="240" height="256" />
        <div className="relative min-w-0">
          <div className="text-[11px] uppercase tracking-[0.2em] font-bold text-[#ffcf5a]">{t.kicker}</div>
          <h1 className="text-[34px] sm:text-[44px] font-black leading-none mt-2" data-testid="bonuses-title">{t.title}</h1>
          <p className="text-[13px] text-[#a4a7b8] mt-3 max-w-[520px] leading-relaxed">{t.sub}</p>
          {!authUser && <button type="button" onClick={openAuth} className="bonus-btn bonus-btn-gold mt-4 w-auto px-6" data-testid="bonuses-login">{t.login}</button>}
        </div>
      </header>
      <div className="bonus-chain mt-5" data-testid="bonus-chain">
        {gifts.map((g, i) => <GiftCard key={g.id} gift={g} index={i} lang={lang} busy={busy || !authUser}
          onActivate={() => run(api.bonusActivate, lang === "en" ? "Gift 1 is active — top up from 500 RAP" : "Подарок 1 активирован — пополните от 500 RAP")}
          onClaim={(id) => run(() => api.bonusClaim(id), lang === "en" ? "Gift received" : "Подарок получен")} onTopUp={topUp} />)}
      </div>
      {data?.wager?.required > 0 && <div className="mt-5"><WagerBar wager={data.wager} lang={lang} /></div>}
      <div className="mt-5">
        <WeeklyCard weekly={data?.weekly} lang={lang} busy={busy} authed={Boolean(authUser)} onSupport={support}
          onClaim={() => run(api.bonusWeekly, lang === "en" ? "+20 RAP credited" : "+20 RAP зачислено")} />
      </div>
      <section className="mt-5 blox-panel p-5 fade-up" data-testid="bonus-rules">
        <h2 className="text-[15px] font-bold mb-2">{lang === "en" ? "Bonus rules" : "Правила бонусов"}</h2>
        <ul className="space-y-1.5 text-[12px] text-[#b4b7c7] list-disc pl-5">{(RULES[lang] || RULES.ru)(data?.wager?.x || 5).map((r) => <li key={r}>{r}</li>)}</ul>
      </section>
    </div>
  );
}
