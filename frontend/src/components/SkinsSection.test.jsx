import React, { act, useState } from "react";
import { createRoot } from "react-dom/client";
import SkinsSection from "./SkinsSection";
import { api } from "../lib/api";
import { LangProvider } from "../lib/i18n";

jest.mock("@/lib/utils", () => jest.requireActual("../lib/utils"), { virtual: true });
jest.mock("../hooks/useAuth", () => ({ useAuth: () => ({ authUser: { session_id: "player" }, openAuth: jest.fn(), setAuthUser: jest.fn() }) }));
jest.mock("../lib/api", () => ({ ...jest.requireActual("../lib/api"), api: { shop: jest.fn(), buySkins: jest.fn() } }));
jest.mock("../lib/sound", () => ({ playTick: jest.fn() }));

const skins = Array.from({ length: 52 }, (_, i) => ({ id: `skin-${i}`, uid: `owned-${i}`, type: "AWP", name: `Skin ${i}`, price: 100 + i, rarity: "pink" }));
const byId = (id) => document.querySelector(`[data-testid="${id}"]`);
const click = async (id) => act(async () => { byId(id).click(); });
const load = async () => act(async () => { jest.advanceTimersByTime(250); });
let root;
let container;

function Harness({ inventory = skins }) {
  const [selected, setSelected] = useState([]);
  const [target, setTarget] = useState(null);
  const [balance, setBalance] = useState(1000);
  return <LangProvider><SkinsSection user={{ session_id: "player", balance, skins: inventory }} onPurchased={(user) => setBalance(user.balance)} betSkins={selected} onToggleBetSkin={(skin) => setSelected((current) => [...current, skin])} target={target} onSelectTarget={setTarget} /></LangProvider>;
}

beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  global.crypto = require("crypto").webcrypto;
  localStorage.setItem("bloxgrade_lang", "ru");
  window.innerWidth = 1280;
  jest.useFakeTimers();
  api.shop.mockReset();
  api.buySkins.mockReset();
  api.buySkins.mockResolvedValue({ user: { session_id: "player", balance: 699, skins: [] }, count: 3 });
  api.shop.mockImplementation(async ({ page, limit, q }) => {
    const filtered = q ? skins.filter((skin) => skin.name.includes(q)) : skins;
    return { items: filtered.slice((page - 1) * limit, page * limit), page, total: filtered.length };
  });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<Harness />); });
  await load();
});

afterEach(async () => {
  await act(async () => { root.unmount(); });
  container.remove();
  jest.useRealTimers();
});

test("both lists have independent pages and retain selected skins", async () => {
  expect(document.querySelectorAll('[data-testid^="bet-card-"]')).toHaveLength(25);
  expect(document.querySelectorAll('[data-testid^="shop-skin-"]')).toHaveLength(25);
  await click("bet-card-owned-0");
  await click("shop-skin-skin-0");
  await click("inventory-pagination-page-2");
  expect(byId("bet-card-owned-0")).toBeNull();
  expect(byId("bet-card-owned-25")).not.toBeNull();
  expect(byId("shop-skin-skin-0")).not.toBeNull();
  await click("shop-pagination-page-3");
  await load();
  expect(api.shop).toHaveBeenLastCalledWith({ sort: "price_desc", page: 3, limit: 25 });
  expect(document.querySelectorAll('[data-testid^="shop-skin-"]')).toHaveLength(2);
  expect(byId("shop-grid").firstElementChild.children).toHaveLength(25);
  await click("inventory-pagination-page-1");
  await click("shop-pagination-page-1");
  await load();
  expect(byId("bet-card-owned-0").getAttribute("aria-pressed")).toBe("true");
  expect(byId("shop-skin-skin-0").getAttribute("aria-pressed")).toBe("true");
});

test("search from a later page resets the catalog to page one", async () => {
  await click("shop-pagination-page-3");
  await load();
  await act(async () => {
    const input = byId("search-input");
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, "Skin 31");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await load();
  expect(api.shop).toHaveBeenLastCalledWith({ sort: "price_desc", page: 1, limit: 25, q: "Skin 31" });
  expect(byId("shop-skin-skin-31")).not.toBeNull();
  expect(byId("shop-pagination-page-1").getAttribute("aria-current")).toBe("page");
  expect(byId("shop-grid").firstElementChild.children).toHaveLength(25);
});

test("inventory returns to an available page when skins are removed", async () => {
  await click("inventory-pagination-page-3");
  await act(async () => { root.render(<Harness inventory={skins.slice(0, 26)} />); });
  expect(byId("inventory-pagination-page-2").getAttribute("aria-current")).toBe("page");
  expect(byId("bet-card-owned-25")).not.toBeNull();
  expect(document.querySelectorAll('[data-testid^="bet-card-"]')).toHaveLength(1);
  expect(byId("inventory-grid").firstElementChild.children).toHaveLength(25);
});

test("resizing keeps five rows in both lists and resets to an available page", async () => {
  await click("inventory-pagination-page-3");
  await click("shop-pagination-page-3");
  await load();
  for (const [width, size] of [[800, 20], [390, 15], [1280, 25]]) {
    await act(async () => { window.innerWidth = width; window.dispatchEvent(new Event("resize")); });
    await load();
    expect(api.shop).toHaveBeenLastCalledWith({ sort: "price_desc", page: 1, limit: size });
    expect(byId("inventory-grid").firstElementChild.children).toHaveLength(size);
    expect(byId("shop-grid").firstElementChild.children).toHaveLength(size);
    expect(byId("inventory-pagination-page-1").getAttribute("aria-current")).toBe("page");
  }
});

test("store cart buys selected quantities at catalog prices and returns to inventory", async () => {
  await click("inventory-tab-store");
  await load();
  await click("store-skin-skin-0");
  await click("store-skin-skin-0");
  await click("store-skin-skin-1");
  expect(byId("store-cart-count").textContent).toBe("3");
  expect(byId("store-shop-grid").firstElementChild.children).toHaveLength(25);
  await click("store-cart-button");
  expect(byId("store-buy").disabled).toBe(false);
  await click("store-buy");
  expect(api.buySkins).toHaveBeenCalledTimes(1);
  expect(api.buySkins).toHaveBeenCalledWith({
    request_id: expect.stringMatching(/^[0-9a-f-]{36}$/), expected_total: 301,
    items: [{ id: "skin-0", quantity: 2 }, { id: "skin-1", quantity: 1 }],
  });
  expect(byId("store-cart-dialog")).toBeNull();
  expect(byId("store-cart-count")).toBeNull();
  expect(byId("inventory-tab-mine").getAttribute("aria-selected")).toBe("true");
});

test("insufficient balance shows the shortage and disables purchase", async () => {
  api.shop.mockResolvedValueOnce({ items: [{ ...skins[0], price: 1500 }], total: 1, page: 1 });
  await click("inventory-tab-store");
  await load();
  await click("store-skin-skin-0");
  await click("store-cart-button");
  expect(byId("store-shortage").textContent).toContain("500,00");
  expect(byId("store-buy").disabled).toBe(true);
  expect(byId("store-topup")).not.toBeNull();
  expect(api.buySkins).not.toHaveBeenCalled();
});

test("an interrupted purchase retries the same request without changing the cart", async () => {
  api.buySkins.mockRejectedValueOnce(new Error("connection lost"));
  await click("inventory-tab-store");
  await load();
  await click("store-skin-skin-0");
  await click("store-cart-button");
  await click("store-buy");
  expect(byId("store-cart-clear").disabled).toBe(true);
  expect(byId("store-buy").textContent).toBe("Проверить покупку");
  await click("store-buy");
  expect(api.buySkins).toHaveBeenCalledTimes(2);
  expect(api.buySkins.mock.calls[1][0]).toEqual(api.buySkins.mock.calls[0][0]);
});
