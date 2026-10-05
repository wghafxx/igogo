const originalAudio = global.Audio;
const originalContext = window.AudioContext;
const originalFetch = global.fetch;
let media;
beforeEach(() => {
  jest.resetModules();
  media = { currentTime: 1, play: jest.fn().mockResolvedValue(), preload: "", volume: 0 };
  global.Audio = jest.fn(() => media);
  window.AudioContext = undefined;
});
afterEach(() => { global.Audio = originalAudio; window.AudioContext = originalContext; global.fetch = originalFetch; });

test("plays the supplied MP3 and catches browser playback rejection", async () => {
  const { playRequestSound, REQUEST_SOUND_URL } = require("./request-sound");
  expect(await playRequestSound()).toBe(true);
  expect(global.Audio).toHaveBeenCalledWith("/sounds/new-request.mp3");
  expect(REQUEST_SOUND_URL).toBe("/sounds/new-request.mp3");
  expect(media.currentTime).toBe(0);
  media.play.mockRejectedValueOnce(new Error("Autoplay blocked"));
  expect(await playRequestSound()).toBe(false);
});

test("operator gesture unlocks Web Audio for later asynchronous request alerts", async () => {
  const buffer = {};
  const gain = { gain: {}, connect: jest.fn() };
  const firstSource = { connect: jest.fn(), start: jest.fn(), stop: jest.fn(), disconnect: jest.fn() };
  const nextSource = { ...firstSource, start: jest.fn() };
  const context = { state: "suspended", destination: {}, resume: jest.fn(() => { context.state = "running"; return Promise.resolve(); }),
    decodeAudioData: jest.fn().mockResolvedValue(buffer), createBufferSource: jest.fn().mockReturnValueOnce(firstSource).mockReturnValueOnce(nextSource),
    createGain: jest.fn().mockReturnValue(gain) };
  window.AudioContext = jest.fn(() => context);
  global.fetch = jest.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(1) });
  const { prepareRequestSound, playRequestSound } = require("./request-sound");
  prepareRequestSound();
  expect(context.resume).toHaveBeenCalledTimes(1);
  expect(await playRequestSound()).toBe(true);
  expect(firstSource.buffer).toBe(buffer);
  expect(firstSource.start).toHaveBeenCalledTimes(1);
  expect(gain.gain.value).toBe(0.6);
  expect(media.play).not.toHaveBeenCalled();
  expect(await playRequestSound()).toBe(true);
  expect(firstSource.stop).toHaveBeenCalledTimes(1);
  expect(nextSource.start).toHaveBeenCalledTimes(1);
});
