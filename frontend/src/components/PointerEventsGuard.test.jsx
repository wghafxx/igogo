import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import PointerEventsGuard from "./PointerEventsGuard";

let container;
let root;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.useFakeTimers();
  document.body.innerHTML = "";
  document.body.style.pointerEvents = "";
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => {
    root.unmount();
  });
  container.remove();
  document.body.style.pointerEvents = "";
  jest.useRealTimers();
});

test("recovers orphan body pointer lock within bounded time under continuous mutations", async () => {
  await act(async () => {
    root.render(<PointerEventsGuard />);
  });

  document.body.setAttribute("style", "pointer-events: none;");
  // MutationObserver is a microtask: deliver the lock notification before
  // advancing fake time (the browser does this between every timer task).
  await act(async () => { await Promise.resolve(); });

  const spam = document.createElement("div");
  spam.setAttribute("data-state", "closed");
  document.body.appendChild(spam);
  const mutator = setInterval(() => {
    spam.setAttribute("data-state", spam.getAttribute("data-state") === "closed" ? "closing" : "closed");
    spam.style.opacity = String(Math.random());
    const child = document.createElement("span");
    spam.appendChild(child);
    spam.removeChild(child);
  }, 16);

  for (let frame = 0; frame < 32; frame += 1) {
    await act(async () => {
      jest.advanceTimersByTime(16);
      await Promise.resolve();
    });
  }

  clearInterval(mutator);
  expect(document.body.style.pointerEvents).toBe("");
});

test("does not clear lock while an actual open dialog layer exists", async () => {
  const openDialog = document.createElement("div");
  openDialog.setAttribute("role", "dialog");
  openDialog.setAttribute("data-state", "open");
  document.body.appendChild(openDialog);

  await act(async () => {
    root.render(<PointerEventsGuard />);
  });

  document.body.setAttribute("style", "pointer-events: none;");

  await act(async () => {
    jest.advanceTimersByTime(400);
  });

  expect(document.body.style.pointerEvents).toBe("none");
});

test("restores pointer events after open dialog closes", async () => {
  const openDialog = document.createElement("div");
  openDialog.setAttribute("role", "dialog");
  openDialog.setAttribute("data-state", "open");
  document.body.appendChild(openDialog);

  await act(async () => {
    root.render(<PointerEventsGuard />);
  });

  document.body.setAttribute("style", "pointer-events: none;");

  await act(async () => {
    jest.advanceTimersByTime(200);
  });
  expect(document.body.style.pointerEvents).toBe("none");

  openDialog.setAttribute("data-state", "closed");

  await act(async () => {
    jest.advanceTimersByTime(400);
  });

  expect(document.body.style.pointerEvents).toBe("");
});

test.each(["dialog", "alertdialog", "menu", "listbox"])("preserves an open %s lock through repeated checks", async (role) => {
  const layer = document.createElement("div");
  layer.setAttribute("role", role);
  layer.setAttribute("data-state", "open");
  document.body.appendChild(layer);
  document.body.style.pointerEvents = "none";
  await act(async () => { root.render(<PointerEventsGuard />); });
  await act(async () => { jest.advanceTimersByTime(3000); });
  expect(document.body.style.pointerEvents).toBe("none");
  layer.remove();
  await act(async () => { await Promise.resolve(); });
  await act(async () => { jest.advanceTimersByTime(350); });
  expect(document.body.style.pointerEvents).toBe("");
});

test("a leftover tooltip popper is not a modal lock owner", async () => {
  const wrapper = document.createElement("div");
  wrapper.setAttribute("data-radix-popper-content-wrapper", "");
  document.body.appendChild(wrapper);
  document.body.style.pointerEvents = "none";
  await act(async () => { root.render(<PointerEventsGuard />); });
  await act(async () => { jest.advanceTimersByTime(350); });
  expect(document.body.style.pointerEvents).toBe("");
});
