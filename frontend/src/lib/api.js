import axios from "axios";
import { getLang } from "./i18n";
import { capturedReferral } from "./referral";
import { EVENTS, notifyNotificationsChanged } from "./events";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const TOKEN_KEY = "bloxgrade_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

export const http = axios.create({ baseURL: API, withCredentials: true, timeout: 20000 });
const normalizeError = (error) => {
  const detail = error.response?.data?.detail;
  const fallback = getLang() === "en" ? "Check your input" : "Проверьте введённые данные";
  if (Array.isArray(detail)) error.response.data.detail = detail.map((d) => d.msg || fallback).join(". ");
  else if (detail && typeof detail === "object") error.response.data.detail = fallback;
  return Promise.reject(error);
};
export const NOTIFICATIONS_CHANGED = EVENTS.notificationsChanged;
http.interceptors.response.use((response) => {
  if (response.config.method === "post" && /^\/(deposits(?:\/|$)|skins\/withdraw$|payments\/xrocket\/invoices(?:\/|$))/.test(response.config.url)) {
    notifyNotificationsChanged();
  }
  return response;
}, normalizeError);
http.interceptors.request.use((cfg) => {
  const t = getToken();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  cfg.headers["X-Session-Id"] = getSessionId();
  // Automatic support-chat replies follow the language chosen on the site.
  cfg.headers["X-Lang"] = getLang();
  return cfg;
});

export const getSessionId = () => {
  let id = localStorage.getItem("bloxgrade_session");
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem("bloxgrade_session", id);
  }
  return id;
};

export const discordLoginUrl = () => {
  const ref = capturedReferral();
  return `${API}/auth/discord/login${ref ? `?ref=${encodeURIComponent(ref)}` : ""}`;
};

export const api = {
  presence: (session_id) => http.post(`/presence`, { session_id }).then((r) => r.data),
  stats: () => http.get(`/stats`).then((r) => r.data),
  gameConfig: () => http.get(`/game-config`).then((r) => r.data),
  user: (session_id) => http.get(`/user/${session_id}`).then((r) => r.data),
  me: () => http.get(`/auth/me`).then((r) => r.data),
  logout: () => http.post(`/auth/logout`).then((r) => r.data),
  liveDrops: (limit = 30) => http.get(`/live-drops`, { params: { limit, include_best: true } }).then((r) => r.data),
  shop: (params, options = {}) => http.get(`/shop`, { params, signal: options.signal }).then((r) => r.data),
  buySkins: (payload) => http.post(`/shop/buy`, payload).then((r) => r.data),
  upgrade: (payload) => http.post(`/upgrade`, payload).then((r) => r.data),
  depositInfo: () => http.get(`/deposit/info`).then((r) => r.data),
  applyPromo: (code) => http.post(`/promo/apply`, { code }).then((r) => r.data),
  profile: () => http.get(`/profile`).then((r) => r.data),
  notifications: () => http.get(`/notifications`).then((r) => r.data),
  readNotifications: (read_through) => http.post(`/notifications/read`, { read_through }).then((r) => r.data),
  referrals: () => http.get(`/referrals`).then((r) => r.data),
  publicProfile: (discordId) => http.get(`/users/${discordId}`).then((r) => r.data),
  saveRoblox: (payload) => http.post(`/profile/roblox`, payload).then((r) => r.data),
  createDeposit: (payload) => http.post(`/deposits`, payload).then((r) => r.data),
  cancelDeposit: (id) => http.post(`/deposits/${id}/cancel`).then((r) => r.data),
  myDeposits: () => http.get(`/deposits/my`).then((r) => r.data),
  xrocketInfo: () => http.get(`/payments/xrocket/info`).then((r) => r.data),
  xrocketInvoices: () => http.get(`/payments/xrocket/invoices`).then((r) => r.data),
  createXrocketInvoice: (payload) => http.post(`/payments/xrocket/invoices`, payload).then((r) => r.data),
  xrocketInvoice: (id) => http.get(`/payments/xrocket/invoices/${encodeURIComponent(id)}`).then((r) => r.data),
  refreshXrocketInvoice: (id) => http.post(`/payments/xrocket/invoices/${encodeURIComponent(id)}/refresh`).then((r) => r.data),
  cryptobotInfo: () => http.get(`/payments/cryptobot/info`).then((r) => r.data),
  cryptobotInvoices: () => http.get(`/payments/cryptobot/invoices`).then((r) => r.data),
  createCryptobotInvoice: (payload) => http.post(`/payments/cryptobot/invoices`, payload).then((r) => r.data),
  cryptobotInvoice: (id) => http.get(`/payments/cryptobot/invoices/${encodeURIComponent(id)}`).then((r) => r.data),
  refreshCryptobotInvoice: (id) => http.post(`/payments/cryptobot/invoices/${encodeURIComponent(id)}/refresh`).then((r) => r.data),
  chats: () => http.get(`/chats`).then((r) => r.data),
  createChat: (payload) => http.post(`/chats`, payload).then((r) => r.data),
  chatMessages: (id, after) => http.get(`/chats/${encodeURIComponent(id)}/messages`, { params: after ? { after } : {} }).then((r) => r.data),
  sendChatMessage: (id, text) => http.post(`/chats/${encodeURIComponent(id)}/messages`, { text }).then((r) => r.data),
  closeChat: (id) => http.post(`/chats/${encodeURIComponent(id)}/close`).then((r) => r.data),
  chatAttach: (id, blob) => {
    const form = new FormData();
    form.append("file", blob, `screenshot.${(blob.type || "image/webp").split("/")[1]}`);
    return http.post(`/chats/${encodeURIComponent(id)}/attachments`, form, { timeout: 60000 }).then((r) => r.data);
  },
  chatAttachment: (id, attachmentId) => http.get(`/chats/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}`, { responseType: "blob" }).then((r) => r.data),
  donationRequest: (currency, amount) => http.post(`/donationalerts/requests`, { currency, amount }).then((r) => r.data),
  donationPaid: (depositId) => http.post(`/donationalerts/requests/${encodeURIComponent(depositId)}/paid`).then((r) => r.data),
  reopenChat: (id) => http.post(`/chats/${encodeURIComponent(id)}/reopen`).then((r) => r.data),
  sellSkins: (uids) => http.post(`/skins/sell`, { uids }).then((r) => r.data),
  withdrawSkins: (uids) => http.post(`/skins/withdraw`, { uids }).then((r) => r.data),
};

// Construct formatters once per locale, not twice per card on every click.
const formatters = new Map();
const formatter = (money = false) => {
  const locale = getLang() === "en" ? "en-US" : "ru-RU";
  const key = `${locale}:${money}`;
  if (!formatters.has(key)) formatters.set(key, new Intl.NumberFormat(locale,
    money ? { minimumFractionDigits: 2, maximumFractionDigits: 2 } : undefined));
  return formatters.get(key);
};
export const formatNumber = (n) => formatter().format(Math.round(Number(n) || 0));

// Сервер отдаёт даты из Mongo «голыми» (без часового пояса, по факту UTC).
// Без поправки браузер читает их как локальное время и все часы плывут
// на смещение зоны (у админа в UTC+5 ожидание стартовало с «5 ч»).
export const parseServerDate = (d) => {
  if (typeof d === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(d) && !/(Z|[+-]\d{2}:?\d{2})$/.test(d)) d += "Z";
  return new Date(d);
};

export const formatMoney = (n) => formatter(true).format(Number(n) || 0);

export const inventoryTotal = (skins) => (skins || []).reduce((a, s) => a + Number(s.price || 0), 0);

export const pct = (frac) => String(Math.round(Number(frac || 0) * 10000) / 100).replace(".", ",");

const ADMIN_KEY = "bloxgrade_admin_token";
export const getAdminToken = () => sessionStorage.getItem(ADMIN_KEY);
export const setAdminToken = (t) => (t ? sessionStorage.setItem(ADMIN_KEY, t) : sessionStorage.removeItem(ADMIN_KEY));
export const adminHttp = axios.create({ baseURL: API, timeout: 20000 });
adminHttp.interceptors.response.use((response) => response, normalizeError);
adminHttp.interceptors.request.use((cfg) => {
  const t = getAdminToken();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
export const adminApi = {
  login: (phrases) => adminHttp.post(`/admin/login`, { phrases }).then((r) => r.data),
  logout: () => adminHttp.post(`/admin/logout`).then((r) => r.data),
  session: () => adminHttp.get(`/admin/session`).then((r) => r.data),
  promos: () => adminHttp.get(`/admin/promos`).then((r) => r.data),
  createPromo: (payload) => adminHttp.post(`/admin/promos`, payload).then((r) => r.data),
  updatePromo: (id, payload) => adminHttp.put(`/admin/promos/${encodeURIComponent(id)}`, payload).then((r) => r.data),
  deletePromo: (id) => adminHttp.delete(`/admin/promos/${encodeURIComponent(id)}`).then((r) => r.data),
  promoGifts: (promoId, limit = 100) => adminHttp.get(`/admin/promo-gifts`, { params: { promo_id: promoId, limit } }).then((r) => r.data),
  deposits: (status) => adminHttp.get(`/admin/deposits`, { params: { status } }).then((r) => r.data),
  confirm: (id, rap, note) => adminHttp.post(`/admin/deposits/${id}/confirm`, { rap, note }).then((r) => r.data),
  depositPreview: (id, rap) => adminHttp.post(`/admin/deposits/${id}/preview`, { rap }).then((r) => r.data),
  reject: (id, reason) => adminHttp.post(`/admin/deposits/${id}/reject`, { reason }).then((r) => r.data),
  withdrawals: (status) => adminHttp.get(`/admin/withdrawals`, { params: { status } }).then((r) => r.data),
  withdrawalDone: (id) => adminHttp.post(`/admin/withdrawals/${id}/done`).then((r) => r.data),
  withdrawalCancel: (id, reason) => adminHttp.post(`/admin/withdrawals/${id}/cancel`, { reason }).then((r) => r.data),
  bank: () => adminHttp.get(`/admin/bank`).then((r) => r.data),
  bankSettings: (payload, pin) => adminHttp.put(`/admin/bank/settings`, { ...payload, pin }).then((r) => r.data),
  bankAdjust: (amount, note, pin) => adminHttp.post(`/admin/bank/adjust`, { amount, note, pin }).then((r) => r.data),
  poolTopup: (amount, note, pin) => adminHttp.post(`/admin/bank/pool`, { amount, note, pin }).then((r) => r.data),
  bankReset: (pin, requestId) => adminHttp.post(`/admin/bank/reset`, { pin, request_id: requestId, scope: "full_economy" }, { timeout: 110000 }).then((r) => r.data),
  players: () => adminHttp.get(`/admin/players`).then((r) => r.data),
  grantCoins: (id, payload) => adminHttp.post(`/admin/players/${encodeURIComponent(id)}/coins`, payload).then((r) => r.data),
  coinGrants: (id) => adminHttp.get(`/admin/players/${encodeURIComponent(id)}/coins`).then((r) => r.data),
  commands: () => adminHttp.get(`/admin/commands`).then((r) => r.data),
  createCommand: (payload) => adminHttp.post(`/admin/commands`, payload).then((r) => r.data),
  updateCommand: (id, payload) => adminHttp.put(`/admin/commands/${encodeURIComponent(id)}`, payload).then((r) => r.data),
  deleteCommand: (id) => adminHttp.delete(`/admin/commands/${encodeURIComponent(id)}`).then((r) => r.data),
  rains: (limit = 20) => adminHttp.get(`/admin/rains`, { params: { limit } }).then((r) => r.data),
  rainSettings: () => adminHttp.get(`/admin/rain/settings`).then((r) => r.data),
  saveRainSettings: (payload) => adminHttp.put(`/admin/rain/settings`, payload).then((r) => r.data),
  rainClose: () => adminHttp.post(`/admin/rain/close`).then((r) => r.data),
  chats: (status, q, offset = 0) => adminHttp.get(`/admin/chats`, { params: { status, offset, ...(q ? { q } : {}) } }).then((r) => r.data),
  search: (q) => adminHttp.get(`/admin/search`, { params: { q } }).then((r) => r.data),
  // requestId stays the same for retries of one command, so a lost response never credits twice.
  chatDeposit: (id, rap, note, requestId) => adminHttp.post(`/admin/chats/${encodeURIComponent(id)}/deposit`, { rap, note, request_id: requestId }).then((r) => r.data),
  chatDepositPreview: (id, rap) => adminHttp.post(`/admin/chats/${encodeURIComponent(id)}/deposit/preview`, { rap }).then((r) => r.data),
  chatWithdrawalsDone: (id) => adminHttp.post(`/admin/chats/${encodeURIComponent(id)}/withdrawals/done`).then((r) => r.data),
  chatSummary: () => adminHttp.get(`/admin/chats/summary`).then((r) => r.data),
  chatMessages: (id) => adminHttp.get(`/admin/chats/${encodeURIComponent(id)}/messages`).then((r) => r.data),
  chatAccept: (id) => adminHttp.post(`/admin/chats/${encodeURIComponent(id)}/accept`).then((r) => r.data),
  chatSend: (id, text) => adminHttp.post(`/admin/chats/${encodeURIComponent(id)}/messages`, { text }).then((r) => r.data),
  chatAttachment: (id, attachmentId) => adminHttp.get(`/admin/chats/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}`, { responseType: "blob" }).then((r) => r.data),
  telegramStatus: () => adminHttp.get(`/admin/telegram`).then((r) => r.data),
  telegramSetup: () => adminHttp.post(`/admin/telegram/setup`).then((r) => r.data),
  telegramTest: () => adminHttp.post(`/admin/telegram/test`).then((r) => r.data),
  chatClose: (id) => adminHttp.post(`/admin/chats/${encodeURIComponent(id)}/close`).then((r) => r.data),
};

export const DEPOSIT_FEE = 0.2;

export const DEPOSIT_REJECTION_REASONS = {
  long_wait: "Долгое ожидание",
  illiquid_skin: "Неликвидный скин",
  yellow_tag: "Жёлтая табличка на скине",
  no_reason: "Без причины",
};

export const rejectionReasonText = (reason, t) => Object.prototype.hasOwnProperty.call(DEPOSIT_REJECTION_REASONS, reason)
  ? t(`requests.rejection_${reason}`) : reason;
