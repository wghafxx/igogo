import React, { useEffect, useRef, useState } from "react";
import { TrendingDownIcon } from "./icons/trending-down";
import { TrendingUpIcon } from "./icons/trending-up";
import { Logo, RobuxIcon } from "./Logo";
import AnimButton from "./AnimButton";
import DiscordButton from "./DiscordButton";
import SkinShowcase from "./SkinShowcase";
import { SearchIcon } from "./icons/search";
import { WalletIcon } from "./icons/wallet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { api, formatMoney, inventoryTotal } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useAuth } from "../hooks/useAuth";
import { rarityColor, rarityLabel } from "../lib/rarity";
import { playTick } from "../lib/sound";

const EmptySlot = () => <div className="skin-slot" aria-hidden="true" />;

export const SkinCard = ({ item, onClick, selected, disabled, testId }) => {
  const color = rarityColor(item.rarity);
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      disabled={onClick ? disabled : undefined}
      aria-pressed={onClick ? Boolean(selected) : undefined}
      aria-label={`${item.type} ${item.name}, ${formatMoney(item.price)} RAP`}
      className={`skin-slot skin-card w-full ${onClick ? "cursor-pointer disabled:cursor-wait" : ""} ${selected ? "selected" : ""}`}
      style={{ "--rarity": color }}
      onClick={onClick}
      data-testid={testId || `skin-${item.uid || item.id}`}
      data-rarity={item.rarity || "stock"}
    >
      <div className="absolute top-1.5 left-1.5 right-1.5 flex items-center justify-between text-[10px]">
        <span className="flex items-center gap-0.5 font-bold text-[#ffb000]">
          {formatMoney(item.price)} <RobuxIcon size={9} />
        </span>
        <span className="rarity-dot" title={rarityLabel(item.rarity)} />
      </div>
      {item.image && <img src={item.image} alt={item.name} className="absolute inset-0 m-auto w-3/5 h-3/5 object-contain drop-shadow-[0_6px_10px_rgba(0,0,0,0.6)]" />}
      <div className="absolute inset-x-1 bottom-1.5 text-center">
        <div className="text-[8px] text-[#7d8194] truncate">{item.type}</div>
        <div className="text-[10px] font-bold truncate">{item.name}</div>
      </div>
    </Tag>
  );
};

const PanelHeader = ({ title, children }) => (
  <div className="min-h-[52px] px-3 py-2 flex flex-wrap items-center gap-2 sm:gap-3">
    <div className="w-8 h-8 rounded-md bg-[#00a2ff] flex items-center justify-center shrink-0">
      <Logo size={16} className="[&_path]:fill-white" />
    </div>
    <span className="font-bold text-[14px] whitespace-nowrap">{title}</span>
    {children}
  </div>
);

const GRID = "grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-2";

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

const PriceInput = ({ value, onChange, placeholder, testId, ariaLabel }) => (
  <div className="relative">
    <RobuxIcon size={11} className="absolute left-2 top-1/2 -translate-y-1/2" />
    <input
      value={value}
      onChange={(e) => {
        const next = e.target.value.replace(",", ".");
        if (/^\d{0,9}(\.\d{0,2})?$/.test(next)) onChange(next);
      }}
      inputMode="decimal"
      aria-label={ariaLabel}
      placeholder={placeholder}
      className="h-8 w-[62px] pl-6 pr-2 rounded-md bg-[#0f1015] text-[12px] text-white placeholder:text-[#5f6377] outline-none focus:ring-1 focus:ring-[#00a2ff]"
      data-testid={testId}
    />
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

const UserInventory = ({ t, skins, onTopUp, selectedUids, onToggle, disabled }) => (
  <div className="relative p-2 pt-0" data-testid="user-inventory">
    {skins.length > 0 ? (
      <div className={GRID}>
        {skins.map((s, i) => (
          <SkinCard key={s.uid || `${s.id || s.name}-${i}`} item={s} disabled={disabled} testId={`bet-card-${s.uid}`} selected={selectedUids.includes(s.uid)} onClick={() => onToggle(s)} />
        ))}
      </div>
    ) : (
      <>
        <div className={`${GRID} blur-[3px] opacity-50 pointer-events-none select-none`}>
          {Array.from({ length: 15 }).map((_, i) => (
            <EmptySlot key={i} />
          ))}
        </div>
        <div className="absolute inset-0 flex items-center justify-center">
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
        </div>
      </>
    )}
  </div>
);

export default function SkinsSection({ onTopUp, user, target, onSelectTarget, betSkins = [], onToggleBetSkin, sound, disabled }) {
  const { authUser, openAuth } = useAuth();
  const { t } = useLang();
  const [sort, setSort] = useState("price_desc");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  const [mobileTab, setMobileTab] = useState("mine");
  const searchRef = useRef(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    const params = { sort };
    if (minPrice !== "" && Number.isFinite(Number(minPrice))) params.min_price = Number(minPrice);
    if (maxPrice !== "" && Number.isFinite(Number(maxPrice))) params.max_price = Number(maxPrice);
    if (query) params.q = query;
    const timer = setTimeout(() => api
      .shop(params)
      .then((d) => alive && setItems(d.items || []))
      .catch(() => { if (alive) { setItems([]); setError(t("skins.catalog_fail")); } })
      .finally(() => { if (alive) setLoading(false); }), 200);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [sort, minPrice, maxPrice, query, retry]);

  const openSearch = () => {
    setSearchOpen(true);
    setTimeout(() => searchRef.current?.focus(), 50);
  };
  const closeSearch = () => {
    if (!query) setSearchOpen(false);
  };

  const sorted = [...items].sort((a, b) => (sort === "price_asc" ? a.price - b.price : b.price - a.price));

  return (
    <section className="grid grid-cols-1 lg:grid-cols-2 gap-3 lg:gap-6 mt-4 sm:mt-5 fade-up" data-testid="skins-section">
      <MobileTabs t={t} value={mobileTab} onChange={setMobileTab} />
      <div className={`blox-panel overflow-hidden ${mobileTab === "mine" ? "" : "hidden lg:block"}`} data-testid="my-skins-panel">
        <PanelHeader title={t("skins.mine")}>
          {authUser && (
            <div className="ml-auto flex items-center gap-2 h-8 px-3 rounded-md bg-[#0f1015]" title={t("skins.inventory_value_hint")} data-testid="inventory-value-chip">
              <span className="text-[11px] text-[#8e91a3] whitespace-nowrap">{t("skins.inventory")} · {user?.skins?.length || 0}</span>
              <span className="text-[13px] font-bold text-[#ffb000] tabular-nums flex items-center gap-1" data-testid="inventory-value">
                {formatMoney(inventoryTotal(user?.skins))} <RobuxIcon size={10} />
              </span>
            </div>
          )}
        </PanelHeader>
        {authUser ? (
          <UserInventory
            t={t}
            disabled={disabled}
            skins={user?.skins || []}
            onTopUp={onTopUp}
            selectedUids={betSkins.map((b) => b.uid)}
            onToggle={(sk) => {
              playTick(sound);
              onToggleBetSkin(sk);
            }}
          />
        ) : (
          <GuestInventory t={t} onLogin={openAuth} />
        )}
      </div>

      <div className={`blox-panel overflow-hidden ${mobileTab === "shop" ? "" : "hidden lg:block"}`} data-testid="shop-panel">
        <PanelHeader title={t("skins.shop")}>
          <div className="w-full sm:w-auto sm:ml-auto flex items-center gap-2 min-w-0">
            <Select value={sort} onValueChange={setSort}>
              <SelectTrigger className="h-8 w-[100px] shrink-0 bg-[#0f1015] border-0 text-[12px] text-white focus:ring-0" data-testid="sort-select">
                <div className="flex items-center gap-1.5">
                  {sort === "price_desc" ? <TrendingDownIcon size={13} className="text-[#7d8194]" /> : <TrendingUpIcon size={13} className="text-[#7d8194]" />}
                  <SelectValue />
                </div>
              </SelectTrigger>
              <SelectContent className="bg-[#1c1d25] border-0 text-white">
                <SelectItem value="price_desc" data-testid="sort-desc" className="text-[12px] focus:bg-[#262833] focus:text-white">Цена ↓</SelectItem>
                <SelectItem value="price_asc" data-testid="sort-asc" className="text-[12px] focus:bg-[#262833] focus:text-white">Цена ↑</SelectItem>
              </SelectContent>
            </Select>

            <div
              className={`flex items-center gap-2 overflow-hidden transition-[max-width,opacity] duration-300 ease-out ${searchOpen ? "max-w-0 opacity-0" : "max-w-[140px] opacity-100"}`}
              data-testid="price-filters"
            >
              <PriceInput value={minPrice} onChange={setMinPrice} placeholder={t("skins.from")} ariaLabel={t("skins.min_price")} testId="min-price-input" />
              <PriceInput value={maxPrice} onChange={setMaxPrice} placeholder={t("skins.to")} ariaLabel={t("skins.max_price")} testId="max-price-input" />
            </div>

            <div
              className={`h-8 flex items-center rounded-md bg-[#0f1015] transition-[width] duration-300 ease-out overflow-hidden ${searchOpen ? "w-[172px]" : "w-8"}`}
              data-testid="search-box"
            >
              <AnimButton
                icon={SearchIcon}
                size={14}
                className="w-8 h-8 shrink-0 flex items-center justify-center text-[#7d8194] hover:text-white transition-colors"
                onClick={openSearch}
                data-testid="search-toggle"
              />
              <input
                ref={searchRef}
                value={query}
                maxLength={100}
                aria-label={t("skins.search")}
                onChange={(e) => setQuery(e.target.value)}
                onBlur={closeSearch}
                placeholder={t("skins.search")}
                className={`h-8 bg-transparent text-[12px] text-white placeholder:text-[#5f6377] outline-none pr-2 transition-opacity duration-200 ${searchOpen ? "w-full opacity-100" : "w-0 opacity-0"}`}
                data-testid="search-input"
              />
            </div>
          </div>
        </PanelHeader>
        <div className={`p-2 pt-0 ${GRID}`} data-testid="shop-grid">
          {loading ? <div className="col-span-full py-10 text-center text-sm text-[#8e91a3]" data-testid="shop-loading">{t("skins.loading")}</div> : error ? <div className="col-span-full py-10 text-center text-sm" data-testid="shop-error">{error}<button className="block mx-auto mt-3 text-[#00a2ff]" data-testid="shop-retry" onClick={() => setRetry((v) => v + 1)}>{t("skins.retry")}</button></div> : sorted.length > 0
            ? sorted.map((it) => (
                <SkinCard
                  key={it.id || it.name}
                  item={it}
                  disabled={disabled}
                  testId={`shop-skin-${it.id}`}
                  selected={target?.id === it.id}
                  onClick={() => {
                    playTick(sound);
                    onSelectTarget(target?.id === it.id ? null : it);
                  }}
                />
              ))
            : <div className="col-span-full py-10 text-center text-sm text-[#8e91a3]" data-testid="shop-empty">{t("skins.empty")}</div>}
        </div>
      </div>
    </section>
  );
}
