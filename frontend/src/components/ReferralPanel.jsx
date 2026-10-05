import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, formatMoney, formatNumber } from "../lib/api";
import { useLang } from "../lib/i18n";
import { LinkIcon } from "./icons/link";

export default function ReferralPanel() {
  const { t } = useLang();
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const load = useCallback(async () => {
    try { setData(await api.referrals()); setError(false); }
    catch { setError(true); }
  }, []);
  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(data.url); toast.success(t("referrals.copied")); }
    catch { toast.error(t("referrals.copy_fail")); }
  };
  return <section className="space-y-4" data-testid="referral-panel">
    <div className="rounded-xl bg-[#0f1015] p-4 space-y-3">
      <div className="flex items-center gap-2 font-bold text-[15px]"><LinkIcon size={17} className="text-[#ffb000]" />{t("referrals.heading")}</div>
      <p className="text-[12px] text-[#8e91a3] leading-relaxed">{t("referrals.intro")}</p>
      {data && <div className="flex flex-col sm:flex-row gap-2">
        <input value={data.url} readOnly onFocus={(e) => e.target.select()} aria-label={t("referrals.link")} className="min-w-0 flex-1 h-11 px-3 rounded-lg bg-[#1c1d25] text-[12px] text-[#c9ccd8] outline-none focus:ring-1 focus:ring-[#ffb000]" data-testid="referral-link" />
        <button onClick={copy} className="h-11 px-4 rounded-lg bg-[#ffb000] hover:bg-[#ffc233] text-black font-bold text-[12px]" data-testid="referral-copy">{t("referrals.copy")}</button>
      </div>}
      {error && <div className="text-[12px] text-[#ff8a8a]">{t("referrals.error")} <button onClick={load} className="text-[#00a2ff]" data-testid="referral-retry">{t("common.retry")}</button></div>}
      {!data && !error && <div className="text-[12px] text-[#8e91a3]">{t("referrals.loading")}</div>}
    </div>
    <div className="grid sm:grid-cols-2 gap-3">
      <div className="rounded-xl bg-[#ffb000]/10 p-4 space-y-1"><div className="text-[22px] font-black text-[#ffb000]">+25 RAP</div><p className="text-[12px] text-[#c9ccd8] leading-relaxed">{t("referrals.bonus_rule")}</p></div>
      <div className="rounded-xl bg-[#00a2ff]/10 p-4 space-y-1"><div className="text-[22px] font-black text-[#00a2ff]">+3,5%</div><p className="text-[12px] text-[#c9ccd8] leading-relaxed">{t("referrals.percent_rule")}</p></div>
    </div>
    <p className="text-[11px] leading-relaxed text-[#8e91a3]">{t("referrals.calculation")}</p>
    {data && <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="referral-stats">
        {[["invited", formatNumber(data.invited_count)], ["qualified", formatNumber(data.qualified_count)], ["earned", `${formatMoney(data.earned_rap)} RAP`], ["deposits", `${formatMoney(data.deposit_earned_rap)} RAP`]].map(([key, value]) => <div key={key} className="rounded-lg bg-[#0f1015] p-3"><div className="text-[11px] text-[#8e91a3]">{t(`referrals.${key}`)}</div><div className="text-[15px] font-bold mt-1 break-words" data-testid={`referral-stat-${key}`}>{value}</div></div>)}
      </div>
      <div className="space-y-2">
        <div className="text-[13px] font-bold">{t("referrals.friends")}</div>
        {!data.invites.length && <div className="py-6 text-center text-[12px] text-[#8e91a3]">{t("referrals.empty")}</div>}
        {data.invites.map((invite, index) => <div key={index} className="flex flex-wrap items-center gap-3 rounded-lg bg-[#0f1015] p-3 text-[12px]" data-testid="referral-invite">
          <b className="flex-1 min-w-[100px] break-words">{invite.nickname}</b>
          <div className="w-44 space-y-1">
            <div className={invite.qualified ? "text-[#72dca0]" : "text-[#8e91a3]"}>{invite.qualified ? t("referrals.bonus_paid") : `${formatMoney(invite.wagered_rap)} / 100 RAP`}</div>
            <div className="h-1.5 rounded-full bg-[#262833] overflow-hidden"><div style={{ width: `${Math.max(0, Math.min(100, invite.wagered_rap))}%` }} className="h-full rounded-full bg-[#ffb000]" /></div>
          </div>
          <span className="text-[#ffb000] font-bold">+{formatMoney(invite.earned_rap)} RAP</span>
        </div>)}
        {data.invited_count > data.invites.length && <p className="text-[11px] text-[#8e91a3]">{t("referrals.recent")}</p>}
      </div>
    </>}
  </section>;
}
