import { useEffect, useState, useCallback, useRef } from "react";
import { api, getSessionId, parseServerDate } from "../lib/api";
import { useAuth } from "./useAuth";

const DEFAULT_SETTINGS = {
  multipliers: [2, 4, 8],
  percents: [35, 55, 75],
  sound: true,
  fastSpin: false,
};

// Mute lasts only for this page visit, including client-side navigation.
// A reload/new tab starts a new module instance with sound enabled again.
let visitSoundEnabled = true;

export const loadSettings = () => {
  try {
    const raw = localStorage.getItem("bloxgrade_settings");
    return { ...normalizeSettings(raw ? JSON.parse(raw) : DEFAULT_SETTINGS), sound: visitSoundEnabled };
  } catch {
    return { ...DEFAULT_SETTINGS, sound: visitSoundEnabled };
  }
};

export const normalizeSettings = (value) => {
  const s = value && typeof value === "object" ? value : {};
  const list = (key, min, max) => [...new Set([
    ...(Array.isArray(s[key]) ? s[key] : []).filter((v) => Number.isFinite(Number(v))).map((v) => Math.max(min, Math.min(max, Math.round(Number(v))))),
    ...DEFAULT_SETTINGS[key],
  ])].slice(0, 3);
  return {
    multipliers: list("multipliers", 2, 100), percents: list("percents", 1, 75),
    sound: typeof s.sound === "boolean" ? s.sound : DEFAULT_SETTINGS.sound,
    fastSpin: typeof s.fastSpin === "boolean" ? s.fastSpin : DEFAULT_SETTINGS.fastSpin,
  };
};
export const saveSettings = (s) => {
  const clean = normalizeSettings(s);
  visitSoundEnabled = clean.sound;
  try { localStorage.setItem("bloxgrade_settings", JSON.stringify(clean)); } catch { /* Settings remain usable for this visit. */ }
};
export { DEFAULT_SETTINGS };

export function useSession() {
  const { authUser, setAuthUser } = useAuth();
  const sessionId = authUser?.session_id || getSessionId();
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  const [stats, setStats] = useState({ online: 0, upgrades: 0 });
  const [user, setUser] = useState({ balance: 0, nickname: "Player", skins: [] });
  const [drops, setDrops] = useState([]);
  const [bestDrop, setBestDrop] = useState(null);
  const userRefreshPaused = useRef(false);
  const pauseUserRefresh = useCallback((value) => { userRefreshPaused.current = value; }, []);

  const refreshUser = useCallback(async () => {
    try {
      const u = await api.user(sessionId);
      if (u.session_id === sessionIdRef.current) {
        setUser(u);
        setAuthUser((old) => old?.session_id === u.session_id ? u : old);
      }
    } catch (e) {
      console.error("user fetch failed", e);
    }
  }, [sessionId, setAuthUser]);

  const refreshDrops = useCallback(async () => {
    try {
      const feed = await api.liveDrops(30);
      setDrops(feed.drops || []);
      setBestDrop(feed.best_drop ? { ...feed.best_drop, expiresAt: Date.now() + Math.max(0, parseServerDate(feed.best_drop_expires_at) - parseServerDate(feed.server_time)) } : null);
    } catch (e) {
      console.error("drops fetch failed", e);
    }
  }, []);

  useEffect(() => {
    if (!bestDrop) return;
    const timer = setTimeout(() => setBestDrop(null), Math.max(0, bestDrop.expiresAt - Date.now()));
    return () => clearTimeout(timer);
  }, [bestDrop]);

  useEffect(() => {
    let alive = true;
    setUser({ balance: 0, nickname: "Player", skins: [] });
    const beat = async () => {
      try {
        const s = await api.presence(sessionId);
        if (alive) setStats(s);
      } catch (e) {
        console.error("presence failed", e);
      }
    };
    beat();
    refreshUser();
    refreshDrops();
    const t1 = setInterval(beat, 15000);
    const t2 = setInterval(refreshDrops, 5000);
    const t3 = setInterval(() => { if (!userRefreshPaused.current) refreshUser(); }, 15000);
    return () => {
      alive = false;
      clearInterval(t1);
      clearInterval(t2);
      clearInterval(t3);
    };
  }, [sessionId, refreshUser, refreshDrops]);

  return { sessionId, stats, setStats, user, setUser, refreshUser, drops, bestDrop, refreshDrops, pauseUserRefresh };
}
