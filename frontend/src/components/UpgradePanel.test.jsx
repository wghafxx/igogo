import React, { act } from "react";
import { createRoot } from "react-dom/client";
import UpgradePanel from "./UpgradePanel";
import { api } from "../lib/api";
import { useUpgradeSpin } from "../hooks/useUpgradeSpin";

jest.mock("../lib/api", () => ({ api: { gameConfig: jest.fn(), shop: jest.fn() }, formatMoney: (n) => String(n) }));
jest.mock("sonner", () => ({ toast: { info: jest.fn(), error: jest.fn() } }));
jest.mock("../hooks/useAuth", () => ({ useAuth: () => ({ authUser: { id: "player" } }) }));
jest.mock("../lib/i18n", () => ({ useLang: () => ({ t: (key) => key, lang: "ru" }) }));
jest.mock("../hooks/useUpgradeSpin", () => ({ useUpgradeSpin: jest.fn() }));
jest.mock("../lib/sound", () => ({ playTick: jest.fn(), prepareResultSounds: jest.fn() }));
jest.mock("./Gauge", () => ({ chance }) => <div data-testid="chance">{chance}</div>);
jest.mock("./Logo", () => ({ Logo: () => null, RobuxIcon: () => null }));
jest.mock("./AnimButton", () => ({ icon, iconProps, size, ...props }) => <button {...props} />);
jest.mock("./ui/tooltip", () => ({
  Tooltip: ({ children }) => <>{children}</>, TooltipProvider: ({ children }) => <>{children}</>,
  TooltipTrigger: ({ children }) => <>{children}</>, TooltipContent: () => null,
}));
jest.mock("./ui/slider", () => ({ Slider: ({ value, onValueChange, ...props }) => <input {...props} type="range" value={value[0]} onChange={(e) => onValueChange([Number(e.target.value)])} /> }));

let root, container, props, spin;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const render = async () => act(async () => root.render(<UpgradePanel {...props} />));
const setStake = async (value) => act(async () => {
  const input = byId("bet-slider");
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(value));
  input.dispatchEvent(new Event("input", { bubbles: true }));
});

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.resetAllMocks();
  // Even a stale server config with the former RTP-adjusted limit cannot
  // make the client spend above its displayed cap.
  api.gameConfig.mockResolvedValue({ rtp: .87, min_chance: .01, max_chance: .75, max_bet_ratio: .75 / .87 });
  spin = jest.fn();
  useUpgradeSpin.mockReturnValue({ busyRef: { current: false }, spinning: false, runSpin: spin });
  props = { sessionId: "player", user: { balance: 1000 },
    settings: { sound: false, multipliers: [2, 4], percents: [75, 35, 1] },
    target: { id: "rusted", name: "Rusted", price: 2000 },
    betSkins: [{ uid: "sakura", name: "Sakura", price: 1295 }],
    onSelectTarget: jest.fn(),
  };
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("screenshot case caps extra balance at 205 and sends exactly 75% total stake", async () => {
  await render();
  expect(byId("bet-slider").max).toBe("205");
  await setStake(205);
  expect(byId("bet-amount").textContent).toBe("205");
  expect(byId("total-bet").textContent).toBe("1500");
  expect(byId("chance").textContent).toBe("0.75");
  await act(async () => byId("upgrade-button").click());
  expect(spin).toHaveBeenCalledWith(expect.objectContaining({ bet_amount: 205, bet_items: [{ uid: "sakura" }], chance: .75 }));
});

test("six copies are shown separately and their combined stake is sent against one target", async () => {
  props.betSkins = Array.from({ length: 6 }, (_, i) => ({ id: "same-skin", uid: `copy-${i}`, name: `Copy ${i}`, price: 100 }));
  props.onRemoveBetSkin = jest.fn((uid) => {
    props = { ...props, betSkins: props.betSkins.filter((skin) => skin.uid !== uid) };
    root.render(<UpgradePanel {...props} />);
  });
  await render();
  expect(byId("bet-skin-count").textContent).toBe("6/6");
  expect(byId("bet-skins-grid").children).toHaveLength(6);
  expect(byId("bet-slider").max).toBe("900");
  await setStake(50);
  expect(byId("total-bet").textContent).toBe("650");
  expect(Number(byId("chance").textContent)).toBeCloseTo(.325);
  await act(async () => byId("upgrade-button").click());
  expect(spin).toHaveBeenCalledWith({ session_id: "player", bet_amount: 50,
    bet_items: props.betSkins.map(({ uid }) => ({ uid })), target_item: { id: "rusted" }, chance: .325 });
  await act(async () => byId("bet-skin-copy-2-remove").click());
  expect(props.onRemoveBetSkin).toHaveBeenCalledWith("copy-2");
  expect(byId("bet-skin-copy-2")).toBeNull();
  expect(byId("bet-skins-grid").children).toHaveLength(5);
  expect(byId("bet-skin-count").textContent).toBe("5/6");
  expect(byId("total-bet").textContent).toBe("550");
});

test("skin removal is disabled during a spin and a seven-skin stake cannot start", async () => {
  props.betSkins = Array.from({ length: 6 }, (_, i) => ({ uid: `copy-${i}`, name: `Copy ${i}`, price: 100 }));
  props.onRemoveBetSkin = jest.fn();
  useUpgradeSpin.mockReturnValue({ busyRef: { current: true }, spinning: true, runSpin: spin });
  await render();
  await act(async () => byId("bet-skin-copy-0-remove").click());
  expect(props.onRemoveBetSkin).not.toHaveBeenCalled();
  useUpgradeSpin.mockReturnValue({ busyRef: { current: false }, spinning: false, runSpin: spin });
  props.betSkins = [...props.betSkins, { uid: "seventh", name: "Seventh", price: 100 }];
  await render();
  expect(byId("upgrade-button").disabled).toBe(true);
  await act(async () => byId("upgrade-button").click());
  expect(spin).not.toHaveBeenCalled();
});

test("quick target selection uses all six skin values", async () => {
  props.betSkins = Array.from({ length: 6 }, (_, i) => ({ uid: `copy-${i}`, name: `Copy ${i}`, price: 6.5 }));
  props.target = null;
  props.settings.percents = [50];
  catalog([{ id: "case1", price: 88 }, { id: "too-cheap", price: 13 }]);
  await render();
  await act(async () => byId("pct-50").click());
  expect(props.onSelectTarget).toHaveBeenLastCalledWith(expect.objectContaining({ id: "case1" }));
  expect(byId("total-bet").textContent).toBe("39");
});

test("skins already at 75% disable extra cash, and skins above cap disable the upgrade", async () => {
  props.betSkins = [{ uid: "sakura", price: 1500 }];
  await render();
  expect(byId("bet-slider").disabled).toBe(true);
  expect(byId("bet-amount").textContent).toBe("0");
  expect(byId("upgrade-button").disabled).toBe(false);
  props.betSkins = [{ uid: "sakura", price: 1500.01 }];
  await render();
  expect(byId("bet-slider").disabled).toBe(true);
  expect(byId("upgrade-button").disabled).toBe(true);
});

test("changing target reduces an already selected balance to the new cap", async () => {
  await render();
  await setStake(205);
  props.target = { id: "cheaper", price: 1800 };
  await render();
  expect(byId("bet-slider").max).toBe("55");
  expect(byId("bet-amount").textContent).toBe("55");
});

test("cent rounding keeps the largest affordable amount without overpaying", async () => {
  props.betSkins = [{ uid: "sakura", price: 1295.29 }];
  await render();
  expect(byId("bet-slider").max).toBe("204.71");
  props.target = { id: "fractional", price: 99.99 };
  props.betSkins = [];
  await render();
  expect(byId("bet-slider").max).toBe("74.99");
});

const catalog = (items) => api.shop.mockImplementation(async (params) => ({ items: items
  .filter((item) => item.price >= params.min_price && item.price <= params.max_price)
  .sort((a, b) => params.sort === "price_asc" ? a.price - b.price : b.price - a.price).slice(0, params.limit) }));

test("39 RAP stake selects the nearest real chance for 25%, 50%, 75% without adding balance", async () => {
  props.betSkins = [{ uid: "case39", price: 39 }];
  props.target = null;
  props.settings.percents = [25, 50, 75];
  catalog([{ id: "case1", price: 88 }, { id: "case2", price: 165 }, { id: "case3", price: 60 }, { id: "over-cap", price: 40 }]);
  props.onSelectTarget.mockImplementation((item) => { props = { ...props, target: item }; root.render(<UpgradePanel {...props} />); });
  await render();
  await act(async () => byId("pct-50").click());
  expect(props.onSelectTarget).toHaveBeenLastCalledWith(expect.objectContaining({ id: "case1" }));
  expect(Number(byId("chance").textContent)).toBeCloseTo(39 / 88);
  expect(byId("total-bet").textContent).toBe("39");
  expect(byId("bet-amount").textContent).toBe("0");
  await act(async () => byId("pct-25").click());
  expect(props.onSelectTarget).toHaveBeenLastCalledWith(expect.objectContaining({ id: "case2" }));
  await act(async () => byId("pct-75").click());
  expect(props.onSelectTarget).toHaveBeenLastCalledWith(expect.objectContaining({ id: "case3" }));
  expect(Number(byId("chance").textContent)).toBe(.65);
});

test("multipliers pick the nearest price ratio and preserve the selected cash stake", async () => {
  props.betSkins = [];
  catalog([{ id: "two", price: 220 }, { id: "four", price: 410 }]);
  await render();
  await setStake(100);
  await act(async () => byId("mult-x2").click());
  expect(props.onSelectTarget).toHaveBeenLastCalledWith(expect.objectContaining({ id: "two" }));
  expect(byId("bet-amount").textContent).toBe("100");
  await act(async () => byId("mult-x4").click());
  expect(props.onSelectTarget).toHaveBeenLastCalledWith(expect.objectContaining({ id: "four" }));
});

test("nearest percent uses chance distance rather than price distance", async () => {
  props.betSkins = [{ uid: "source", price: 100 }];
  props.settings.percents = [50];
  catalog([{ id: "below", price: 170 }, { id: "above", price: 235 }]);
  await render();
  await act(async () => byId("pct-50").click());
  expect(props.onSelectTarget).toHaveBeenLastCalledWith(expect.objectContaining({ id: "above" }));
  await act(async () => byId("mult-x2").click());
  expect(props.onSelectTarget).toHaveBeenLastCalledWith(expect.objectContaining({ id: "below" }));
});

test("empty or failed catalog leaves the target and balance unchanged", async () => {
  catalog([]);
  await render();
  await act(async () => byId("pct-75").click());
  expect(props.onSelectTarget).not.toHaveBeenCalled();
  api.shop.mockRejectedValueOnce(new Error("Offline"));
  await act(async () => byId("pct-75").click());
  expect(props.onSelectTarget).not.toHaveBeenCalled();
  expect(byId("bet-amount").textContent).toBe("0");
});

test("a rapid upgrade click cannot start the old target while quick selection is pending", async () => {
  catalog([{ id: "new-target", price: 2000 }]);
  await render();
  await act(async () => { byId("pct-75").click(); byId("upgrade-button").click(); });
  expect(spin).not.toHaveBeenCalled();
});

test("changing the source during a slow lookup does not apply its stale target", async () => {
  let finish;
  api.shop.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  await render();
  await act(async () => byId("pct-75").click());
  props.betSkins = [{ uid: "new-source", price: 39 }];
  await render();
  await act(async () => { finish({ items: [{ id: "old-target", price: 2000 }] }); });
  expect(props.onSelectTarget).not.toHaveBeenCalled();
});
