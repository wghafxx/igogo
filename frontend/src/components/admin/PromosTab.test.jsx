import React, { act } from "react";
import { createRoot } from "react-dom/client";
import PromosTab from "./PromosTab";
import { adminApi } from "../../lib/api";

jest.mock("@/lib/utils", () => jest.requireActual("../../lib/utils"), { virtual: true });
jest.mock("../../lib/api", () => ({ adminApi: { promos: jest.fn(), createPromo: jest.fn(), updatePromo: jest.fn(), deletePromo: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const byId = (id) => document.querySelector(`[data-testid="${id}"]`);
const click = async (element) => act(async () => { (typeof element === "string" ? byId(element) : element).click(); });
const setInput = async (id, value) => act(async () => {
  const input = byId(id);
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
});
let root;
let container;
let promos;

beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.resetAllMocks();
  promos = [{ id: "pelmen", code: "PELMEN", percent: 10, unique_users: 7 }, { id: "inka", code: "INKAB00M", percent: 9, unique_users: 2 }];
  adminApi.promos.mockImplementation(async () => [...promos]);
  adminApi.createPromo.mockResolvedValue({});
  adminApi.updatePromo.mockResolvedValue({});
  adminApi.deletePromo.mockResolvedValue({ ok: true });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<PromosTab />); });
});

afterEach(async () => {
  await act(async () => { root.unmount(); });
  container.remove();
});

test("shows unique people and supports creating a fractional bonus", async () => {
  expect(byId("promo-row-pelmen").textContent).toContain("+10%");
  expect(byId("promo-row-pelmen").querySelector('[data-testid="promo-unique-users"]').textContent).toBe("7");
  await click("promo-add");
  await setInput("promo-code", "NEW_PROMO-1");
  await setInput("promo-percent", "12.34");
  expect(byId("promo-code").checkValidity()).toBe(true);
  await click("promo-save");
  expect(adminApi.createPromo).toHaveBeenCalledWith({ code: "NEW_PROMO-1", percent: 12.34 });
  expect(byId("promo-editor")).toBeNull();
});

test("editing submits the stable ID, updated name and percent", async () => {
  await click(document.querySelector('[aria-label="Редактировать PELMEN"]'));
  expect(byId("promo-code").value).toBe("PELMEN");
  expect(byId("promo-percent").value).toBe("10");
  await setInput("promo-code", "DUMPLING");
  await setInput("promo-percent", "9.5");
  promos = [{ id: "pelmen", code: "DUMPLING", percent: 9.5, unique_users: 7 }];
  await click("promo-save");
  expect(adminApi.updatePromo).toHaveBeenCalledWith("pelmen", { code: "DUMPLING", percent: 9.5 });
  expect(byId("promo-row-pelmen").textContent).toContain("DUMPLING");
  expect(byId("promo-unique-users").textContent).toBe("7");
});

test("duplicate error preserves entered values for correction", async () => {
  adminApi.createPromo.mockRejectedValueOnce({ response: { data: { detail: "Промокод с таким названием уже существует" } } });
  await click("promo-add");
  await setInput("promo-code", "PELMEN");
  await click("promo-save");
  expect(document.querySelector('[role="alert"]').textContent).toContain("уже существует");
  expect(byId("promo-code").value).toBe("PELMEN");
  expect(byId("promo-save").disabled).toBe(false);
  await setInput("promo-code", "NEW");
  await click("promo-save");
  expect(byId("promo-editor")).toBeNull();
});

test("invalid names and percentages cannot be submitted", async () => {
  await click("promo-add");
  await setInput("promo-code", "two words");
  expect(byId("promo-code").checkValidity()).toBe(false);
  await click("promo-save");
  expect(adminApi.createPromo).not.toHaveBeenCalled();
  await setInput("promo-code", "valid");
  for (const percent of ["0", "-1", "50.01", "1.234", ""]) {
    await setInput("promo-percent", percent);
    expect(byId("promo-percent").checkValidity()).toBe(false);
  }
});

test("deletion requires its dialog action and failed requests can be retried", async () => {
  await click(document.querySelector('[aria-label="Удалить PELMEN"]'));
  expect(adminApi.deletePromo).not.toHaveBeenCalled();
  adminApi.deletePromo.mockRejectedValueOnce(new Error("Offline"));
  await click("promo-delete-confirm");
  expect(byId("promo-delete-dialog")).not.toBeNull();
  expect(document.querySelector('[role="alert"]').textContent).toContain("Не удалось удалить");
  promos = promos.filter((p) => p.id !== "pelmen");
  await click("promo-delete-confirm");
  expect(adminApi.deletePromo).toHaveBeenLastCalledWith("pelmen");
  expect(byId("promo-delete-dialog")).toBeNull();
  expect(byId("promo-row-pelmen")).toBeNull();
});

test("empty list still allows creating a promo", async () => {
  promos = [];
  await act(async () => { root.render(<PromosTab refreshKey={1} />); });
  expect(byId("promos-tab").textContent).toContain("Промокодов пока нет");
  await click("promo-add");
  expect(byId("promo-editor")).not.toBeNull();
});
