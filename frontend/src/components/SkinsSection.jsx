import React, { useEffect, useState } from "react";
import { Boxes, Store } from "lucide-react";
import { RobuxIcon } from "./Logo";
import AnimButton from "./AnimButton";
import DiscordButton from "./DiscordButton";
import SkinShowcase from "./SkinShowcase";
import SkinPagination from "./SkinPagination";
import { WalletIcon } from "./icons/wallet";
import { formatMoney, inventoryTotal } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../hooks/useAuth";
import { playTick } from "../lib/sound";
import { SkinCard, SkinGrid, PanelHeader, getPageSize } from "./skins/SkinGrid";
import SkinCatalog from "./skins/SkinCatalog";
import SkinShop from "./skins/SkinShop";
export { SkinCard } from "./skins/SkinGrid";

export const InventoryTabs = ({ value, onChange }) => {
  const { t } = useLang();
  return <div className="flex shrink-0 items-center gap-1 rounded-lg bg-[#0f1015] p-1" role="tablist" aria-label={t("store.sections")}>
    {[["mine", Boxes, t("skins.mine")], ["store", Store, t("store.title")]].map(([key, Icon, label]) => (
      <button key={key} type="button" role="tab" aria-selected={value === key} aria-label={label} title={label} onClick={() => onChange(key)} className={`h-7 w-7 rounded-md flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ffd36b] ${value === key ? "bg-[#ffb000] text-black shadow-sm" : "text-[#8e91a3] hover:bg-white/5 hover:text-white"}`} data-testid={`inventory-tab-${key}`}><Icon size={16} aria-hidden="true" /></button>
    ))}
  </div>;
};

const MobileTabs = ({ t, value, onChange }) => (
  <div className="lg:hidden blox-panel p-1 grid grid-cols-2 gap-1" data-testid="mobile-skins-tabs">
    {[
      { key: "mine", label: t("skins.mine") },
      { key: "shop", label: t("skins.shop") },
    ].map((tab) => (
      <button
        key={tab.key}
        type="button"
        onClick={() => onChange(tab.key)}
        className={`h-10 rounded-lg text-[13px] font-bold transition-colors ${value === tab.key ? "bg-[#00a2ff] text-white shadow-[0_4px_14px_rgba(0,162,255,0.35)]" : "text-[#8e91a3] hover:text-white"}`}
        data-testid={`mobile-tab-${tab.key}`}
      >
        {tab.label}
      </button>
    ))}
  </div>
);

const GuestInventory = ({ t, onLogin }) => (
  <div className="relative p-2 pt-0" data-testid="guest-inventory">
    <div className="text-center pt-6 pb-4">
      <div className="font-bold text-[18px]" data-testid="guest-title">
        {t("skins.guest_title")}
      </div>
      <div className="text-[12px] text-[#7d8194] mt-1">{t("skins.guest_text")}</div>
      <DiscordButton className="mt-4" onClick={onLogin} data-testid="inventory-login-button" />
    </div>
    <SkinShowcase size="md" className="mt-2" />
  </div>
);

const UserInventory = ({ t, skins, pageSize, onTopUp, selectedUids, onToggle, disabled }) => {
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(skins.length / pageSize));
  const currentPage = Math.min(page, pages);
  useEffect(() => { setPage((current) => Math.min(current, pages)); }, [pages]);
  useEffect(() => { setPage(1); }, [pageSize]);
  const visibleSkins = skins.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  return (
    <div className="flex flex-1 flex-col" data-testid="user-inventory">
      <SkinGrid pageSize={pageSize} testId="inventory-grid" overlay={skins.length === 0 && (
          <div className="bg-[#0d0e12] rounded-xl px-7 py-5 text-center shadow-[0_10px_40px_rgba(0,0,0,0.6)]" data-testid="topup-skins-card">
            <div className="font-bold text-[14px] mb-3">{t("skins.topup_skins")}</div>
            <AnimButton
              icon={WalletIcon}
              size={14}
              className="h-9 px-5 rounded-lg border border-[#00a2ff] text-[#00a2ff] font-bold text-[13px] flex items-center gap-2 mx-auto hover:bg-[#00a2ff]/10 transition-colors"
              onClick={onTopUp}
              data-testid="topup-skins-button"
            >
              {t("skins.topup")}
            </AnimButton>
          </div>
      )}>
        {visibleSkins.map((s, i) => (
          <SkinCard key={s.uid || `${s.id || s.name}-${i}`} item={s} disabled={disabled} testId={`bet-card-${s.uid}`} selected={selectedUids.includes(s.uid)} onClick={() => onToggle(s)} />
        ))}
      </SkinGrid>
      <SkinPagination page={currentPage} pages={pages} onChange={setPage} label={t("skins.mine_pages")} testId="inventory-pagination" />
    </div>
  );
};

export default function SkinsSection({ onTopUp, user, target, onSelectTarget, onPurchased, betSkins = [], onToggleBetSkin, sound, disabled }) {
  const { authUser, openAuth } = useAuth();
  const { t } = useLang();
  const [pageSize, setPageSize] = useState(getPageSize);
  const [mobileTab, setMobileTab] = useState("mine");
  const [leftMode, setLeftMode] = useState("mine");
  useEffect(() => {
    const resize = () => setPageSize(getPageSize());
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  return (
    <section className="grid grid-cols-1 lg:grid-cols-2 gap-3 lg:gap-6 mt-4 sm:mt-5 fade-up" data-testid="skins-section">
      <MobileTabs t={t} value={mobileTab} onChange={setMobileTab} />
      <div className={`blox-panel flex-col overflow-hidden ${mobileTab === "mine" ? "flex" : "hidden lg:flex"}`} data-testid="my-skins-panel">
        <div className={leftMode === "mine" ? "flex flex-1 flex-col" : "hidden"}>
          <PanelHeader title={<InventoryTabs value="mine" onChange={setLeftMode} />}>
            {authUser && <div className="ml-auto min-w-0 flex flex-wrap items-center gap-x-2 gap-y-0.5 min-h-8 px-2 py-1 rounded-md bg-[#0f1015]" title={t("skins.inventory_value_hint")} data-testid="inventory-value-chip">
              <span className="text-[11px] text-[#8e91a3] whitespace-nowrap">{t("skins.inventory")} · {user?.skins?.length || 0}</span>
              <span className="text-[13px] font-bold text-[#ffb000] tabular-nums flex items-center gap-1" data-testid="inventory-value">{formatMoney(inventoryTotal(user?.skins))} <RobuxIcon size={10} /></span>
            </div>}
          </PanelHeader>
          {authUser ? <UserInventory key={user?.session_id || "inventory"} t={t} disabled={disabled} skins={user?.skins || []} pageSize={pageSize} onTopUp={onTopUp} selectedUids={betSkins.map((b) => b.uid)} onToggle={(skin) => { playTick(sound); onToggleBetSkin(skin); }} /> : <GuestInventory t={t} onLogin={openAuth} />}
        </div>
        <SkinShop key={authUser?.session_id || "guest"} active={leftMode === "store"} tabs={<InventoryTabs value="store" onChange={setLeftMode} />} pageSize={pageSize} user={user} disabled={disabled} onTopUp={onTopUp} onPurchased={(updated) => { onPurchased?.(updated); setLeftMode("mine"); }} />
      </div>
      <div className={`blox-panel flex-col overflow-hidden ${mobileTab === "shop" ? "flex" : "hidden lg:flex"}`} data-testid="shop-panel">
        <SkinCatalog pageSize={pageSize} title={t("skins.shop")} renderItem={(item) => <SkinCard key={item.id} item={item} disabled={disabled} testId={`shop-skin-${item.id}`} selected={target?.id === item.id} onClick={() => { playTick(sound); onSelectTarget(target?.id === item.id ? null : item); }} />} />
      </div>
    </section>
  );
}
