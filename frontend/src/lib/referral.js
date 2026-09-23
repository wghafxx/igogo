const KEY = "bloxgrade_referral";
const valid = (value) => /^[a-f0-9]{16}$/.test(value || "");

export function capturedReferral() {
  const incoming = new URLSearchParams(window.location.search).get("ref");
  try {
    const saved = localStorage.getItem(KEY);
    if (valid(saved)) return saved;
    if (valid(incoming)) { localStorage.setItem(KEY, incoming); return incoming; }
  } catch { return valid(incoming) ? incoming : null; }
  return null;
}

export function clearReferral() {
  try { localStorage.removeItem(KEY); } catch { /* Storage can be disabled. */ }
}
