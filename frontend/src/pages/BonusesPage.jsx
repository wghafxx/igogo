import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../hooks/useAuth";
import { useSessionCtx } from "../hooks/useSessionCtx";
import { openLiveChat } from "../lib/events";
import GiftCard from "../components/bonuses/GiftCard";
import WeeklyCard from "../components/bonuses/WeeklyCard";

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
      <div className="mt-5">
        <WeeklyCard weekly={data?.weekly} lang={lang} busy={busy} authed={Boolean(authUser)} onSupport={support}
          onClaim={() => run(api.bonusWeekly, lang === "en" ? "+20 RAP credited" : "+20 RAP зачислено")} />
      </div>
    </div>
  );
}
