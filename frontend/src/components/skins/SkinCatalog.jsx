import React, { useEffect, useRef, useState } from "react";
import { TrendingDownIcon } from "../icons/trending-down";
import { TrendingUpIcon } from "../icons/trending-up";
import { SearchIcon } from "../icons/search";
import { RobuxIcon } from "../Logo";
import AnimButton from "../AnimButton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import SkinPagination from "../SkinPagination";
import { api } from "../../lib/api";
import { useLang } from "../../lib/i18n";
import { PanelHeader, SkinGrid } from "./SkinGrid";

const PriceInput = ({ value, onChange, placeholder, testId, ariaLabel }) => (
  <div className="relative min-w-0 flex-1">
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
      className="h-8 w-full min-w-0 pl-6 pr-1 rounded-md bg-[#0f1015] text-[12px] text-white placeholder:text-[#5f6377] outline-none focus:ring-1 focus:ring-[#00a2ff]"
      data-testid={testId}
    />
  </div>
);


export default function SkinCatalog({ pageSize, title, compact = false, renderItem, testPrefix = "" }) {
  const { t } = useLang();
  const [sort, setSort] = useState("price_desc");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [shopPage, setShopPage] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  const searchRef = useRef(null);

  useEffect(() => { setShopPage(1); }, [pageSize]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    const params = { sort, page: shopPage, limit: pageSize };
    if (minPrice !== "" && Number.isFinite(Number(minPrice))) params.min_price = Number(minPrice);
    if (maxPrice !== "" && Number.isFinite(Number(maxPrice))) params.max_price = Number(maxPrice);
    if (query) params.q = query;
    const timer = setTimeout(() => api
      .shop(params)
      .then((d) => {
        if (!alive) return;
        setItems(d.items || []);
        setTotalItems(d.total || 0);
        setShopPage(d.page || 1);
      })
      .catch(() => { if (alive) { setItems([]); setError(true); } })
      .finally(() => { if (alive) setLoading(false); }), 200);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [sort, minPrice, maxPrice, query, retry, shopPage, pageSize]);

  const changeFilter = (setter, value) => {
    setter(value);
    setShopPage(1);
  };

  const openSearch = () => {
    setSearchOpen(true);
    setTimeout(() => searchRef.current?.focus(), 50);
  };
  const closeSearch = () => {
    if (!query) setSearchOpen(false);
  };

  const shopPages = Math.max(1, Math.ceil(totalItems / pageSize));

  return (<>
        <PanelHeader title={title} compact={compact}>
          <div className="w-full flex items-center gap-2 min-w-0" data-testid={`${testPrefix}catalog-controls`}>
            <Select value={sort} onValueChange={(value) => changeFilter(setSort, value)}>
              <SelectTrigger className="h-8 w-[100px] shrink-0 bg-[#0f1015] border-0 text-[12px] text-white focus:ring-0" data-testid={`${testPrefix}sort-select`}>
                <div className="flex items-center gap-1.5">
                  {sort === "price_desc" ? <TrendingDownIcon size={13} className="text-[#7d8194]" /> : <TrendingUpIcon size={13} className="text-[#7d8194]" />}
                  <SelectValue />
                </div>
              </SelectTrigger>
              <SelectContent className="bg-[#1c1d25] border-0 text-white">
                <SelectItem value="price_desc" data-testid={`${testPrefix}sort-desc`} className="text-[12px] focus:bg-[#262833] focus:text-white">Цена ↓</SelectItem>
                <SelectItem value="price_asc" data-testid={`${testPrefix}sort-asc`} className="text-[12px] focus:bg-[#262833] focus:text-white">Цена ↑</SelectItem>
              </SelectContent>
            </Select>

            <div
              className={searchOpen ? "hidden" : "flex min-w-0 flex-1 items-center gap-2"}
              data-testid={`${testPrefix}price-filters`}
            >
              <PriceInput value={minPrice} onChange={(value) => changeFilter(setMinPrice, value)} placeholder={t("skins.from")} ariaLabel={t("skins.min_price")} testId={`${testPrefix}min-price-input`} />
              <PriceInput value={maxPrice} onChange={(value) => changeFilter(setMaxPrice, value)} placeholder={t("skins.to")} ariaLabel={t("skins.max_price")} testId={`${testPrefix}max-price-input`} />
            </div>

            <div
              className={`h-8 flex min-w-0 items-center rounded-md bg-[#0f1015] overflow-hidden ${searchOpen ? "flex-1" : "w-8 shrink-0"}`}
              data-testid={`${testPrefix}search-box`}
            >
              <AnimButton
                icon={SearchIcon}
                size={14}
                className="w-8 h-8 shrink-0 flex items-center justify-center text-[#7d8194] hover:text-white transition-colors"
                onClick={openSearch}
                aria-label={t("skins.search")}
                title={t("skins.search")}
                data-testid={`${testPrefix}search-toggle`}
              />
              <input
                ref={searchRef}
                value={query}
                maxLength={100}
                aria-label={t("skins.search")}
                onChange={(e) => changeFilter(setQuery, e.target.value)}
                onBlur={closeSearch}
                placeholder={t("skins.search")}
                className={`h-8 min-w-0 bg-transparent text-[12px] text-white placeholder:text-[#5f6377] outline-none pr-2 ${searchOpen ? "flex-1" : "hidden"}`}
                data-testid={`${testPrefix}search-input`}
              />
            </div>
          </div>
        </PanelHeader>
        <SkinGrid pageSize={pageSize} testId={`${testPrefix}shop-grid`} overlay={
          loading ? <div className="rounded-lg bg-[#0d0e12] p-4 text-sm text-[#8e91a3]" data-testid={`${testPrefix}shop-loading`}>{t("skins.loading")}</div>
            : error ? <div className="rounded-lg bg-[#0d0e12] p-4 text-sm" data-testid={`${testPrefix}shop-error`}>{t("skins.catalog_fail")}<button className="block mx-auto mt-3 text-[#00a2ff]" data-testid={`${testPrefix}shop-retry`} onClick={() => setRetry((v) => v + 1)}>{t("skins.retry")}</button></div>
            : items.length === 0 ? <div className="rounded-lg bg-[#0d0e12] p-4 text-sm text-[#8e91a3]" data-testid={`${testPrefix}shop-empty`}>{t("skins.empty")}</div> : null
        }>
          {!loading && !error && items.map(renderItem)}
        </SkinGrid>
        <SkinPagination page={shopPage} pages={shopPages} onChange={setShopPage} disabled={loading || Boolean(error)} label={t("skins.shop_pages")} testId={`${testPrefix}shop-pagination`} />
  </>);
}
