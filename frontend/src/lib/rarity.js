const IMG = "https://bloxstrike.net/items/bloxstrike-live";

export const RARITIES = {
  stock: { label: "Stock", color: "#b8bcc9" },
  blue: { label: "Blue", color: "#4b9dff" },
  purple: { label: "Purple", color: "#a35cff" },
  pink: { label: "Pink", color: "#ff4fd8" },
  red: { label: "Red", color: "#ff3b3b" },
  gold: { label: "Gold", color: "#ffc634" },
  special: { label: "Special", color: "#ffe27a" },
  forbidden: { label: "Forbidden", color: "#ff7a1a" },
};

export const RARITY_ORDER = ["stock", "blue", "purple", "pink", "red", "gold", "special", "forbidden"];

export const rarityColor = (key) => (RARITIES[key] || RARITIES.stock).color;
export const rarityLabel = (key) => (RARITIES[key] || RARITIES.stock).label;

// Reel animation: start item -> unnamed items fly through -> final item
export const REEL_START = { id: "case", name: "Finishline Case", type: "Case", rarity: "stock", image: `${IMG}/114958333422119.png` };
export const REEL_FINAL = { id: "karambit", name: "Tiger Stripes", type: "Karambit", rarity: "special", image: `${IMG}/95211024718206.png` };
export const REEL_FLY = [
  { id: "s1", image: `${IMG}/73060066712564.png` },
  { id: "s2", image: `${IMG}/84048948308515.png` },
  { id: "s3", image: `${IMG}/133957542310311.png` },
];
