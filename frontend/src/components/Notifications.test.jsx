import React, { act } from "react";
import { createRoot } from "react-dom/client";
import Notifications from "./Notifications";
import { api, NOTIFICATIONS_CHANGED } from "../lib/api";
import { LangProvider } from "../lib/i18n";
import { toast } from "sonner";

jest.mock("@/lib/utils", () => jest.requireActual("../lib/utils"), { virtual: true });
jest.mock("../lib/api", () => ({ ...jest.requireActual("../lib/api"), api: { notifications: jest.fn(), readNotifications: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { error: jest.fn() } }));
// Popover placement/focus is covered in the real-browser check. Keep these tests
// focused on asynchronous feed state without JSDOM's layout/focus machinery.
jest.mock("./ui/popover", () => {
  const React = require("react");
  const Context = React.createContext(() => {});
  return {
    Popover: ({ children, onOpenChange }) => <Context.Provider value={onOpenChange}>{children}</Context.Provider>,
    PopoverTrigger: ({ children }) => {
      const change = React.useContext(Context);
      return React.cloneElement(children, { onClick: () => change(true) });
    },
    PopoverContent: ({ children, align, sideOffset, ...props }) => <div {...props}>{children}</div>,
  };
});

const initial = [
  { id: "w:cancelled", type: "withdrawal_cancelled", amount: 75, item_name: "Typhon", reason: "Скин недоступен", created_at: "2026-09-14T12:00:00Z", read: false },
  { id: "d:confirmed", type: "deposit_confirmed", amount: 120, created_at: "2026-09-14T11:00:00Z", read: false },
];
const byId = (id) => document.querySelector(`[data-testid="${id}"]`);
const click = async (id) => act(async () => { byId(id).click(); });
let root, container;

beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
  localStorage.setItem("bloxgrade_lang", "ru");
  jest.useFakeTimers();
  jest.clearAllMocks();
  api.notifications.mockReset().mockResolvedValue({ items: initial });
  api.readNotifications.mockReset().mockResolvedValue({ ok: true });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<LangProvider><Notifications /></LangProvider>); });
});

afterEach(async () => {
  await act(async () => { root.unmount(); });
  container.remove();
  jest.useRealTimers();
});

test("shows real operation details, cancellation reasons, and unread count", async () => {
  expect(byId("notifications-badge").textContent).toBe("2");
  await click("notifications-button");
  const panel = byId("notifications-popover");
  expect(panel.textContent).toContain("Вывод отменён");
  expect(panel.textContent).toContain("Скин недоступен");
  expect(panel.textContent).toContain("Typhon");
  expect(panel.textContent).toContain("Пополнение зачислено");
  expect(panel.textContent).toContain("120,00 RAP");
  expect(panel.textContent).not.toContain("Нет новых уведомлений");
});

test("refreshes for operations and polling without duplicating entries", async () => {
  const next = { id: "d:cancelled", type: "deposit_cancelled", created_at: "2026-09-14T12:01:00Z", read: false };
  api.notifications.mockResolvedValue({ items: [next, ...initial] });
  await act(async () => { window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED)); });
  await click("notifications-button");
  await act(async () => { jest.advanceTimersByTime(15000); });
  expect(document.querySelectorAll('[data-testid="notification-item"]')).toHaveLength(3);
  expect(byId("notifications-badge").textContent).toBe("3");
  expect(api.notifications).toHaveBeenCalledTimes(4);
});

test("mark all read persists the visible cutoff and leaves newer arrivals unread", async () => {
  await click("notifications-button");
  let finish;
  api.readNotifications.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  await click("notifications-read-all");
  const next = { id: "new", type: "deposit_requested", created_at: "2026-09-14T12:01:00Z", read: false };
  api.notifications.mockResolvedValue({ items: [next, ...initial] });
  await act(async () => { window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED)); });
  await act(async () => { finish({ ok: true }); });
  expect(api.readNotifications).toHaveBeenCalledWith(initial[0].created_at);
  expect(byId("notifications-badge").textContent).toBe("1");
  // A response already in flight before the read cannot undo the local marker.
  await act(async () => { window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED)); });
  expect(byId("notifications-badge").textContent).toBe("1");
});

test("a failed refresh preserves history and a failed read preserves unread state", async () => {
  api.notifications.mockRejectedValue(new Error("offline"));
  await click("notifications-button");
  expect(byId("notifications-popover").textContent).toContain("Не удалось загрузить уведомления");
  expect(document.querySelectorAll('[data-testid="notification-item"]')).toHaveLength(2);
  api.readNotifications.mockRejectedValue(new Error("offline"));
  await click("notifications-read-all");
  expect(toast.error).toHaveBeenCalled();
  expect(byId("notifications-badge").textContent).toBe("2");
});
