import React, { act } from "react";
import { createRoot } from "react-dom/client";
import AdminPage from "./AdminPage";
import { adminApi, DEPOSIT_REJECTION_REASONS } from "../lib/api";

jest.mock("@/lib/utils", () => jest.requireActual("../lib/utils"), { virtual: true });
jest.mock("../lib/api", () => ({
  ...jest.requireActual("../lib/api"),
  getAdminToken: () => "test-admin",
  adminApi: { session: jest.fn(), deposits: jest.fn(), reject: jest.fn(), promos: jest.fn(), withdrawals: jest.fn(), withdrawalDone: jest.fn(), withdrawalCancel: jest.fn() },
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

test.each(Object.entries(DEPOSIT_REJECTION_REASONS))("requires explicit selection and submits %s", async (reason, label) => {
  await click("admin-reject-button");
  expect(adminApi.reject).not.toHaveBeenCalled();
  expect(byId("admin-reject-confirm").disabled).toBe(true);
  expect(document.querySelectorAll('input[name="deposit-rejection-reason"]:checked')).toHaveLength(0);
  expect(byId(`admin-reject-reason-${reason}`).parentElement.textContent).toBe(label);
  await click(`admin-reject-reason-${reason}`);
  expect(byId("admin-reject-confirm").disabled).toBe(false);
  await click("admin-reject-confirm");
  expect(adminApi.reject).toHaveBeenCalledTimes(1);
  expect(adminApi.reject).toHaveBeenCalledWith("deposit-1", reason);
  expect(byId("admin-reject-dialog")).toBeNull();
});

test("cancel does not reject and reopening clears the selected reason", async () => {
  await click("admin-reject-button");
  await click("admin-reject-reason-no_reason");
  await click("admin-reject-cancel");
  expect(adminApi.reject).not.toHaveBeenCalled();
  await click("admin-reject-button");
  expect(byId("admin-reject-confirm").disabled).toBe(true);
  expect(byId("admin-reject-reason-no_reason").checked).toBe(false);
});

test("failed rejection keeps the selected reason for retry", async () => {
  adminApi.reject.mockRejectedValueOnce(new Error("Network error"));
  await click("admin-reject-button");
  await click("admin-reject-reason-yellow_tag");
  await click("admin-reject-confirm");
  expect(byId("admin-reject-dialog")).not.toBeNull();
  expect(byId("admin-reject-reason-yellow_tag").checked).toBe(true);
  expect(byId("admin-reject-confirm").disabled).toBe(false);
});

test("promo tab loads promo statistics without requesting deposit statuses", async () => {
  adminApi.deposits.mockClear();
  await click("admin-tab-promos");
  expect(byId("promos-table").textContent).toContain("PELMEN");
  expect(byId("promo-unique-users").textContent).toBe("2");
  expect(adminApi.deposits).not.toHaveBeenCalled();
  await click("admin-refresh-button");
  expect(adminApi.promos).toHaveBeenCalledTimes(2);
});

test("custom deposit rejection requires text and submits the trimmed reason", async () => {
  await click("admin-reject-button");
  await click("admin-reject-reason-custom");
  await typeReason("admin-reject-custom-reason", " \n ");
  expect(byId("admin-reject-confirm").disabled).toBe(true);
  await typeReason("admin-reject-custom-reason", "  Не получили скин\nПроверьте получателя  ");
  await click("admin-reject-confirm");
  expect(adminApi.reject).toHaveBeenCalledWith("deposit-1", "Не получили скин\nПроверьте получателя");
});

test("withdrawal cancellation requires a reason and preserves it on a failed request", async () => {
  await click("admin-tab-withdrawals");
  await click("admin-withdrawal-cancel-button");
  expect(byId("admin-withdrawal-cancel-confirm").disabled).toBe(true);
  await typeReason("admin-withdrawal-cancel-reason", "  Нет подходящих скинов  ");
  adminApi.withdrawalCancel.mockRejectedValueOnce(new Error("Network error"));
  await click("admin-withdrawal-cancel-confirm");
  expect(byId("admin-withdrawal-cancel-reason").value).toBe("  Нет подходящих скинов  ");
  await click("admin-withdrawal-cancel-confirm");
  expect(adminApi.withdrawalCancel).toHaveBeenLastCalledWith("withdrawal-1", "Нет подходящих скинов");
  expect(byId("admin-cancel-withdrawal-dialog")).toBeNull();
  expect(adminApi.withdrawalDone).not.toHaveBeenCalled();
});

test("cancelled withdrawals show the reason and have no fulfilment actions", async () => {
  await click("admin-tab-withdrawals");
  adminApi.withdrawals.mockResolvedValue([{ id: "withdrawal-1", status: "cancelled", item: { name: "Skin", price: 100 }, created_at: "2026-09-12T00:00:00Z", cancellation_reason: "Нет подходящих скинов" }]);
  await click("admin-withdrawals-cancelled");
  expect(adminApi.withdrawals).toHaveBeenLastCalledWith("cancelled");
  expect(byId("admin-withdrawal-reason").textContent).toContain("Нет подходящих скинов");
  expect(byId("admin-withdrawal-done-button")).toBeNull();
  expect(byId("admin-withdrawal-cancel-button")).toBeNull();
});
