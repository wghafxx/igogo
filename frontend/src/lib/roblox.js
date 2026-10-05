export const validDisplayName = (value) => value.trim().length >= 3 && value.trim().length <= 20 && !/[\u0000-\u001f\u007f]/.test(value);
export const normalizeRobloxUsername = (value) => value.trim().replace(/^@/, "");
export const validRobloxUsername = (value) => /^[A-Za-z0-9_]{3,20}$/.test(normalizeRobloxUsername(value));
export const validRobloxLink = (value) => {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== "https:" || !["roblox.com", "www.roblox.com"].includes(url.hostname) || url.username || url.password || url.port) return false;
    return /^\/users\/[1-9]\d*\/profile\/?$/.test(url.pathname) ||
      (url.pathname === "/share" && /^[A-Za-z0-9]+$/.test(url.searchParams.get("code") || "") && url.searchParams.get("type") === "Profile");
  } catch { return false; }
};
export const hasRobloxProfile = (user) => Boolean(user && validDisplayName(user.roblox_display_name || "") && validRobloxUsername(user.roblox_nick || "") && validRobloxLink(user.roblox_link || ""));
