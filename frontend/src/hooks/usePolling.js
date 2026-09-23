import { useEffect, useRef } from "react";

// Shared refresh policy: no overlapping runs, paused while the tab is hidden, one catch-up run when it returns.
export function usePolling(fn, delay, enabled = true) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    if (!enabled || !delay) return undefined;
    let running = false;
    const tick = async () => {
      if (running || document.hidden) return;
      running = true;
      try { await fnRef.current(); } catch { /* callers report their own errors */ } finally { running = false; }
    };
    const timer = setInterval(tick, delay);
    const onVisible = () => { if (!document.hidden) tick(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, [delay, enabled]);
}
