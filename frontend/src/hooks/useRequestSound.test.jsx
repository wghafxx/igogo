import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { useRequestSound } from "./useRequestSound";
import { playRequestSound, prepareRequestSound } from "../lib/request-sound";
import RequestSoundButton from "../components/RequestSoundButton";

jest.mock("../lib/request-sound", () => ({ playRequestSound: jest.fn(), prepareRequestSound: jest.fn() }));
const summary = (cursor, unread = 0) => ({ open: 1, active: 0, unread, request_cursor: cursor });
const first = "2026-10-03T00:00:00Z";
const second = "2026-10-03T00:00:01Z";
const third = "2026-10-03T00:00:02Z";
let root;
let container;
const Harness = ({ data, enabled = true }) => <RequestSoundButton {...useRequestSound(data, enabled)} />;
const render = (data, enabled = true) => act(async () => { root.render(<Harness data={data} enabled={enabled} />); });
const click = () => act(async () => { container.querySelector("button").click(); });

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  jest.resetAllMocks();
  playRequestSound.mockResolvedValue(true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => { await act(async () => { root.unmount(); }); container.remove(); });

test("initial requests and ordinary message counters are silent; new request plays once", async () => {
  await render(summary(first));
  await render(summary(first, 10));
  expect(playRequestSound).not.toHaveBeenCalled();
  await render(summary(second, 10));
  expect(playRequestSound).toHaveBeenCalledTimes(1);
  await render(summary(second, 0));
  await render(summary(first)); // Delayed response or another employee taking a chat.
  await render(summary(second));
  expect(playRequestSound).toHaveBeenCalledTimes(1);
  await render(summary(third));
  expect(playRequestSound).toHaveBeenCalledTimes(2);
});

test("the first request after an empty queue plays; summaries without cursor are safe", async () => {
  await render({ open: 0, unread: 0 });
  await render(summary(null));
  await render(summary(first));
  expect(playRequestSound).toHaveBeenCalledTimes(1);
});

test("mute remembers the choice and new requests are not replayed when re-enabled", async () => {
  await render(summary(first));
  await click();
  expect(localStorage.getItem("bloxgrade:request-sound")).toBe("off");
  await render(summary(second));
  expect(playRequestSound).not.toHaveBeenCalled();
  await click(); // Explicit sound check on enabling.
  expect(prepareRequestSound).toHaveBeenCalledTimes(1);
  expect(playRequestSound).toHaveBeenCalledTimes(1);
  expect(localStorage.getItem("bloxgrade:request-sound")).toBe("on");
  await render(summary(second));
  expect(playRequestSound).toHaveBeenCalledTimes(1);
  await render(summary(third));
  expect(playRequestSound).toHaveBeenCalledTimes(2);
});

test("browser restrictions offer a gesture to enable sound without replaying old requests", async () => {
  await render(summary(first));
  playRequestSound.mockResolvedValueOnce(false);
  await render(summary(second));
  expect(container.textContent).toContain("Включить звук заявок");
  await click();
  expect(container.textContent).toContain("Звук заявок включён");
  expect(prepareRequestSound).toHaveBeenCalledTimes(1);
  await render(summary(second));
  expect(playRequestSound).toHaveBeenCalledTimes(2);
});

test("sound unlock happens on operator gestures and access loss resets the baseline", async () => {
  await render(summary(first));
  await act(async () => { document.dispatchEvent(new Event("pointerdown")); });
  expect(prepareRequestSound).toHaveBeenCalledTimes(1);
  expect(playRequestSound).not.toHaveBeenCalled();
  await render(summary(second), false);
  await render(summary(third), true);
  expect(playRequestSound).not.toHaveBeenCalled();
});
