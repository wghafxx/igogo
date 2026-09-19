const REMOTE = /^https?:\/\/bloxstrike\.net\/items\/bloxstrike-live\/(\d+)\.png$/i;

// Catalog images are mirrored as small WebP files in /public/items (scripts/optimize_images.py).
export const skinImg = (url) => {
  if (typeof url !== "string") return url;
  const m = url.match(REMOTE);
  return m ? `/items/${m[1]}.webp` : url;
};
