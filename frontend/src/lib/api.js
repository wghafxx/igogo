import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const TOKEN_KEY = "bloxgrade_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

const http = axios.create({ baseURL: API, withCredentials: true, timeout: 20000 });
const normalizeError = (error) => {
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) error.response.data.detail = detail.map((d) => d.msg || "Проверьте введённые данные").join(". ");
  else if (detail && typeof detail === "object") error.response.data.detail = "Проверьте введённые данные";
  return Promise.reject(error);
};
http.interceptors.response.use((response) => response, normalizeError);
http.interceptors.request.use((cfg) => {
  const t = getToken();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
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

export const discordLoginUrl = `${API}/auth/discord/login`;

export const api = {
  presence: (session_id) => http.post(`/presence`, { session_id }).then((r) => r.data),
  stats: () => http.get(`/stats`).then((r) => r.data),
  gameConfig: () => http.get(`/game-config`).then((r) => r.data),
  user: (session_id) => http.get(`/user/${session_id}`).then((r) => r.data),
  me: () => http.get(`/auth/me`).then((r) => r.data),
  logout: () => http.post(`/auth/logout`).then((r) => r.data),
  liveDrops: (limit = 30) => http.get(`/live-drops`, { params: { limit } }).then((r) => r.data),
  shop: (params) => http.get(`/shop`, { params }).then((r) => r.data),
  upgrade: (payload) => http.post(`/upgrade`, payload).then((r) => r.data),
  depositInfo: () => http.get(`/deposit/info`).then((r) => r.data),
  applyPromo: (code) => http.post(`/promo/apply`, { code }).then((r) => r.data),
  profile: () => http.get(`/profile`).then((r) => r.data),
  publicProfile: (discordId) => http.get(`/users/${discordId}`).then((r) => r.data),
  saveRoblox: (payload) => http.post(`/profile/roblox`, payload).then((r) => r.data),
  createDeposit: (payload) => http.post(`/deposits`, payload).then((r) => r.data),
  cancelDeposit: (id) => http.post(`/deposits/${id}/cancel`).then((r) => r.data),
  myDeposits: () => http.get(`/deposits/my`).then((r) => r.data),
  sellSkins: (uids) => http.post(`/skins/sell`, { uids }).then((r) => r.data),
  withdrawSkins: (uids) => http.post(`/skins/withdraw`, { uids }).then((r) => r.data),
};

export const formatNumber = (n) =>
  new Intl.NumberFormat("ru-RU").format(Math.round(Number(n) || 0));

// Сервер отдаёт даты из Mongo «голыми» (без часового пояса, по факту UTC).
// Без поправки браузер читает их как локальное время и все часы плывут
// на смещение зоны (у админа в UTC+5 ожидание стартовало с «5 ч»).
export const parseServerDate = (d) => {
  if (typeof d === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(d) && !/(Z|[+-]\d{2}:?\d{2})$/.test(d)) d += "Z";
  return new Date(d);
};

export const formatMoney = (n) =>
  new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(n) || 0);

export const inventoryTotal = (skins) => (skins || []).reduce((a, s) => a + Number(s.price || 0), 0);

export const pct = (frac) => String(Math.round(Number(frac || 0) * 1000) / 10).replace(".", ",");

const ADMIN_KEY = "bloxgrade_admin_token";
export const getAdminToken = () => sessionStorage.getItem(ADMIN_KEY);
export const setAdminToken = (t) => (t ? sessionStorage.setItem(ADMIN_KEY, t) : sessionStorage.removeItem(ADMIN_KEY));
const adminHttp = axios.create({ baseURL: API, timeout: 20000 });
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
  deposits: (status) => adminHttp.get(`/admin/deposits`, { params: { status } }).then((r) => r.data),
  confirm: (id, rap, note) => adminHttp.post(`/admin/deposits/${id}/confirm`, { rap, note }).then((r) => r.data),
  depositPreview: (id, rap) => adminHttp.post(`/admin/deposits/${id}/preview`, { rap }).then((r) => r.data),
  reject: (id) => adminHttp.post(`/admin/deposits/${id}/reject`).then((r) => r.data),
  withdrawals: (status) => adminHttp.get(`/admin/withdrawals`, { params: { status } }).then((r) => r.data),
  withdrawalDone: (id) => adminHttp.post(`/admin/withdrawals/${id}/done`).then((r) => r.data),
  bank: () => adminHttp.get(`/admin/bank`).then((r) => r.data),
  bankSettings: (payload) => adminHttp.put(`/admin/bank/settings`, payload).then((r) => r.data),
  bankAdjust: (amount, note) => adminHttp.post(`/admin/bank/adjust`, { amount, note }).then((r) => r.data),
  poolTopup: (amount, note) => adminHttp.post(`/admin/bank/pool`, { amount, note }).then((r) => r.data),
  players: () => adminHttp.get(`/admin/players`).then((r) => r.data),
  rains: (limit = 20) => adminHttp.get(`/admin/rains`, { params: { limit } }).then((r) => r.data),
  rainSettings: () => adminHttp.get(`/admin/rain/settings`).then((r) => r.data),
  saveRainSettings: (payload) => adminHttp.put(`/admin/rain/settings`, payload).then((r) => r.data),
  rainClose: () => adminHttp.post(`/admin/rain/close`).then((r) => r.data),
};

export const DEPOSIT_FEE = 0.2;
