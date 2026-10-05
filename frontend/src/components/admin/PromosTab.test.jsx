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
  expect(adminApi.createPromo).toHaveBeenCalledWith({ code: "NEW_PROMO-1", percent: 12.34, is_media: false, media_percent: 0 });
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
  expect(adminApi.updatePromo).toHaveBeenCalledWith("pelmen", { code: "DUMPLING", percent: 9.5, is_media: false, media_percent: 0 });
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

test("media checkbox presets launch terms and saves an explicit media mark", async () => {
  await click("promo-add");
  await setInput("promo-code", "STREAMER");
  expect(byId("promo-is-media").checked).toBe(false);
  expect(byId("promo-media-percent")).toBeNull();
  await click("promo-is-media");
  expect(byId("promo-percent").value).toBe("7.5");
  expect(byId("promo-media-percent").value).toBe("13");
  expect(byId("promo-media-terms").textContent).toContain("3\u00a0250 ₽");
  await click("promo-save");
  expect(adminApi.createPromo).toHaveBeenCalledWith({ code: "STREAMER", percent: 7.5, is_media: true, media_percent: 13 });
});

test("media rows show a separate salary and editing preserves the contract", async () => {
  promos = [{ id: "sinzuku", code: "SINZUKU", percent: 7.5, is_media: true, media_percent: 13,
    deposited_rap: 1000, media_payout_rub: 32.5 }];
  await act(async () => { root.render(<PromosTab refreshKey={10} />); });
  const row = byId("promo-row-sinzuku");
  expect(row.querySelector('[data-testid="promo-media-badge"]').textContent).toBe("Медиапромокод");
  expect(row.querySelector('[data-testid="promo-media-payout"]').textContent).toBe("32,5 ₽13% от пополнений");
  await click(document.querySelector('[aria-label="Редактировать SINZUKU"]'));
  expect(byId("promo-is-media").checked).toBe(true);
  expect(byId("promo-percent").value).toBe("7.5");
  expect(byId("promo-media-percent").value).toBe("13");
  await setInput("promo-code", "NEW_MEDIA");
  await click("promo-save");
  expect(adminApi.updatePromo).toHaveBeenCalledWith("sinzuku", { code: "NEW_MEDIA", percent: 7.5, is_media: true, media_percent: 13 });
});

test("removing the media mark clears commission and retains the player bonus", async () => {
  await click("promo-add");
  await setInput("promo-code", "ORDINARY");
  await click("promo-is-media");
  await click("promo-is-media");
  expect(byId("promo-media-percent")).toBeNull();
  expect(byId("promo-percent").value).toBe("7.5");
  await click("promo-save");
  expect(adminApi.createPromo).toHaveBeenCalledWith({ code: "ORDINARY", percent: 7.5, is_media: false, media_percent: 0 });
});

test("invalid media commission cannot be submitted", async () => {
  await click("promo-add");
  await setInput("promo-code", "STREAMER");
  await click("promo-is-media");
  for (const rate of ["-1", "100.01", "13.001", ""]) {
    await setInput("promo-media-percent", rate);
    expect(byId("promo-media-percent").checkValidity()).toBe(false);
    await click("promo-save");
  }
  expect(adminApi.createPromo).not.toHaveBeenCalled();
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

test("shows actual deposit RAP separately from activations and gift amounts", async () => {
  promos = [
    { id: "pelmen", code: "PELMEN", percent: 10, unique_users: 7, deposited_rap: 1234.56,
      skin_deposited_rap: 1000, cash_deposited_rap: 234.56, deposit_count: 5, depositors: 2 },
    { id: "gift", code: "GIFT", type: "rap_fixed", amount_rap: 100, max_uses: 5, used_count: 3 },
  ];
  await act(async () => { root.render(<PromosTab refreshKey={2} />); });
  const row = byId("promo-row-pelmen");
  expect(row.querySelector('[data-testid="promo-deposited-rap"]').textContent).toContain("1\u00a0234,56");
  expect(row.querySelector('[data-testid="promo-deposit-count"]').textContent).toBe("5");
  expect(row.querySelector('[data-testid="promo-depositors"]').textContent).toBe("2");
  expect(row.querySelector('[data-testid="promo-deposited-rub"]').textContent).toBe("308,64 ₽ для расчёта");
  expect(row.querySelector('[data-testid="promo-unique-users"]').textContent).toBe("7");
  expect(byId("promo-row-gift").querySelector('[data-testid="promo-deposited-rap"]').textContent).toBe("—");
  expect(row.querySelector('[data-testid="promo-media-payout"]').textContent).toBe("—");
  expect(byId("promo-row-gift").querySelector('[data-testid="promo-media-payout"]').textContent).toBe("—");
});

test("applies inclusive local calendar dates and resets to all-time", async () => {
  await setInput("promo-date-from", "2026-10-01");
  await setInput("promo-date-to", "2026-10-03");
  await click("promo-period-apply");
  expect(adminApi.promos).toHaveBeenLastCalledWith({
    date_from: new Date("2026-10-01T00:00:00").toISOString(),
    date_to: new Date("2026-10-04T00:00:00").toISOString(),
  });
  expect(byId("promo-period-label").textContent).toContain("2026-10-01 — 2026-10-03");
  await click("promo-all-time");
  expect(adminApi.promos).toHaveBeenLastCalledWith({});
  expect(byId("promo-period-label").textContent).toContain("Всё время");
});

test("invalid period preserves the displayed report", async () => {
  const calls = adminApi.promos.mock.calls.length;
  await setInput("promo-date-from", "2026-10-03");
  await setInput("promo-date-to", "2026-10-01");
  await click("promo-period-apply");
  expect(document.querySelector('[role="alert"]').textContent).toContain("Дата начала");
  expect(adminApi.promos).toHaveBeenCalledTimes(calls);
  expect(byId("promo-row-pelmen")).not.toBeNull();
});

test("does not display or export the old report when loading a new period fails", async () => {
  adminApi.promos.mockRejectedValueOnce(new Error("Offline"));
  await click("promo-this-month");
  expect(byId("promos-table")).toBeNull();
  expect(byId("promo-export").disabled).toBe(true);
  expect(document.querySelector('[role="alert"]').textContent).toContain("Не удалось загрузить");
});

test("CSV export contains confirmed turnover fields and excludes gift promos", async () => {
  promos = [
    { id: "pelmen", code: "PELMEN", percent: 10, unique_users: 99, deposited_rap: 200,
      skin_deposited_rap: 120, cash_deposited_rap: 80, deposit_count: 2, depositors: 1 },
    { id: "sinzuku", code: "SINZUKU", percent: 7.5, is_media: true, media_percent: 13,
      deposited_rap: 1000, skin_deposited_rap: 1000, deposit_count: 1, depositors: 1, media_payout_rub: 32.5 },
    { id: "gift", code: "GIFT", type: "rap_fixed", amount_rap: 100, max_uses: 5, used_count: 3 },
  ];
  await act(async () => { root.render(<PromosTab refreshKey={3} />); });
  jest.useFakeTimers();
  const createObjectURL = jest.fn().mockReturnValue("blob:report");
  const revokeObjectURL = jest.fn();
  const previousCreate = URL.createObjectURL;
  const previousRevoke = URL.revokeObjectURL;
  URL.createObjectURL = createObjectURL;
  URL.revokeObjectURL = revokeObjectURL;
  const anchorClick = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  try {
    await click("promo-export");
    const blob = createObjectURL.mock.calls[0][0];
    const text = await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.readAsText(blob);
    });
    expect(text).toContain('"PELMEN";"Всё время";"200";"120";"80";"2";"1";"50"');
    expect(text).toContain('"SINZUKU";"Всё время";"1000";"1000";"0";"1";"1";"250";"13";"32.5";"Да"');
    expect(text).not.toContain('"GIFT"');
    jest.advanceTimersByTime(1000);
  } finally {
    anchorClick.mockRestore();
    URL.createObjectURL = previousCreate;
    URL.revokeObjectURL = previousRevoke;
    jest.useRealTimers();
  }
});

test("a late save refresh cannot replace the newly selected payroll period", async () => {
  let finishSave;
  adminApi.createPromo.mockImplementationOnce(() => new Promise((resolve) => { finishSave = resolve; }));
  await click("promo-add");
  await setInput("promo-code", "NEW");
  await click("promo-save");
  await click("promo-this-month");
  const periodCalls = adminApi.promos.mock.calls.length;
  expect(adminApi.promos.mock.calls[periodCalls - 1][0].date_from).toBeDefined();
  await act(async () => { finishSave({}); });
  expect(adminApi.promos).toHaveBeenCalledTimes(periodCalls);
  expect(byId("promo-period-label").textContent).not.toContain("Всё время");
});

const setSelect = async (id, value) => act(async () => {
  const el = byId(id);
  Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(el, value);
  el.dispatchEvent(new Event("change", { bubbles: true }));
});

test("shows RAP gifts with amount, usage and expiry", async () => {
  promos = [
    { id: "g1", code: "GIFT", type: "rap_fixed", amount_rap: 100.5, max_uses: 10, unique_users: 3, used_count: 3, expires_at: "2030-05-01T12:00:00Z" },
    { id: "pelmen", code: "PELMEN", percent: 10, unique_users: 7 },
  ];
  await act(async () => { root.render(<PromosTab refreshKey={7} />); });
  const row = byId("promo-row-g1");
  expect(row.textContent).toContain("100");
  expect(row.textContent).toContain("RAP");
  expect(row.textContent).toContain("RAP-подарок");
  expect(row.querySelector('[data-testid="promo-unique-users"]').textContent).toContain("3");
  expect(row.querySelector('[data-testid="promo-unique-users"]').textContent).toContain("10");
  expect(row.textContent).not.toContain("+10%");
});

test("creating a RAP gift sends type, amount, limit and expiry", async () => {
  await click("promo-add");
  await click("promo-is-media");
  await setSelect("promo-type", "rap_fixed");
  expect(byId("promo-is-media")).toBeNull();
  await setInput("promo-code", "GIFT100");
  await setInput("promo-amount", "100.5");
  await setInput("promo-max-uses", "25");
  expect(byId("promo-amount").checkValidity()).toBe(true);
  expect(byId("promo-max-uses").checkValidity()).toBe(true);
  await click("promo-save");
  expect(adminApi.createPromo).toHaveBeenCalledWith(
    expect.objectContaining({ code: "GIFT100", type: "rap_fixed", amount_rap: 100.5, max_uses: 25 }));
  expect(adminApi.createPromo.mock.calls[0][0]).not.toHaveProperty("is_media");
  expect(adminApi.createPromo.mock.calls[0][0]).not.toHaveProperty("media_percent");
  expect(byId("promo-editor")).toBeNull();
});

test("RAP editor shows total campaign budget and one-per-person rule", async () => {
  await click("promo-add");
  await setSelect("promo-type", "rap_fixed");
  await setInput("promo-amount", "100");
  await setInput("promo-max-uses", "25");
  expect(byId("promo-budget").textContent).toContain("2");
  expect(byId("promo-budget").textContent).toContain("1 человеку");
});

test("editing a RAP gift locks type and freezes amount after bookings", async () => {
  promos = [{ id: "g1", code: "GIFT", type: "rap_fixed", amount_rap: 50, max_uses: 5, unique_users: 2, used_count: 2 }];
  await act(async () => { root.render(<PromosTab refreshKey={8} />); });
  await click(document.querySelector('[aria-label="Редактировать GIFT"]'));
  expect(byId("promo-type").value).toBe("rap_fixed");
  expect(byId("promo-type").disabled).toBe(true);
  expect(byId("promo-amount").value).toBe("50");
  expect(byId("promo-amount").disabled).toBe(true);
  await setInput("promo-max-uses", "8");
  promos = [{ id: "g1", code: "GIFT", type: "rap_fixed", amount_rap: 50, max_uses: 8, unique_users: 2, used_count: 2 }];
  await click("promo-save");
  expect(adminApi.updatePromo).toHaveBeenCalledWith("g1",
    expect.objectContaining({ type: "rap_fixed", amount_rap: 50, max_uses: 8 }));
});

test("invalid RAP amounts and limits cannot be submitted", async () => {
  await click("promo-add");
  await setSelect("promo-type", "rap_fixed");
  await setInput("promo-code", "GIFT");
  for (const bad of ["0", "-5", "100000.01", "10.001", ""]) {
    await setInput("promo-amount", bad);
    expect(byId("promo-amount").checkValidity()).toBe(false);
  }
  await setInput("promo-amount", "10");
  for (const bad of ["0", "-1", "100001", "2.5", ""]) {
    await setInput("promo-max-uses", bad);
    expect(byId("promo-max-uses").checkValidity()).toBe(false);
  }
  await click("promo-save");
  expect(adminApi.createPromo).not.toHaveBeenCalled();
});

test("RAP delete dialog warns that issued gifts stay", async () => {
  promos = [{ id: "g1", code: "GIFT", type: "rap_fixed", amount_rap: 10, max_uses: 5, unique_users: 1, used_count: 1 }];
  await act(async () => { root.render(<PromosTab refreshKey={9} />); });
  await click(document.querySelector('[aria-label="Удалить GIFT"]'));
  expect(byId("promo-delete-dialog").textContent).toContain("не отзовётся");
  await click("promo-delete-confirm");
  expect(adminApi.deletePromo).toHaveBeenLastCalledWith("g1");
});
