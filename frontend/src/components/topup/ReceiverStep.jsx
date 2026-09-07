import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { ExternalLinkIcon } from "../icons/external-link";
import { ArrowLeftIcon } from "../icons/arrow-left";
import { BadgeAlertIcon } from "../icons/badge-alert";
import { RobuxIcon } from "../Logo";
import RobloxLinkCard from "../RobloxLinkCard";
import { api, formatMoney } from "../../lib/api";
import { useAuth } from "../../hooks/useAuth";
import { calcCredit } from "./AmountStep";

const STEPS = [
  "Добавьте наш аккаунт в друзья и дождитесь принятия заявки.",
  "Зайдите в игру, откройте Trade Plaza и выберите наш ник в списке друзей.",
  "Положите в трейд свои скины (каждый от 20 RAP) и отправьте — ничего не просите взамен.",
  "Впишите ниже названия скинов и нажмите «Подтвердить».",
];

export default function ReceiverStep({ receivers, rap, onBack, onDone }) {
  const { authUser } = useAuth();
  const [receiver, setReceiver] = useState(receivers[0]);
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setReceiver((current) => receivers.find((r) => r.id === current?.id) || receivers[0]); }, [receivers]);
  const linked = Boolean(authUser?.roblox_nick && authUser?.roblox_link);
  const credit = calcCredit(Number(rap), authUser?.promo_bonus);

  const submit = async () => {
    if (busy || !receiver || !linked || desc.trim().length < 3) return;
    setBusy(true);
    try {
      const d = await api.createDeposit({ description: desc.trim(), expected_rap: Number(rap), receiver_id: receiver.id });
      toast.success("Заявка отправлена. После проверки трейда получите скины и остаток на баланс");
      onDone(d);
    } catch (e) {
      const m = e?.response?.data?.detail;
      toast.error(typeof m === "string" ? m : "Не удалось отправить заявку");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="topup-receiver-step">
      <button onClick={onBack} className="text-[12px] text-[#8e91a3] hover:text-white inline-flex items-center gap-1" data-testid="topup-back-button">
        <ArrowLeftIcon size={13} /> Изменить сумму
      </button>

      <div className="text-[12px] text-[#8e91a3]">Кому отправить трейд</div>
      <div className="space-y-2" data-testid="topup-receivers">
        {receivers.map((r) => (
          <div
            key={r.id}
            className={`w-full rounded-xl p-3 flex flex-wrap items-center gap-3 text-left border transition-colors ${receiver?.id === r.id ? "border-[#ffb000] bg-[#ffb000]/10" : "border-[#2a2b31] bg-[#0f1015] hover:border-[#3a3c47]"}`}
            data-testid={`topup-receiver-${r.id}`}
          >
            <img src={r.avatar} alt={r.nickname} className="w-14 h-14 rounded-full object-cover bg-[#2a2b31]" />
            <button onClick={() => setReceiver(r)} data-testid={`topup-select-receiver-${r.id}`} className="min-w-0 flex-1 text-left">
              <div className="text-[15px] font-black" data-testid="topup-receiver-nick">{r.nickname}</div>
              <div className="text-[12px] text-[#8e91a3]">{r.handle} · Roblox</div>
            </button>
            <a href={r.friend_url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="h-9 px-3 rounded-lg bg-[#00a2ff] hover:bg-[#1ab0ff] text-white text-[12px] font-bold inline-flex items-center gap-1.5 shrink-0" data-testid="topup-open-profile">
              Профиль <ExternalLinkIcon size={12} />
            </a>
          </div>
        ))}
      </div>

      <ol className="space-y-1.5" data-testid="topup-steps">
        {STEPS.map((s, i) => (
          <li key={i} className="flex gap-2.5 text-[12px] text-[#b4b7c7] leading-snug">
            <span className="w-5 h-5 rounded-full bg-[#ffb000] text-black font-black text-[11px] flex items-center justify-center shrink-0">{i + 1}</span>
            <span>{s}</span>
          </li>
        ))}
      </ol>

      <div className="rounded-lg bg-[#ff5c5c]/10 border border-[#ff5c5c]/40 px-3 py-2 flex items-start gap-2 text-[11px] text-[#ff9b9b] leading-snug" data-testid="topup-warning">
        <BadgeAlertIcon size={14} className="shrink-0 mt-0.5" />
        <span>Скины дешевле 20 RAP не зачисляются. Отправляйте трейд только с аккаунта, привязанного ниже — иначе мы не поймём, кому начислять.</span>
      </div>

      <div className="rounded-xl bg-[#0f1015] p-3 space-y-2" data-testid="topup-roblox-block">
        <div className="text-[11px] uppercase text-[#7d8194]">Ваш Roblox (с него должен прийти трейд)</div>
        <RobloxLinkCard />
        {!linked && <div className="text-[11px] text-[#ff9b9b]" data-testid="topup-roblox-required">Без привязанного Roblox отправить заявку нельзя.</div>}
      </div>

      <textarea
        value={desc}
        onChange={(e) => setDesc(e.target.value.slice(0, 300))}
        placeholder="Названия скинов, которые отправили. Например: Karambit Tiger Stripes, Glove Case ×2"
        className="w-full h-20 p-3 rounded-xl bg-[#0f1015] outline-none text-[13px] resize-none focus:ring-1 focus:ring-[#ffb000] placeholder:text-[#5f6377]"
        data-testid="deposit-description-input"
      />

      <button
        onClick={submit}
        disabled={busy || !receiver || !linked || desc.trim().length < 3}
        className="w-full py-3.5 rounded-xl bg-[#ffb000] hover:bg-[#ffc233] disabled:opacity-40 text-black font-black text-[15px] flex flex-wrap items-center justify-center gap-2 transition-colors"
        data-testid="deposit-submit-button"
      >
        Подтвердить · {formatMoney(Number(rap))} RAP <span className="text-[12px] font-bold text-black/60 inline-flex items-center gap-1">(скины + остаток: {formatMoney(credit)} <RobuxIcon size={11} />)</span>
      </button>
    </div>
  );
}
