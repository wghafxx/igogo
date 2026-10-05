import { api } from "./api";

// Chance and multiplier are monotonic in price: the nearest eligible target
// is one of the two catalog neighbours of the ideal price, across all pages.
export async function findQuickTarget(stake, chance, config, { signal, multiplier = false } = {}) {
  const stakeCents = Math.round(stake * 100);
  const cap = Math.min(config.max_chance, config.max_bet_ratio ?? config.max_chance);
  const minPrice = Math.ceil(stakeCents / cap - 1e-8) / 100;
  const maxPrice = Math.floor(stakeCents * config.rtp / config.min_chance + 1e-8) / 100;
  const ideal = stake / chance;
  const bounds = [
    { min_price: minPrice, max_price: Math.min(ideal, maxPrice), sort: "price_desc" },
    { min_price: Math.max(ideal, minPrice), max_price: maxPrice, sort: "price_asc" },
  ];
  const pages = await Promise.all(bounds.filter((b) => b.min_price <= b.max_price)
    .map((params) => api.shop({ ...params, page: 1, limit: 1 }, { signal })));
  const candidates = pages.flatMap((p) => p.items || []).filter((item) => {
    const price = Number(item.price);
    return item.id && price >= minPrice && price <= maxPrice;
  });
  const distance = (item) => multiplier ? Math.abs(Number(item.price) / stake - 1 / chance) : Math.abs(stake / Number(item.price) - chance);
  candidates.sort((a, b) => distance(a) - distance(b) || Number(b.price) - Number(a.price) || String(a.id).localeCompare(String(b.id)));
  return candidates[0] || null;
}
