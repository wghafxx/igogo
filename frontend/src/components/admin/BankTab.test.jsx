import React, { act } from "react";
import { createRoot } from "react-dom/client";
import BankTab from "./BankTab";
import { adminApi } from "../../lib/api";
import { toast } from "sonner";

jest.mock("../../lib/api", () => ({
  adminApi: { bank: jest.fn(), poolTopup: jest.fn(), bankAdjust: jest.fn(), bankSettings: jest.fn(), bankReset: jest.fn() },
  formatMoney: (value) => String(value), parseServerDate: (value) => new Date(value),
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("../Logo", () => ({ RobuxIcon: () => null }));
jest.mock("@/lib/utils", () => jest.requireActual("../../lib/utils"), { virtual: true });

const byId = (id) => document.querySelector(`[data-testid="${id}"]`);
const click = async (id) => act(async () => byId(id).click());
const input = async (id, value) => act(async () => {
  const element = byId(id);
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
});
const confirmPin = async (pin = "1001") => {
  expect(byId("pin-dialog")).not.toBeNull();
  await input("pin-dialog-input", pin);
  await click("pin-dialog-confirm");
};
let root, container, data;

beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.resetAllMocks();
  data = { bank: 1000, commission_profit: 200, available_bank: 800, net: 700, pool: 500,
    liabilities: { total: 100, balances: 100, inventory: 0, pending_withdrawals: 0 },
    rtp: { rtp: .5, wagered: 100, paid: 50 }, settings: { rtp_target: .85 },
    games: { total: 10, wins: 5, forced_losses: 0, forced_by: {} }, ledger: [] };
  adminApi.bank.mockImplementation(async () => ({ ...data }));
  adminApi.poolTopup.mockImplementation(async (amount) => { data.pool += amount; return { ok: true, pool: data.pool }; });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<BankTab />));
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("shows commission separately from total bank and available funds", () => {
  expect(byId("bank-commission-profit").textContent).toContain("200");
  expect(byId("bank-commission-profit").textContent).toContain("20%");
  expect(byId("bank-available").textContent).toContain("800");
  expect(byId("bank-net").textContent).toContain("700");
  expect(byId("bank-net").textContent).toContain("Свободный остаток");
});

test("decrease sends a negative amount, refreshes pool and leaves commission intact", async () => {
  await input("bank-pool-amount", "200");
  await input("bank-pool-note", "Уменьшение бюджета");
  await click("bank-pool-decrease");
  expect(adminApi.poolTopup).not.toHaveBeenCalled();
  await confirmPin();
  expect(adminApi.poolTopup).toHaveBeenCalledWith(-200, "Уменьшение бюджета", "1001");
  expect(byId("bank-pool").textContent).toContain("300");
  expect(byId("bank-commission-profit").textContent).toContain("200");
});

test("increase still sends a positive amount", async () => {
  await input("bank-pool-amount", "150");
  await input("bank-pool-note", "Бюджет");
  await click("bank-pool-submit");
  await confirmPin();
  expect(adminApi.poolTopup).toHaveBeenCalledWith(150, "Бюджет", "1001");
  expect(byId("bank-pool").textContent).toContain("650");
});

test("cannot decrease beyond displayed free pool or submit without a reason", async () => {
  await input("bank-pool-amount", "100");
  expect(byId("bank-pool-decrease").disabled).toBe(true);
  await input("bank-pool-note", "Бюджет");
  await input("bank-pool-amount", "501");
  expect(byId("bank-pool-decrease").disabled).toBe(true);
  expect(byId("bank-pool-submit").disabled).toBe(false);
  await input("bank-pool-amount", "500");
  expect(byId("bank-pool-decrease").disabled).toBe(false);
});

test("a concurrent pool change error is visible and can be retried", async () => {
  await input("bank-pool-amount", "200");
  await input("bank-pool-note", "Бюджет");
  adminApi.poolTopup.mockRejectedValueOnce({ response: { data: { detail: "Недостаточно средств" } } });
  await click("bank-pool-decrease");
  await confirmPin();
  expect(toast.error).toHaveBeenCalledWith("Недостаточно средств");
  expect(byId("bank-pool-amount").value).toBe("200");
  await click("pin-dialog-cancel");
  expect(byId("bank-pool-decrease").disabled).toBe(false);
  await click("bank-pool-decrease");
  await confirmPin();
  expect(byId("bank-pool").textContent).toContain("300");
});

test("RTP change asks for confirmation with PIN", async () => {
  adminApi.bankSettings.mockResolvedValue({ rtp_target: .9 });
  await input("setting-rtp_target-slider", "90");
  await click("setting-rtp_target-save");
  expect(byId("pin-dialog-description").textContent).toContain("90%");
  await confirmPin();
  expect(adminApi.bankSettings).toHaveBeenCalledWith({ rtp_target: .9 }, "1001");
});

test("full bank reset requires PIN and calls the reset endpoint", async () => {
  adminApi.bankReset.mockImplementation(async () => { data = { ...data, bank: 0, pool: 0, commission_profit: 0, available_bank: 0 }; return { ok: true, bank: 0, pool: 0, commission_profit: 0 }; });
  await click("bank-reset-button");
  expect(byId("pin-dialog-title").textContent).toContain("ВЕСЬ банк");
  await confirmPin("1001");
  expect(adminApi.bankReset).toHaveBeenCalledWith("1001");
  expect(byId("bank-balance").textContent).toContain("0");
  expect(byId("bank-pool").textContent).toContain("0");
});
