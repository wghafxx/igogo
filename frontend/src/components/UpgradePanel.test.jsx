import React, { act } from "react";
import { createRoot } from "react-dom/client";
import UpgradePanel from "./UpgradePanel";
import { api } from "../lib/api";
import { useUpgradeSpin } from "../hooks/useUpgradeSpin";

jest.mock("../lib/api", () => ({ api: { gameConfig: jest.fn() }, formatMoney: (n) => String(n) }));
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
  };
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("screenshot case caps extra balance at 205 and sends exactly 75% total stake", async () => {
  await render();
  expect(byId("bet-slider").max).toBe("205");
  await act(async () => byId("pct-75").click());
  expect(byId("bet-amount").textContent).toBe("205");
  expect(byId("total-bet").textContent).toBe("1500");
  expect(byId("chance").textContent).toBe("0.75");
  await act(async () => byId("upgrade-button").click());
  expect(spin).toHaveBeenCalledWith(expect.objectContaining({ bet_amount: 205, bet_items: [{ uid: "sakura" }], chance: .75 }));
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
  await act(async () => byId("pct-75").click());
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
