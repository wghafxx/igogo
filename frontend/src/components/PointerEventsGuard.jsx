import { useEffect } from "react";

const OPEN_LAYERS = ['dialog', 'alertdialog', 'menu', 'listbox']
  .map((role) => `[role="${role}"][data-state="open"]`).join(', ');

// Radix locks body pointer-events while a modal layer is open; if a layer unmounts mid-transition the lock can
// get stuck and the whole page stops reacting to clicks. Clear it whenever no layer is actually open.
export default function PointerEventsGuard() {
  useEffect(() => {
    let timer = null;
    const check = () => {
      timer = null;
      if (document.body.style.pointerEvents !== "none") return;
      // A popper wrapper can belong to a tooltip or a closed menu. Only an
      // actually open dismissable layer owns the lock (including Radix Select).
      if (!document.querySelector(OPEN_LAYERS)) document.body.style.pointerEvents = "";
    };
    const schedule = () => {
      // Throttle, not debounce: ongoing animation must never postpone recovery.
      if (timer === null && document.body.style.pointerEvents === "none") {
        timer = window.setTimeout(check, 350);
      }
    };
    const bodyObserver = new MutationObserver(schedule);
    bodyObserver.observe(document.body, { attributes: true, attributeFilter: ["style"] });
    const layerObserver = new MutationObserver(schedule);
    layerObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-state"] });
    const interval = window.setInterval(schedule, 2000);
    schedule();
    return () => {
      bodyObserver.disconnect();
      layerObserver.disconnect();
      window.clearTimeout(timer);
      window.clearInterval(interval);
    };
  }, []);
  return null;
}
