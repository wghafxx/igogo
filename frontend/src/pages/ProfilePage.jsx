import React, { useCallback, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { CircleDollarSignIcon } from "../components/icons/circle-dollar-sign";
import { WalletIcon } from "../components/icons/wallet";
import { SparklesIcon } from "../components/icons/sparkles";
import { SendIcon } from "../components/icons/send";
import { BoxesIcon } from "../components/icons/boxes";
import { HistoryIcon } from "../components/icons/history";
import { ZapIcon } from "../components/icons/zap";
import { toast } from "sonner";
import { Logo, RobuxIcon } from "../components/Logo";
import { SkinCard } from "../components/SkinsSection";
import TopUpModal, { PromoInput, DepositStatus } from "../components/TopUpModal";
import { WalletIcon as PayIcon } from "../components/icons/wallet";
import RobloxLinkCard from "../components/RobloxLinkCard";
import Nick from "../components/Nick";
import { LinkIcon } from "../components/icons/link";
import { useAuth } from "../hooks/useAuth";
import { useSessionCtx } from "../hooks/useSessionCtx";
import { api, formatMoney, inventoryTotal, parseServerDate } from "../lib/api";
import { useLang } from "../lib/i18n";
import { rarityColor } from "../lib/rarity";
import { DepositReceipt } from "../components/DepositReceipt";

const KIND_KEYS = { won: "profile.kind_won", sold: "profile.kind_sold", withdrawn: "profile.kind_withdrawn", withdraw_requested: "profile.kind_requested", deposited: "profile.kind_deposited", purchased: "profile.kind_purchased" };

const InventoryCard = ({ t, item, active, onToggle, onSell, onWithdraw, busy }) => (
  <div className={`inv-card ${active ? "active" : ""}`} style={{ "--rarity": rarityColor(item.rarity) }} data-testid="inventory-item">
    <SkinCard item={item} selected={active} onClick={onToggle} />
    <div className="inv-actions" onClick={(e) => e.stopPropagation()}>
      <button className="btn-sell" disabled={busy} onClick={onSell} data-testid="item-sell-button">
        {t("profile.sell")} {formatMoney(item.price)} <RobuxIcon size={9} />
      </button>
      <button className="btn-withdraw" disabled={busy} onClick={onWithdraw} data-testid="item-withdraw-button">
        <SendIcon size={11} /> {t("profile.withdraw")}
      </button>
    </div>
  </div>
);

const Stat = ({ title, icon: Icon, children, testId }) => (
  <div className="blox-panel p-4 flex flex-col gap-2" data-testid={testId}>
    <div className="flex items-center justify-between text-[13px] text-[#8e91a3]">
      {title}
      <span className="w-7 h-7 rounded-md bg-[#0f1015] flex items-center justify-center text-[#ffb000]">
        <Icon size={14} />
      </span>
    </div>
    {children}
  </div>
);

export default function ProfilePage() {
  const { authUser, loading, setAuthUser } = useAuth();
  const { refreshUser, openWithdrawalSupport } = useSessionCtx();
  const { t, lang } = useLang();
  const fmtDate = (d) => parseServerDate(d).toLocaleString(lang === "en" ? "en-US" : "ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("inventory");
  const [active, setActive] = useState(null);
  const [topUpOpen, setTopUpOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const [deposits, setDeposits] = useState([]);
  const [loadError, setLoadError] = useState(false);
  const load = useCallback(() => {
    setLoadError(false);
    return Promise.all([api.profile(), api.myDeposits()]).then(([profile, payments]) => {
      setData(profile); setDeposits(payments);
    }).catch(() => setLoadError(true));
  }, []);
  useEffect(() => {
    if (authUser) load();
  }, [authUser, load]);

  if (!loading && !authUser) return <Navigate to="/" replace />;

  const skins = data?.user?.skins || [];
  const invTotal = inventoryTotal(skins);

  const act = async (fn, uids, msg, onSuccess) => {
    if (!uids.length || busy) return;
    setBusy(true);
    try {
      const u = await fn(uids);
      setAuthUser(u);
      setActive(null);
      toast.success(msg(uids.length));
      onSuccess?.(uids.length);
      load();
      refreshUser();
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("common.error"));
    } finally {
      setBusy(false);
    }
  };
  const sell = (uids) => act(api.sellSkins, uids, (n) => `${t("profile.sold")} ${n} ${t("common.items_unit")} — ${t("profile.sold_tail")}`);
  const withdraw = (uids) => act(api.withdrawSkins, uids, (n) => `${t("profile.withdraw_created")} ${n} ${t("common.items_unit")} ${t("profile.withdraw_created_tail")}`, openWithdrawalSupport);

  return (
    <div className="max-w-[1000px] mx-auto space-y-4" data-testid="profile-page">
      {loadError && <div className="blox-panel p-4 text-sm text-[#ff8a8a]" data-testid="profile-load-error">{t("profile.load_fail")} <button onClick={load} className="text-[#00a2ff]" data-testid="profile-retry">{t("common.retry")}</button></div>}
        <div className="blox-panel p-3 grid grid-cols-1 md:grid-cols-[300px_1fr_1fr] gap-3 fade-up">
          <div className="rounded-xl bg-[#0f1015] p-4 flex flex-col gap-3" data-testid="profile-card">
            <div className="flex items-center gap-4">
              {authUser?.avatar && <img src={authUser.avatar} alt="" className="w-16 h-16 rounded-lg object-cover" data-testid="profile-page-avatar" />}
              <div className="min-w-0">
                <Nick gold={authUser?.gold_nick} className="font-bold text-[15px] truncate block" testId="profile-page-nickname">{authUser?.nickname}</Nick>
                <div className="mt-1 inline-flex items-center text-[11px] text-[#8e91a3] bg-[#1c1d25] rounded px-2 py-0.5" data-testid="profile-page-id">ID {authUser?.discord_id}</div>
                {authUser?.gold_nick && <div className="mt-1 text-[10px] font-bold text-[#ffb000]" data-testid="profile-gold-badge">{t("profile.gold")}</div>}
              </div>
            </div>
            <button
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(`${window.location.origin}/users/${authUser?.discord_id}`);
                  toast.success(t("profile.copy_link"));
                } catch { toast.error(t("profile.copy_fail")); }
              }}
              className="h-9 rounded-lg bg-[#1c1d25] hover:bg-[#22242e] text-[12px] font-bold text-[#c9ccd8] flex items-center justify-center gap-2 px-3 transition-colors"
              title={`${window.location.origin}/users/${authUser?.discord_id}`}
              data-testid="profile-copy-link"
            >
              <LinkIcon size={13} /> <span className="truncate">/users/{authUser?.discord_id}</span>
            </button>
            <RobloxLinkCard />
          </div>

          <Stat title={t("profile.balance")} icon={CircleDollarSignIcon} testId="profile-balance-block">
            <div className="text-[28px] font-black flex items-center gap-2 leading-none" data-testid="profile-balance">
              {formatMoney(data?.user?.balance ?? authUser?.balance)} <RobuxIcon size={20} />
            </div>
            <div className="flex items-center justify-between text-[12px] rounded-md bg-[#0f1015] px-2.5 py-1.5" data-testid="profile-inventory-value-block">
              <span className="text-[#8e91a3] flex items-center gap-1.5"><BoxesIcon size={13} className="text-[#ffb000]" /> {t("profile.inventory")} · {skins.length} {t("common.items_unit")}</span>
              <span className="font-bold flex items-center gap-1 tabular-nums" data-testid="profile-inventory-value">{formatMoney(invTotal)} <RobuxIcon size={10} /></span>
            </div>
            <PromoInput compact />
            <button onClick={() => setTopUpOpen(true)} className="h-10 rounded-lg bg-[#ffb000] hover:bg-[#ffc233] text-black font-bold text-[13px] flex items-center justify-center gap-2 transition-colors" data-testid="profile-topup-button">
              <WalletIcon size={15} /> {t("profile.topup")}
            </button>
          </Stat>

          <div className="grid grid-rows-[1fr_auto] gap-3">
            <Stat title={t("profile.best")} icon={SparklesIcon} testId="profile-best-drop">
              {data?.best_drop ? (
                <div className="flex items-center gap-3" style={{ "--rarity": rarityColor(data.best_drop.item_rarity) }}>
                  <img src={data.best_drop.item_image} alt="" className="w-14 h-14 object-contain" />
                  <div className="min-w-0">
                    <div className="text-[10px] text-[#7d8194]">{data.best_drop.item_type}</div>
                    <div className="font-bold text-[13px] truncate">{data.best_drop.item_name}</div>
                    <div className="text-[12px] font-bold text-[#ffb000] flex items-center gap-1">{formatMoney(data.best_drop.item_price)} <RobuxIcon size={10} /></div>
                  </div>
                </div>
              ) : (
                <div className="text-[12px] text-[#5f6377]">{t("profile.best_empty")}</div>
              )}
            </Stat>
            <div className="grid grid-cols-2 gap-3">
              <Stat title={t("profile.withdrawn")} icon={SendIcon} testId="profile-withdrawn">
                <div className="text-[12px] text-[#8e91a3]">{data?.stats?.withdrawn_count ?? 0} {t("profile.withdrawn_items")}</div>
                <div className="font-bold flex items-center gap-1">{formatMoney(data?.stats?.withdrawn_sum)} <RobuxIcon size={11} /></div>
              </Stat>
              <Stat title={t("profile.upgrades")} icon={Logo} testId="profile-upgrades">
                <div className="text-[22px] font-black leading-none">{data?.stats?.upgrades ?? 0}</div>
                <div className="text-[11px] text-[#8e91a3]">{t("profile.wins")} {data?.stats?.wins ?? 0}</div>
              </Stat>
            </div>
          </div>
        </div>

        <div className="blox-panel fade-up" style={{ animationDelay: "80ms" }}>
          <div className="px-3 py-2.5 flex flex-wrap items-center gap-2 border-b border-[#15161b]">
            <div className="flex flex-wrap items-center gap-1 rounded-lg bg-[#0f1015] p-1">
              {[
                ["inventory", BoxesIcon, t("profile.tab_inventory")],
                ["items", HistoryIcon, t("profile.tab_items")],
                ["games", ZapIcon, t("profile.tab_games")],
                ["payments", PayIcon, t("profile.tab_payments")],
              ].map(([k, Icon, label]) => (
                <button key={k} onClick={() => setTab(k)} className={`h-8 px-3 rounded-md text-[12px] font-bold flex items-center gap-1.5 transition-colors ${tab === k ? "bg-[#ffb000] text-black" : "text-[#8e91a3] hover:text-white"}`} data-testid={`profile-tab-${k}`}>
                  <Icon size={13} /> {label}
                </button>
              ))}
            </div>
            {tab === "inventory" && (
              <div className="ml-auto flex items-center gap-3">
                <span className="text-[12px] text-[#8e91a3] hidden sm:flex items-center gap-1.5" data-testid="inventory-total-label">
                  {t("profile.inventory_total")} <span className="font-bold text-white flex items-center gap-1 tabular-nums">{formatMoney(invTotal)} <RobuxIcon size={10} /></span>
                </span>
                <button onClick={() => sell(skins.map((s) => s.uid))} disabled={busy || skins.length === 0} className="btn-sell h-8 px-3" data-testid="sell-all-button">
                  {t("profile.sell_all")} {formatMoney(invTotal)} <RobuxIcon size={9} />
                </button>
              </div>
            )}
          </div>

          <div className="p-3 min-h-[220px]">
            {tab === "inventory" &&
              (skins.length ? (
                <>
                  <div className="text-[11px] text-[#5f6377] mb-2" data-testid="inventory-hint">{t("profile.inventory_hint")}</div>
                  <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-8 gap-2" data-testid="profile-inventory">
                    {skins.map((s) => (
                      <InventoryCard
                        key={s.uid}
                        t={t}
                        item={s}
                        active={active === s.uid}
                        busy={busy}
                        onToggle={() => setActive((p) => (p === s.uid ? null : s.uid))}
                        onSell={() => sell([s.uid])}
                        onWithdraw={() => withdraw([s.uid])}
                      />
                    ))}
                  </div>
                </>
              ) : (
                <div className="h-[200px] flex items-center justify-center text-[13px] text-[#5f6377]" data-testid="profile-inventory-empty">{t("profile.inventory_empty")}</div>
              ))}

            {tab === "items" && (
              <div className="space-y-1.5" data-testid="profile-item-history">
                {(data?.item_history || []).length === 0 && <div className="h-[200px] flex items-center justify-center text-[13px] text-[#5f6377]">{t("profile.history_empty")}</div>}
                {(data?.item_history || []).map((h) => (
                  <div key={h.id} className="h-12 px-3 rounded-lg bg-[#0f1015] flex items-center gap-3 text-[12px]" style={{ boxShadow: `inset 3px 0 0 ${rarityColor(h.item?.rarity)}` }}>
                    {h.item?.image && <img src={h.item.image} alt="" className="w-9 h-9 object-contain" />}
                    <div className="min-w-0 flex-1"><span className="font-bold">{h.item?.name}</span> <span className="text-[#7d8194]">{h.item?.type}</span></div>
                    <span className={`font-bold ${h.kind === "won" ? "text-[#2ecc71]" : h.kind === "sold" ? "text-[#ffb000]" : "text-[#00a2ff]"}`}>{KIND_KEYS[h.kind] ? t(KIND_KEYS[h.kind]) : h.kind}</span>
                    <span className="font-bold flex items-center gap-1 w-24 justify-end">{formatMoney(h.price)} <RobuxIcon size={10} /></span>
                    <span className="text-[#5f6377] w-24 text-right">{fmtDate(h.created_at)}</span>
                  </div>
                ))}
              </div>
            )}

            {tab === "payments" && (
              <div className="space-y-1.5" data-testid="profile-payments">
                {deposits.length === 0 && <div className="h-[200px] flex items-center justify-center text-[13px] text-[#5f6377]">{t("profile.payments_empty")}</div>}
                {deposits.map((d) => (
                  <div key={d.id} className="min-h-12 px-3 py-2 rounded-lg bg-[#0f1015] flex flex-wrap items-center gap-3 text-[12px]" data-testid="profile-payment-item">
                    <span className="flex-1 min-w-0 truncate text-[#b4b7c7]">{d.description}{d.expected_rap > 0 ? <span className="text-[#8e91a3]"> · {formatMoney(d.expected_rap)} RAP{d.receiver_nick ? ` → ${d.receiver_nick}` : ""}</span> : null}</span>
                    <DepositStatus status={d.status} />
                    <span className="text-[#5f6377] w-24 text-right">{fmtDate(d.created_at)}</span>
                    <DepositReceipt deposit={d} compact testId={`profile-deposit-receipt-${d.id}`} />
                  </div>
                ))}
              </div>
            )}

            {tab === "games" && (
              <div className="space-y-1.5" data-testid="profile-games-history">
                {(data?.games || []).length === 0 && <div className="h-[200px] flex items-center justify-center text-[13px] text-[#5f6377]">{t("profile.games_empty")}</div>}
                {(data?.games || []).map((g) => (
                  <div key={g.id} className="h-12 px-3 rounded-lg bg-[#0f1015] flex items-center gap-3 text-[12px]">
                    <span className={`w-16 font-bold ${g.win ? "text-[#2ecc71]" : "text-[#ff5c5c]"}`}>{g.win ? t("profile.win") : t("profile.loss")}</span>
                    <span className="text-[#8e91a3] w-14">{(Number(g.display_chance ?? g.chance) * 100).toFixed(1)}%</span>
                    {Number(g.cashback) > 0 && <span className="text-[#2ecc71] text-[11px] font-bold whitespace-nowrap">{t("profile.cashback")} +{Number(g.cashback)}</span>}
                    <span className="flex-1 min-w-0 truncate"><span className="text-[#7d8194]">{t("profile.target")}</span> <span className="font-bold">{g.target?.name}</span></span>
                    <span className="font-bold flex items-center gap-1 w-28 justify-end">{formatMoney(Number(g.bet_amount) + Number(g.items_total || 0))} <RobuxIcon size={10} /></span>
                    <span className="text-[#5f6377] w-24 text-right">{fmtDate(g.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      <TopUpModal open={topUpOpen} onOpenChange={setTopUpOpen} />
    </div>
  );
}
