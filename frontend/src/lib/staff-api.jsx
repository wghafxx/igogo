import { http, adminHttp } from "./api";

const enc = encodeURIComponent;
const data = (r) => r.data;
const upload = (client, url, file, fields) => {
  const form = new FormData();
  form.append("file", file);
  Object.entries(fields).forEach(([k, v]) => v != null && form.append(k, v));
  return client.post(url, form, { timeout: 60000 }).then(data);
};

export const staffApi = {
  me: () => http.get(`/staff/me`).then(data),
  queue: () => http.get(`/staff/queue`).then(data),
  claim: (id) => http.post(`/staff/requests/${enc(id)}/claim`).then(data),
  requests: () => http.get(`/staff/requests`).then(data),
  request: (id) => http.get(`/staff/requests/${enc(id)}`).then(data),
  messages: (id) => http.get(`/staff/requests/${enc(id)}/messages`).then(data),
  send: (id, text) => http.post(`/staff/requests/${enc(id)}/messages`, { text }).then(data),
  chatAttachment: (depId, attachmentId) => http.get(`/staff/requests/${enc(depId)}/attachments/${enc(attachmentId)}`, { responseType: "blob" }).then(data),
  transferStarted: (id) => http.post(`/staff/requests/${enc(id)}/transfer-started`).then(data),
  uploadEvidence: (file, purpose, depositId) => upload(http, `/staff/evidence`, file, { purpose, deposit_id: depositId }),
  evidence: (fileId) => http.get(`/staff/evidence/${enc(fileId)}`, { responseType: "blob" }).then(data),
  report: (id, payload) => http.post(`/staff/requests/${enc(id)}/report`, payload).then(data),
  returnSkins: (id, payload) => http.post(`/staff/requests/${enc(id)}/return`, payload).then(data),
  transfers: () => http.get(`/staff/transfers`).then(data),
  transfer: (payload) => http.post(`/staff/transfers`, payload).then(data),
  shift: () => http.get(`/staff/shift`).then(data),
  shiftAction: (action) => http.post(`/staff/shift/${action}`).then(data),
  stats: (params) => http.get(`/staff/stats`, { params }).then(data),
  chats: (status, q, offset = 0) => http.get(`/staff/chats`, { params: { status, offset, ...(q ? { q } : {}) } }).then(data),
  chatSummary: () => http.get(`/staff/chats/summary`).then(data),
  chatDetail: (id) => http.get(`/staff/chats/${enc(id)}/messages`).then(data),
  chatAccept: (id) => http.post(`/staff/chats/${enc(id)}/accept`).then(data),
  chatSend: (id, text) => http.post(`/staff/chats/${enc(id)}/messages`, { text }).then(data),
  chatClose: (id) => http.post(`/staff/chats/${enc(id)}/close`).then(data),
  chatFile: (id, attachmentId) => http.get(`/staff/chats/${enc(id)}/attachments/${enc(attachmentId)}`, { responseType: "blob" }).then(data),
  chatEvidence: (id, file, purpose) => upload(http, `/staff/chats/${enc(id)}/evidence`, file, { purpose }),
  chatReport: (id, payload) => http.post(`/staff/chats/${enc(id)}/report`, payload).then(data),
  chatReturn: (id, payload) => http.post(`/staff/chats/${enc(id)}/return`, payload).then(data),
  commands: () => http.get(`/staff/commands`).then(data),
};

export const adminStaffApi = {
  list: () => adminHttp.get(`/admin/staff`).then(data),
  create: (payload) => adminHttp.post(`/admin/staff`, payload).then(data),
  update: (id, payload) => adminHttp.put(`/admin/staff/${enc(id)}`, payload).then(data),
  setActive: (id, active) => adminHttp.post(`/admin/staff/${enc(id)}/${active ? "enable" : "disable"}`).then(data),
  stats: (id, params) => adminHttp.get(`/admin/staff/${enc(id)}/stats`, { params }).then(data),
  reviews: () => adminHttp.get(`/admin/staff-reviews`).then(data),
  report: (id) => adminHttp.get(`/admin/staff-reports/${enc(id)}`).then(data),
  approve: (id) => adminHttp.post(`/admin/staff-reports/${enc(id)}/approve`).then(data),
  revision: (id, reason) => adminHttp.post(`/admin/staff-reports/${enc(id)}/revision`, { reason }).then(data),
  reject: (id, reason) => adminHttp.post(`/admin/staff-reports/${enc(id)}/reject`, { reason }).then(data),
  revisionAfterReject: (depId, reason) => adminHttp.post(`/admin/staff-requests/${enc(depId)}/revision`, { reason }).then(data),
  confirmMove: (id) => adminHttp.post(`/admin/staff-moves/${enc(id)}/confirm`).then(data),
  declineMove: (id, reason) => adminHttp.post(`/admin/staff-moves/${enc(id)}/decline`, { reason }).then(data),
  evidence: (fileId) => adminHttp.get(`/admin/staff-evidence/${enc(fileId)}`, { responseType: "blob" }).then(data),
  editShift: (id, payload) => adminHttp.put(`/admin/staff-shifts/${enc(id)}`, payload).then(data),
  resolveManual: (depId, reason) => adminHttp.post(`/admin/staff-manual/${enc(depId)}/resolve`, { reason }).then(data),
  audit: (staffId) => adminHttp.get(`/admin/staff-audit`, { params: staffId ? { staff_id: staffId } : {} }).then(data),
  telegram: () => adminHttp.get(`/admin/staff-telegram`).then(data),
  telegramSetup: () => adminHttp.post(`/admin/staff-telegram/setup`).then(data),
  telegramTest: () => adminHttp.post(`/admin/staff-telegram/test`).then(data),
};

export const errText = (e, fallback = "Ошибка") => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : fallback;
};

export const fmtDuration = (seconds) => {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h} ч ${String(m).padStart(2, "0")} мин` : `${m} мин`;
};

export const fmtRap = (n) => (Math.round((Number(n) || 0) * 100) / 100).toLocaleString("ru-RU", { maximumFractionDigits: 2 });

export const STATE_LABELS = {
  assigned: ["В работе", "bg-[#00a2ff]/15 text-[#7cc8ff]"],
  review: ["На проверке", "bg-[#ffb000]/15 text-[#ffcf5a]"],
  revision: ["На доработке", "bg-[#b36bff]/15 text-[#d2a8ff]"],
  return_required: ["Нужен возврат", "bg-[#ff5c5c]/15 text-[#ff9b9b]"],
  return_review: ["Возврат на проверке", "bg-[#ff5c5c]/15 text-[#ff9b9b]"],
  approving: ["Зачисляется", "bg-[#2ecc71]/15 text-[#7ee2a8]"],
  approved: ["Зачислено", "bg-[#2ecc71]/15 text-[#7ee2a8]"],
  returned: ["Возвращено игроку", "bg-white/[0.06] text-[#8e91a3]"],
  submitted: ["На проверке", "bg-[#ffb000]/15 text-[#ffcf5a]"],
  rejected: ["Отклонено", "bg-[#ff5c5c]/15 text-[#ff9b9b]"],
  manual_review: ["Ручной разбор", "bg-[#ff5c5c]/15 text-[#ff9b9b]"],
  pending: ["Ждёт подтверждения", "bg-[#ffb000]/15 text-[#ffcf5a]"],
  confirmed: ["Подтверждено", "bg-[#2ecc71]/15 text-[#7ee2a8]"],
  declined: ["Отклонено", "bg-[#ff5c5c]/15 text-[#ff9b9b]"],
  cancelled: ["Отменено", "bg-white/[0.06] text-[#8e91a3]"],
};

export const StatePill = ({ state, testId }) => {
  const [label, cls] = STATE_LABELS[state] || [state || "—", "bg-white/[0.06] text-[#8e91a3]"];
  return <span className={`inline-flex items-center h-6 px-2 rounded-full text-[11px] font-bold whitespace-nowrap ${cls}`} data-testid={testId}>{label}</span>;
};
