import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PromoInput } from "./TopUpModal";
import { api } from "../lib/api";
import { useAuth } from "../hooks/useAuth";
import { toast } from "sonner";

jest.mock("@/lib/utils", () => jest.requireActual("../lib/utils"), { virtual: true });
jest.mock("../lib/api", () => ({
  api: { applyPromo: jest.fn() },
  pct: (f) => String(Math.round(Number(f || 0) * 10000) / 100).replace(".", ","),
  formatMoney: (n) => new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(n) || 0),
}));
jest.mock("../hooks/useAuth", () => ({ useAuth: jest.fn() }));
jest.mock("../hooks/useSessionCtx", () => ({ useSessionCtx: jest.fn(() => null) }));
jest.mock("../lib/i18n", () => ({ useLang: () => ({ t: (k) => k }) }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const { useSessionCtx } = require("../hooks/useSessionCtx");

const byId = (id) => document.querySelector(`[data-testid="${id}"]`);
const setCode = async (value) => act(async () => {
  const input = byId("promo-input");
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
});
const clickApply = async () => act(async () => { byId("promo-apply-button").click(); });

let root;
let container;
let authUser;
let setAuthUser;
let setUser;

beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.resetAllMocks();
  authUser = { session_id: "discord_1", balance: 0, promo_code: "PELMEN", promo_bonus: 0.1 };
  setAuthUser = jest.fn((u) => { authUser = typeof u === "function" ? u(authUser) : u; });
  setUser = jest.fn();
  useAuth.mockImplementation(() => ({ authUser, setAuthUser }));
  useSessionCtx.mockImplementation(() => ({ setUser }));
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<PromoInput />); });
});

afterEach(async () => {
  await act(async () => { root.unmount(); });
  container.remove();
});

test("percent promo shows percent and updates both auth and session balance", async () => {
  api.applyPromo.mockResolvedValue({ session_id: "discord_1", balance: 0, promo_code: "PELMEN", promo_bonus: 0.1 });
  await setCode("PELMEN");
  await clickApply();
  expect(setAuthUser).toHaveBeenCalled();
  expect(setUser).toHaveBeenCalled();
  expect(byId("promo-bonus").textContent).toContain("%");
  expect(byId("promo-gift")).toBeNull();
});

test("RAP gift shows credited amount, not percent, and syncs session", async () => {
  api.applyPromo.mockResolvedValue({
    session_id: "discord_1", balance: 100.5, promo_code: "PELMEN", promo_bonus: 0.1,
    gift_type: "rap_fixed", gift_amount: 100.5, gift_already_received: false,
  });
  await setCode("GIFT100");
  await clickApply();
  expect(setAuthUser).toHaveBeenCalled();
  expect(setUser).toHaveBeenCalled();
  const gift = byId("promo-gift");
  expect(gift).not.toBeNull();
  expect(gift.textContent).toContain("100");
  expect(gift.textContent).toContain("RAP");
  expect(gift.textContent).not.toContain("%");
});

test("repeated RAP gift shows already-received without percent", async () => {
  api.applyPromo.mockResolvedValue({
    session_id: "discord_1", balance: 100.5, promo_code: null, promo_bonus: 0,
    gift_type: "rap_fixed", gift_amount: 100.5, gift_already_received: true,
  });
  await setCode("GIFT100");
  await clickApply();
  const gift = byId("promo-gift");
  expect(gift).not.toBeNull();
  expect(toast.success).toHaveBeenCalled();
  expect(gift.textContent).not.toContain("%");
});
