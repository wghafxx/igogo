const clickAudio = typeof Audio !== "undefined" ? new Audio("/sounds/click.mp3") : null;
const resultAudio = typeof Audio !== "undefined" ? {
  win: new Audio("/sounds/win.mp3"),
  lose: new Audio("/sounds/lose.mp3"),
} : {};
const rareAudio = typeof Audio !== "undefined" ? {
  casino: new Audio("/sounds/casino.mp3"),
  mellstroy: new Audio("/sounds/mellstroy.mp3"),
} : {};
const RARE_VOLUME = { casino: 0.12, mellstroy: 0.3 };
Object.entries(rareAudio).forEach(([key, audio]) => { audio.preload = "auto"; audio.volume = RARE_VOLUME[key]; });
Object.values(resultAudio).forEach((audio) => { audio.preload = "auto"; });
let context;
let activeSource;
const buffers = {};
const gains = {};
let loading;
// All sounds are normalised to the same loudness, then played quietly.
const TARGET_RMS = 0.06;
const MASTER_VOLUME = 0.45;
const MEDIA_VOLUME = 0.25;
Object.values(resultAudio).forEach((audio) => { audio.volume = MEDIA_VOLUME; });

const normalGain = (buffer) => {
  const data = buffer.getChannelData(0);
  let sum = 0;
  const step = Math.max(1, Math.floor(data.length / 200000));
  let n = 0;
  for (let i = 0; i < data.length; i += step) { sum += data[i] * data[i]; n += 1; }
  const rms = Math.sqrt(sum / Math.max(1, n));
  return rms > 0 ? Math.min(2, TARGET_RMS / rms) : 1;
};

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
      gains[key] = normalGain(buffers[key]);
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
  Object.values(rareAudio).forEach((audio) => { audio.pause(); audio.currentTime = 0; });
};

export const playRareSound = (key, enabled) => {
  if (!enabled || !rareAudio[key]) return;
  stopResultSound();
  try {
    rareAudio[key].volume = RARE_VOLUME[key];
    rareAudio[key].play().catch(() => {});
  } catch { /* Audio failure must never prevent settlement. */ }
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
      const gain = context.createGain();
      gain.gain.value = (gains[key] || 1) * MASTER_VOLUME;
      activeSource.connect(gain);
      gain.connect(context.destination);
      activeSource.start();
      started("webaudio");
    } else {
      resultAudio[key]?.play().then(() => started("media")).catch(() => {});
    }
  } catch { /* Audio failure must never prevent settlement. */ }
};

let lastTick = -Infinity;
export const playTick = (enabled) => {
  if (!enabled || !clickAudio) return;
  // Limit only overlapping sound restarts, never the actual selection clicks.
  const now = performance.now();
  if (now - lastTick < 50) return;
  lastTick = now;
  try {
    clickAudio.currentTime = 0;
    clickAudio.volume = MEDIA_VOLUME;
    clickAudio.play().catch(() => {});
  } catch {
    /* audio not available */
  }
};
