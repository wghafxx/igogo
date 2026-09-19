import React, { act } from "react";
import { createRoot } from "react-dom/client";
import XrocketTopUp from "./XrocketTopUp";
import { api } from "../../lib/api";
import { useAuth } from "../../hooks/useAuth";
import { toast } from "sonner";
import { xrocketRu } from "../../lib/xrocket-i18n";
import { openXrocketPayment } from "../../lib/payment-navigation";

jest.mock("../../lib/api", () => ({
  api: { xrocketInfo: jest.fn(), xrocketInvoices: jest.fn(), createXrocketInvoice: jest.fn(), xrocketInvoice: jest.fn(), refreshXrocketInvoice: jest.fn() },
  formatMoney: (n) => Number(n).toFixed(2), parseServerDate: (d) => new Date(d),
}));
jest.mock("../../hooks/useAuth", () => ({ useAuth: jest.fn() }));
jest.mock("../../lib/payment-navigation", () => ({ openXrocketPayment: jest.fn() }));
jest.mock("../../lib/i18n", () => ({ useLang: () => ({ t: (key) => jest.requireActual("../../lib/xrocket-i18n").xrocketRu[key] || key, lang: "ru" }) }));
jest.mock("../TopUpModal", () => ({ PromoInput: () => <div data-testid="promo-input" /> }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));

const byId = (id) => document.querySelector(`[data-testid="${id}"]`);
const click = async (id) => act(async () => { byId(id).click(); });
const input = async (value) => act(async () => {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(byId("xrocket-amount"), value);
  byId("xrocket-amount").dispatchEvent(new Event("input", { bubbles: true }));
});
const invoice = (status = "awaiting_payment") => ({ id: "xrocket:one", status, amount_rub: 35, currency: "USDT", quoted_rap: 70,
  invoice_url: "https://t.me/xRocket?start=test", expires_at: "2026-09-13T12:00:00Z" });
let root, container, auth, onChanged;
const render = async () => act(async () => { root.render(<XrocketTopUp onChanged={onChanged} />); });

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.resetAllMocks();
  jest.useFakeTimers();
  global.crypto = { randomUUID: jest.fn(() => "request-one") };
  auth = { authUser: { session_id: "discord_1", promo_bonus: 0 }, openAuth: jest.fn(), refresh: jest.fn() };
  useAuth.mockImplementation(() => auth);
  api.xrocketInfo.mockResolvedValue({ enabled: true, min_rub: 35, max_rub: 1000000, rap_rub_rate: .5,
    currencies: ["GRAM", "USDT", "USDC", "BTC", "ETH", "TRX", "SOL", "BNB"] });
  api.xrocketInvoices.mockResolvedValue([]);
  api.createXrocketInvoice.mockResolvedValue(invoice());
  api.xrocketInvoice.mockResolvedValue(invoice());
  api.refreshXrocketInvoice.mockResolvedValue(invoice());
  onChanged = jest.fn();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => { root.unmount(); });
  container.remove();
  jest.useRealTimers();
});

test("minimum, full credit, provider fee and all eight currencies", async () => {
  await render();
  expect(byId("xrocket-amount").value).toBe("35");
  expect(byId("xrocket-credit").textContent).toContain("70.00");
  expect(document.querySelectorAll('[data-testid^="xrocket-currency-"]')).toHaveLength(8);
  expect(byId("xrocket-fee").textContent).toBe(xrocketRu["xrocket.provider_fee"]);
  await input("34.99");
  expect(byId("xrocket-pay").disabled).toBe(true);
  await click("xrocket-pay");
  expect(api.createXrocketInvoice).not.toHaveBeenCalled();
  await input("35,50");
  await click("xrocket-currency-BTC");
  await click("xrocket-pay");
  expect(api.createXrocketInvoice).toHaveBeenCalledWith({ request_id: "request-one", amount_rub: 35.5, currency: "BTC" });
  expect(byId("xrocket-open").getAttribute("href")).toBe(invoice().invoice_url);
  expect(openXrocketPayment).toHaveBeenCalledWith(invoice().invoice_url);
});

test("promo adds ten percent to the full amount", async () => {
  auth.authUser = { ...auth.authUser, promo_bonus: .1, promo_code: "PELMEN" };
  await render();
  expect(byId("xrocket-credit").textContent).toContain("77.00");
  expect(container.textContent).toContain("PELMEN");
});

test("timeout retry uses the same request ID", async () => {
  api.createXrocketInvoice.mockRejectedValueOnce(new Error("timeout"));
  await render();
  await click("xrocket-pay");
  expect(document.querySelector('[role="alert"]')).not.toBeNull();
  await click("xrocket-pay");
  expect(api.createXrocketInvoice).toHaveBeenCalledTimes(2);
  expect(api.createXrocketInvoice.mock.calls[0][0]).toEqual(api.createXrocketInvoice.mock.calls[1][0]);
  expect(global.crypto.randomUUID).toHaveBeenCalledTimes(1);
});

test("local polling confirms payment and refreshes balance once", async () => {
  await render();
  await click("xrocket-pay");
  api.xrocketInvoice.mockResolvedValue({ ...invoice("confirmed"), credited: 70 });
  await act(async () => { jest.advanceTimersByTime(5000); });
  expect(api.xrocketInvoice).toHaveBeenCalledWith("xrocket:one");
  expect(api.refreshXrocketInvoice).not.toHaveBeenCalled();
  expect(auth.refresh).toHaveBeenCalledTimes(1);
  expect(toast.success).toHaveBeenCalledTimes(1);
  expect(byId("xrocket-open")).toBeNull();
  expect(byId("xrocket-status").textContent).toBe(xrocketRu["xrocket.confirmed"]);
  await act(async () => { jest.advanceTimersByTime(10000); });
  expect(api.xrocketInvoice).toHaveBeenCalledTimes(1);
});

test("history resumes pending invoice and manual check handles expiry", async () => {
  api.xrocketInvoices.mockResolvedValue([invoice()]);
  await render();
  await click("xrocket-history-item");
  expect(byId("xrocket-invoice")).not.toBeNull();
  expect(api.createXrocketInvoice).not.toHaveBeenCalled();
  api.refreshXrocketInvoice.mockResolvedValue(invoice("expired"));
  await click("xrocket-check");
  expect(byId("xrocket-status").textContent).toBe(xrocketRu["xrocket.expired"]);
  expect(byId("xrocket-open")).toBeNull();
  expect(auth.refresh).not.toHaveBeenCalled();
});

test("disabled provider prevents invoices and guest opens login", async () => {
  api.xrocketInfo.mockResolvedValue({ enabled: false, currencies: ["USDT"] });
  await render();
  expect(byId("xrocket-pay").disabled).toBe(true);
  expect(container.textContent).toContain(xrocketRu["xrocket.unavailable"]);
  auth.authUser = null;
  await render();
  await click("xrocket-pay");
  expect(auth.openAuth).toHaveBeenCalledTimes(1);
  expect(api.createXrocketInvoice).not.toHaveBeenCalled();
});

test("switching account discards a late invoice response", async () => {
  let resolve;
  api.createXrocketInvoice.mockReturnValue(new Promise((r) => { resolve = r; }));
  await render();
  await click("xrocket-pay");
  auth.authUser = { session_id: "discord_2" };
  await render();
  await act(async () => { resolve(invoice()); });
  expect(byId("xrocket-invoice")).toBeNull();
  expect(openXrocketPayment).not.toHaveBeenCalled();
});

test("failed history row offers a retry of the original request and redirects", async () => {
  api.xrocketInvoices.mockResolvedValue([{ ...invoice("payment_error"), invoice_url: null, error_message: "Попробуйте ещё раз" }]);
  await render();
  await click("xrocket-history-item");
  expect(container.textContent).toContain("Попробуйте ещё раз");
  expect(byId("xrocket-open")).toBeNull();
  await click("xrocket-retry-invoice");
  expect(api.createXrocketInvoice).toHaveBeenCalledWith({ request_id: "one", amount_rub: 35, currency: "USDT" });
  expect(openXrocketPayment).toHaveBeenCalledTimes(1);
});

test("a delayed payment link redirects once and never shows an unpaid link while creating", async () => {
  api.createXrocketInvoice.mockResolvedValue({ ...invoice("creating"), invoice_url: null });
  await render();
  await click("xrocket-pay");
  expect(openXrocketPayment).not.toHaveBeenCalled();
  expect(byId("xrocket-open")).toBeNull();
  expect(byId("xrocket-status").textContent).toBe(xrocketRu["xrocket.preparing"]);
  await act(async () => { jest.advanceTimersByTime(5000); });
  expect(openXrocketPayment).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(5000); });
  expect(openXrocketPayment).toHaveBeenCalledTimes(1);
});
