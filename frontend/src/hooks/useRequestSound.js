import { useCallback, useEffect, useRef, useState } from "react";
import { playRequestSound, prepareRequestSound } from "../lib/request-sound";

const STORAGE_KEY = "bloxgrade:request-sound";
export function useRequestSound(summary, enabled) {
  const cursor = useRef(null);
  const [soundOn, setSoundOn] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) !== "off"; } catch { return true; }
  });
  const [blocked, setBlocked] = useState(false);

  useEffect(() => {
    if (!enabled || !soundOn) return undefined;
    const prepare = () => prepareRequestSound();
    document.addEventListener("pointerdown", prepare, true);
    document.addEventListener("keydown", prepare, true);
    return () => {
      document.removeEventListener("pointerdown", prepare, true);
      document.removeEventListener("keydown", prepare, true);
    };
  }, [enabled, soundOn]);

  useEffect(() => {
    if (!enabled) { cursor.current = null; return; }
    if (!summary || !("request_cursor" in summary)) return;
    const next = summary.request_cursor ? Date.parse(summary.request_cursor) : 0;
    if (!Number.isFinite(next)) return;
    // First successful load is a silent baseline, even when there are old requests.
    if (cursor.current === null) { cursor.current = next; return; }
    if (next <= cursor.current) return;
    cursor.current = next; // Muting and stale/repeated responses do not queue replays.
    if (soundOn) playRequestSound().then((played) => setBlocked(!played));
  }, [summary, enabled, soundOn]);

  const toggleSound = useCallback(() => {
    if (!soundOn || blocked) {
      prepareRequestSound();
      playRequestSound().then((played) => setBlocked(!played));
      setSoundOn(true);
      try { localStorage.setItem(STORAGE_KEY, "on"); } catch { /* Storage is optional. */ }
    } else {
      setSoundOn(false);
      try { localStorage.setItem(STORAGE_KEY, "off"); } catch { /* Storage is optional. */ }
    }
  }, [soundOn, blocked]);
  return { soundOn, blocked, toggleSound };
}
