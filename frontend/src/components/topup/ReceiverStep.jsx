import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { ExternalLinkIcon } from "../icons/external-link";
import { ArrowLeftIcon } from "../icons/arrow-left";
import { BadgeAlertIcon } from "../icons/badge-alert";
import { RobuxIcon } from "../Logo";
import RobloxLinkCard from "../RobloxLinkCard";
import { api, formatMoney } from "../../lib/api";
import { useAuth } from "../../hooks/useAuth";
import { useLang } from "../../lib/i18n";
import { calcCredit } from "./AmountStep";

const STEPS_KEYS = ["receiver.step1", "receiver.step2", "receiver.step3", "receiver.step4"];

export default function ReceiverStep({ receivers, rap, onBack, onDone }) {
  const { authUser } = useAuth();
  const { t } = useLang();
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
      toast.success(t("receiver.sent"));
      onDone(d);
    } catch (e) {
      const m = e?.response?.data?.detail;
      toast.error(typeof m === "string" ? m : t("receiver.fail"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="topup-receiver-step">
      <button onClick={onBack} className="text-[12px] text-[#8e91a3] hover:text-white inline-flex items-center gap-1" data-testid="topup-back-button">
        <ArrowLeftIcon size={13} /> {t("receiver.back")}
      </button>

      <div className="text-[12px] text-[#8e91a3]">{t("receiver.to")}</div>
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
              {t("receiver.profile")} <ExternalLinkIcon size={12} />
            </a>
          </div>
        ))}
      </div>

      <div className="rounded-lg bg-[#ff5c5c]/15 border border-[#ff5c5c]/50 px-3 py-2 text-center text-[15px] font-black uppercase tracking-wide text-[#ff3b3b] leading-snug" data-testid="topup-fake-warning">
        {t("receiver.fake")}
      </div>

      <ol className="space-y-1.5" data-testid="topup-steps">
        {STEPS_KEYS.map((key, i) => (
          <li key={key} className="flex gap-2.5 text-[12px] text-[#b4b7c7] leading-snug">
            <span className="w-5 h-5 rounded-full bg-[#ffb000] text-black font-black text-[11px] flex items-center justify-center shrink-0">{i + 1}</span>
            <span>{t(key)}</span>
          </li>
        ))}
      </ol>

      <div className="rounded-lg bg-[#ff5c5c]/10 border border-[#ff5c5c]/40 px-3 py-2 flex items-start gap-2 text-[11px] text-[#ff9b9b] leading-snug" data-testid="topup-warning">
        <BadgeAlertIcon size={14} className="shrink-0 mt-0.5" />
        <span>{t("receiver.warn")} <b>{t("receiver.warn_note")}</b></span>
      </div>

      <div className="rounded-xl bg-[#0f1015] p-3 space-y-2" data-testid="topup-roblox-block">
        <div className="text-[11px] uppercase text-[#7d8194]">{t("receiver.roblox_title")}</div>
        <RobloxLinkCard />
        {!linked && <div className="text-[11px] text-[#ff9b9b]" data-testid="topup-roblox-required">{t("receiver.roblox_required")}</div>}
      </div>

      <textarea
        value={desc}
        onChange={(e) => setDesc(e.target.value.slice(0, 300))}
        placeholder={t("receiver.desc_ph")}
        className="w-full h-20 p-3 rounded-xl bg-[#0f1015] outline-none text-[13px] resize-none focus:ring-1 focus:ring-[#ffb000] placeholder:text-[#5f6377]"
        data-testid="deposit-description-input"
      />

      <button
        onClick={submit}
        disabled={busy || !receiver || !linked || desc.trim().length < 3}
        className="w-full py-3.5 rounded-xl bg-[#ffb000] hover:bg-[#ffc233] disabled:opacity-40 text-black font-black text-[15px] flex flex-wrap items-center justify-center gap-2 transition-colors"
        data-testid="deposit-submit-button"
      >
        {t("receiver.confirm")} · {formatMoney(Number(rap))} RAP <span className="text-[12px] font-bold text-black/60 inline-flex items-center gap-1">{t("receiver.skins_remainder")} {formatMoney(credit)} <RobuxIcon size={11} />)</span>
      </button>
    </div>
  );
}
