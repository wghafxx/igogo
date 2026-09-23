import React, { useCallback, useEffect, useMemo, useState } from "react";
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
import { preventGameDrag } from "../lib/game-interactions";
import { SkinCard, SkinGrid, PanelHeader, getPageSize } from "./skins/SkinGrid";
import SkinCatalog from "./skins/SkinCatalog";
import SkinShop from "./skins/SkinShop";
export { SkinCard } from "./skins/SkinGrid";

export const InventoryTabs = ({ value, onChange }) => {
  const { t } = useLang();
  return <div className="flex shrink-0 items-center gap-1 rounded-lg bg-[#0f1015] p-1" role="tablist" aria-label={t("store.sections")}>
    {[["mine", Boxes, t("skins.mine")], ["store", Store, t("store.title")]].map(([key, Icon, label]) => (
      <button key={key} type="button" role="tab" aria-selected={value === key} aria-label={label} title={label} onClick={() => onChange(key)} className={`h-7 w-7 rounded-md flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white ${value === key ? "control-solid shadow-sm" : "text-[#999999] hover:bg-white/5 hover:text-white"}`} data-testid={`inventory-tab-${key}`}><Icon size={16} aria-hidden="true" /></button>
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
        className={`h-10 rounded-lg text-[13px] font-bold transition-colors ${value === tab.key ? "control-solid shadow-sm" : "text-[#999999] hover:text-white"}`}
        data-testid={`mobile-tab-${tab.key}`}
      >
        {tab.label}
      </button>
    ))}
  </div>
);

const GuestInventory = React.memo(({ t, onLogin }) => (
  <div className="relative p-2 pt-0" data-testid="guest-inventory">
    <div className="text-center pt-6 pb-4">
      <div className="font-bold text-[18px]" data-testid="guest-title">
        {t("skins.guest_title")}
      </div>
      <div className="text-[12px] text-[#7d8194] mt-1">{t("skins.guest_text")}</div>
      <DiscordButton className="mt-4 min-w-[236px]" onClick={onLogin} data-testid="inventory-login-button" />
    </div>
    <SkinShowcase size="md" className="mt-2" />
  </div>
));

const UserInventory = React.memo(({ t, skins, pageSize, onTopUp, selectedUids, onToggle, disabled }) => {
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
              className="h-9 px-5 rounded-lg border border-white/70 text-white font-bold text-[13px] flex items-center gap-2 mx-auto hover:bg-white/10 transition-colors"
              onClick={onTopUp}
              data-testid="topup-skins-button"
            >
              {t("skins.topup")}
            </AnimButton>
          </div>
      )}>
        {visibleSkins.map((s, i) => (
          <SkinCard key={s.uid || `${s.id || s.name}-${i}`} item={s} disabled={disabled} testId={`bet-card-${s.uid}`} selected={selectedUids.includes(s.uid)} onSelect={onToggle} />
        ))}
      </SkinGrid>
      <SkinPagination page={currentPage} pages={pages} onChange={setPage} label={t("skins.mine_pages")} testId="inventory-pagination" />
    </div>
  );
});

export default function SkinsSection({ onTopUp, user, target, onSelectTarget, onPurchased, betSkins = [], onToggleBetSkin, sound, disabled }) {
  const { authUser, openAuth } = useAuth();
  const { t } = useLang();
  const [pageSize, setPageSize] = useState(getPageSize);
  const [mobileTab, setMobileTab] = useState("mine");
  const [leftMode, setLeftMode] = useState("mine");
  const selectedUids = useMemo(() => betSkins.map((skin) => skin.uid), [betSkins]);
  const selectOwned = useCallback((skin) => {
    playTick(sound);
    onToggleBetSkin(skin);
  }, [sound, onToggleBetSkin]);
  const selectTarget = useCallback((item) => {
    playTick(sound);
    // Functional update preserves every toggle, even multiple clicks in one frame.
    onSelectTarget((current) => current?.id === item.id ? null : item);
  }, [sound, onSelectTarget]);
  useEffect(() => {
    const resize = () => setPageSize(getPageSize());
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  return (
    <section className="game-interaction-surface grid grid-cols-1 lg:grid-cols-2 gap-3 lg:gap-6 mt-4 sm:mt-5 animate__animated animate__fadeInUp animate__delay-short" onDragStartCapture={preventGameDrag} data-testid="skins-section">
      <MobileTabs t={t} value={mobileTab} onChange={setMobileTab} />
      <div className={`blox-panel flex-col overflow-hidden ${mobileTab === "mine" ? "flex" : "hidden lg:flex"}`} data-testid="my-skins-panel">
        <div className={leftMode === "mine" ? "flex flex-1 flex-col" : "hidden"}>
          <PanelHeader title={<>{leftMode === "mine" && <InventoryTabs value="mine" onChange={setLeftMode} />}<span>{t("skins.mine")}</span></>}>
            {authUser && <div className="ml-auto min-w-0 flex items-center gap-2 h-9 px-2 rounded-lg bg-[#0f1015] whitespace-nowrap" title={t("skins.inventory_value_hint")} data-testid="inventory-value-chip">
              <span className="inventory-caption text-[11px] text-[#8e91a3]">{t("skins.inventory")} · {user?.skins?.length || 0}</span>
              <span className="min-w-0 text-[13px] font-bold text-white tabular-nums flex items-center gap-1" data-testid="inventory-value"><span className="truncate">{formatMoney(inventoryTotal(user?.skins))}</span> <RobuxIcon size={10} className="shrink-0" /></span>
            </div>}
          </PanelHeader>
          {authUser ? <UserInventory key={user?.session_id || "inventory"} t={t} disabled={disabled} skins={user?.skins || []} pageSize={pageSize} onTopUp={onTopUp} selectedUids={selectedUids} onToggle={selectOwned} /> : <GuestInventory t={t} onLogin={openAuth} />}
        </div>
        <SkinShop key={authUser?.session_id || "guest"} active={leftMode === "store"} tabs={leftMode === "store" ? <InventoryTabs value="store" onChange={setLeftMode} /> : null} pageSize={pageSize} user={user} disabled={disabled} onTopUp={onTopUp} onPurchased={(updated) => { onPurchased?.(updated); setLeftMode("mine"); }} />
      </div>
      <div className={`blox-panel flex-col overflow-hidden ${mobileTab === "shop" ? "flex" : "hidden lg:flex"}`} data-testid="shop-panel">
        <SkinCatalog pageSize={pageSize} title={t("skins.shop")} renderItem={(item) => <SkinCard key={item.id} item={item} disabled={disabled} testId={`shop-skin-${item.id}`} selected={target?.id === item.id} onSelect={selectTarget} />} />
      </div>
    </section>
  );
}
