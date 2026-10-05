import React, { act } from "react";
import { createRoot } from "react-dom/client";
import StaffPage from "./StaffPage";
import { useAuth } from "../hooks/useAuth";
import { staffApi } from "../lib/staff-api";
import { playRequestSound } from "../lib/request-sound";

jest.mock("@/lib/utils", () => jest.requireActual("../lib/utils"), { virtual: true });
jest.mock("../hooks/useAuth", () => ({ useAuth: jest.fn() }));
jest.mock("../lib/staff-api", () => ({ ...jest.requireActual("../lib/staff-api"),
  staffApi: { me: jest.fn(), chats: jest.fn(), chatSummary: jest.fn() } }));
jest.mock("../lib/request-sound", () => ({ playRequestSound: jest.fn(), prepareRequestSound: jest.fn() }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
let root;
let container;
const click = (id) => act(async () => { container.querySelector(`[data-testid="${id}"]`).click(); });
beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.useFakeTimers();
  jest.resetAllMocks();
  localStorage.clear();
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
  useAuth.mockReturnValue({ authUser: { session_id: "staff-1" }, loading: false });
  staffApi.me.mockResolvedValue({ staff: { roblox_nick: "Receiver" }, shift: null, today: null });
  staffApi.chats.mockResolvedValue({ items: [], has_more: false, total: 0 });
  staffApi.chatSummary.mockResolvedValue({ open: 1, active: 0, unread: 1, request_cursor: "2026-10-03T00:00:00Z" });
  playRequestSound.mockResolvedValue(true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<StaffPage />); });
});
afterEach(async () => {
  await act(async () => { root.unmount(); });
  container.remove();
  jest.useRealTimers();
});

test("staff alerts survive section changes and only new requests play", async () => {
  expect(playRequestSound).not.toHaveBeenCalled();
  staffApi.chatSummary.mockResolvedValue({ open: 1, active: 0, unread: 20, request_cursor: "2026-10-03T00:00:00Z" });
  await act(async () => { jest.advanceTimersByTime(4000); });
  expect(playRequestSound).not.toHaveBeenCalled();
  staffApi.chatSummary.mockResolvedValue({ open: 1, active: 0, unread: 20, request_cursor: "2026-10-03T00:00:01Z" });
  await act(async () => { jest.advanceTimersByTime(4000); });
  expect(playRequestSound).toHaveBeenCalledTimes(1);
  await click("staff-tab-stats");
  await act(async () => { jest.advanceTimersByTime(4000); });
  expect(playRequestSound).toHaveBeenCalledTimes(1);
  staffApi.chatSummary.mockResolvedValue({ open: 1, active: 0, unread: 20, request_cursor: "2026-10-03T00:00:02Z" });
  await act(async () => { jest.advanceTimersByTime(4000); });
  expect(playRequestSound).toHaveBeenCalledTimes(2);
  await click("staff-tab-chats");
  Object.defineProperty(document, "hidden", { configurable: true, value: true });
  staffApi.chatSummary.mockResolvedValue({ open: 1, active: 0, unread: 20, request_cursor: "2026-10-03T00:00:03Z" });
  await act(async () => { jest.advanceTimersByTime(4000); });
  expect(playRequestSound).toHaveBeenCalledTimes(3);
});
