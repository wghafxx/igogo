export const REQUEST_SOUND_URL = "/sounds/new-request.mp3";
let context;
let buffer;
let loading;
let source;
let media;

// Resume during the original operator gesture so later polling can play audio.
export const prepareRequestSound = () => {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    if (!context) context = new AudioContext();
    if (context.state === "suspended") context.resume().catch(() => {});
    if (!buffer && !loading) {
      loading = fetch(REQUEST_SOUND_URL).then((response) => {
        if (!response.ok) throw new Error("Request audio unavailable");
        return response.arrayBuffer();
      }).then((data) => context.decodeAudioData(data)).then((decoded) => { buffer = decoded; })
        .catch(() => {}).finally(() => { loading = null; });
    }
  } catch { /* Playback can fall back to the bundled MP3. */ }
};

export const playRequestSound = async () => {
  try {
    if (context?.state === "running") {
      if (loading) await loading;
      if (buffer) {
        if (source) { try { source.stop(); } catch { /* Already finished. */ } source.disconnect(); }
        const nextSource = context.createBufferSource();
        source = nextSource;
        nextSource.buffer = buffer;
        const gain = context.createGain();
        gain.gain.value = 0.6;
        nextSource.connect(gain);
        gain.connect(context.destination);
        nextSource.onended = () => {
          nextSource.disconnect();
          gain.disconnect();
          if (source === nextSource) source = null;
        };
        nextSource.start();
        return true;
      }
    }
    if (typeof Audio === "undefined") return false;
    if (!media) { media = new Audio(REQUEST_SOUND_URL); media.preload = "auto"; media.volume = 0.6; }
    media.currentTime = 0;
    await media.play();
    return true;
  } catch { return false; } // Browser autoplay restrictions must not break the console.
};
