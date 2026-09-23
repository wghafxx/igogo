import React, { act } from "react";
import { createRoot } from "react-dom/client";
import AdminPage from "./AdminPage";
import { adminApi, DEPOSIT_REJECTION_REASONS } from "../lib/api";

jest.mock("@/lib/utils", () => jest.requireActual("../lib/utils"), { virtual: true });
jest.mock("../lib/api", () => ({
  ...jest.requireActual("../lib/api"),
  getAdminToken: () => "test-admin",
  adminApi: { session: jest.fn(), deposits: jest.fn(), reject: jest.fn(), promos: jest.fn(), withdrawals: jest.fn(), withdrawalDone: jest.fn(), withdrawalCancel: jest.fn(),
    chatSummary: jest.fn(), chats: jest.fn(), search: jest.fn(), chatMessages: jest.fn(), telegramStatus: jest.fn(() => Promise.resolve({ enabled: false })) },
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("../components/admin/BankTab", () => () => null);
jest.mock("../components/admin/PlayersTab", () => () => null);
jest.mock("../components/admin/RainTab", () => () => null);
jest.mock("../components/admin/DepositAllocationPreview", () => ({ DepositAllocationPreview: () => null }));

const byId = (id) => document.querySelector(`[data-testid="${id}"]`);
const click = async (id) => act(async () => { byId(id).click(); });
const typeReason = async (id, text) => act(async () => {
  const input = byId(id);
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(input, text);
  input.dispatchEvent(new Event("input", { bubbles: true }));
});
let root;
let container;

beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.clearAllMocks();
  adminApi.session.mockResolvedValue({ ok: true });
  adminApi.chatSummary.mockResolvedValue({ open: 0, active: 0, unread: 0 });
  adminApi.chats.mockResolvedValue({ items: [], has_more: false, total: 0 });
  adminApi.search.mockResolvedValue([]);
  adminApi.telegramStatus.mockResolvedValue({ enabled: false });
  adminApi.promos.mockResolvedValue([{ id: "pelmen", code: "PELMEN", percent: 10, unique_users: 2 }]);
  adminApi.deposits.mockResolvedValue([{
    id: "deposit-1", nickname: "Player", status: "pending", expected_rap: 100,
    description: "Skin", created_at: "2026-09-12T00:00:00Z",
  }]);
  adminApi.reject.mockResolvedValue({ ok: true });
  adminApi.withdrawals.mockResolvedValue([{ id: "withdrawal-1", status: "pending", user: { nickname: "Player" }, item: { name: "Skin", price: 100 }, created_at: "2026-09-12T00:00:00Z" }]);
  adminApi.withdrawalCancel.mockResolvedValue({ ok: true });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<AdminPage />); });
});

afterEach(async () => {
  await act(async () => { root.unmount(); });
  container.remove();
});

// Deposit rejection / withdrawal dialogs moved from this page into the chat player panel (PlayerPanel);
// the old page-level cases were removed with that UI.
test("promo tab loads promo statistics without requesting deposit statuses", async () => {
  adminApi.deposits.mockClear();
  await click("admin-tab-promos");
  expect(byId("promos-table").textContent).toContain("PELMEN");
  expect(byId("promo-unique-users").textContent).toBe("2");
  expect(adminApi.deposits).not.toHaveBeenCalled();
  await click("admin-refresh-button");
  expect(adminApi.promos).toHaveBeenCalledTimes(2);
});
