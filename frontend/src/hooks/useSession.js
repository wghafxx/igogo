import { useEffect, useState, useCallback, useRef } from "react";
import { matchPath, useLocation } from "react-router-dom";
import { api, getSessionId, parseServerDate } from "../lib/api";
import { useAuth } from "./useAuth";
import { usePolling } from "./usePolling";

const GUEST_USER = { balance: 0, nickname: "Player", skins: [] };
// The live feed is the point of the home page; on text pages it only needs to stay roughly fresh.
const DROPS_MS = { home: 5000, other: 20000 };

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
  const [stats, setStats] = useState({ online: 1, upgrades: 0 });
  // Signed-in user lives only in useAuth (single source); guests keep a local copy.
  const [guestUser, setGuestUser] = useState(GUEST_USER);
  const authedRef = useRef(false);
  authedRef.current = Boolean(authUser);
  const user = authUser || guestUser;
  const setUser = useCallback((value) => (authedRef.current ? setAuthUser : setGuestUser)(value), [setAuthUser]);
  const location = useLocation();
  const onHome = Boolean(matchPath("/:lang", location.pathname));
  const dropsSeq = useRef(0);
  const [drops, setDrops] = useState([]);
  const [bestDrop, setBestDrop] = useState(null);
  const userRefreshPaused = useRef(false);
  const pauseUserRefresh = useCallback((value) => { userRefreshPaused.current = value; }, []);

  const refreshUser = useCallback(async () => {
    try {
      const u = await api.user(sessionId);
      if (u.session_id !== sessionIdRef.current) return;
      if (authedRef.current) setAuthUser((old) => (old?.session_id === u.session_id ? u : old));
      else setGuestUser(u);
    } catch (e) {
      console.error("user fetch failed", e);
    }
  }, [sessionId, setAuthUser]);

  const refreshDrops = useCallback(async () => {
    try {
      const seq = ++dropsSeq.current;
      const feed = await api.liveDrops(30);
      if (seq !== dropsSeq.current) return;
      const next = feed.drops || [];
      setDrops((prev) => (prev.length === next.length && prev.every((d, i) => d.id === next[i].id) ? prev : next));
      const best = feed.best_drop ? { ...feed.best_drop, expiresAt: Date.now() + Math.max(0, parseServerDate(feed.best_drop_expires_at) - parseServerDate(feed.server_time)) } : null;
      setBestDrop((prev) => (prev?.id && prev.id === best?.id && Math.abs(prev.expiresAt - best.expiresAt) < 2000 ? prev : best));
    } catch (e) {
      console.error("drops fetch failed", e);
    }
  }, []);

  useEffect(() => {
    if (!bestDrop) return;
    const timer = setTimeout(() => setBestDrop(null), Math.max(0, bestDrop.expiresAt - Date.now()));
    return () => clearTimeout(timer);
  }, [bestDrop]);

  const beat = useCallback(async () => {
    try {
      const s = await api.presence(sessionId);
      if (sessionIdRef.current === sessionId) setStats((prev) => ({ ...s, online: Math.max(1, Number(s.online) || 0, prev.online - 1) }));
    } catch (e) {
      console.error("presence failed", e);
    }
  }, [sessionId]);

  useEffect(() => {
    setGuestUser(GUEST_USER);
    beat();
    refreshUser();
    refreshDrops();
  }, [sessionId, beat, refreshUser, refreshDrops]);
  usePolling(beat, 15000);
  usePolling(refreshDrops, onHome ? DROPS_MS.home : DROPS_MS.other);
  usePolling(() => (userRefreshPaused.current ? undefined : refreshUser()), 15000);

  return { sessionId, stats, setStats, user, setUser, refreshUser, drops, bestDrop, refreshDrops, pauseUserRefresh };
}
