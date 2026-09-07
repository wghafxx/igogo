const clickAudio = typeof Audio !== "undefined" ? new Audio("/sounds/click.mp3") : null;
const resultAudio = typeof Audio !== "undefined" ? {
  win: new Audio("/sounds/win.mp3"),
  lose: new Audio("/sounds/lose.mp3"),
} : {};
Object.values(resultAudio).forEach((audio) => { audio.preload = "auto"; });
let context;
let activeSource;
const buffers = {};
let loading;

// Resume on the original user gesture, not after the asynchronous spin request.
export const prepareResultSounds = () => {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    if (!context) context = new AudioContext();
    if (context.state === "suspended") context.resume().catch(() => {});
    if (!loading) loading = Promise.all(Object.keys(resultAudio).map(async (key) => {
      const response = await fetch(`/sounds/${key}.mp3`);
      if (!response.ok) throw new Error("Audio unavailable");
      buffers[key] = await context.decodeAudioData(await response.arrayBuffer());
    })).catch(() => { loading = null; });
  } catch { /* Browsers without Web Audio use preloaded media instead. */ }
};

export const stopResultSound = () => {
  if (activeSource) {
    try { activeSource.stop(); } catch { /* Already finished. */ }
    activeSource.disconnect();
    activeSource = null;
  }
  Object.values(resultAudio).forEach((audio) => { audio.pause(); audio.currentTime = 0; });
};

export const playResultSound = (win, enabled) => {
  if (!enabled) return;
  stopResultSound();
  const key = win ? "win" : "lose";
  const started = (mode) => window.dispatchEvent(new CustomEvent("bloxgrade:result-sound", {
    detail: { result: key, source: `/sounds/${key}.mp3`, mode },
  }));
  try {
    if (context?.state === "running" && buffers[key]) {
      activeSource = context.createBufferSource();
      activeSource.buffer = buffers[key];
      activeSource.connect(context.destination);
      activeSource.start();
      started("webaudio");
    } else {
      resultAudio[key]?.play().then(() => started("media")).catch(() => {});
    }
  } catch { /* Audio failure must never prevent settlement. */ }
};

export const playTick = (enabled) => {
  if (!enabled || !clickAudio) return;
  try {
    clickAudio.currentTime = 0;
    clickAudio.volume = 0.6;
    clickAudio.play().catch(() => {});
  } catch {
    /* audio not available */
  }
};
