import React, { act } from "react";
import { createRoot } from "react-dom/client";
import ReferralPanel from "./ReferralPanel";
import { LangProvider } from "../lib/i18n";
import { api } from "../lib/api";

jest.mock("../lib/api", () => ({ ...jest.requireActual("../lib/api"), api: { referrals: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

let root, container;
const byId = (id) => document.querySelector(`[data-testid="${id}"]`);
const render = async () => act(async () => root.render(<LangProvider><ReferralPanel /></LangProvider>));
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.setItem("bloxgrade_lang", "ru");
  api.referrals.mockReset();
  api.referrals.mockResolvedValue({ url: "https://example.test/?ref=0123456789abcdef", invited_count: 2, qualified_count: 1, earned_rap: 32, deposit_earned_rap: 7,
    invites: [{ nickname: "Friend", wagered_rap: 50, qualified: false, earned_rap: 3.5 }, { nickname: "Second", wagered_rap: 100, qualified: true, earned_rap: 28.5 }] });
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: jest.fn().mockResolvedValue() } });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("shows permanent deposit rewards, qualification progress and copies the personal link", async () => {
  await render();
  expect(byId("referral-panel").textContent).toContain("Отыгрыш для процентов не нужен");
  expect(byId("referral-stat-earned").textContent).toBe("32,00 RAP");
  expect(byId("referral-panel").textContent).toContain("50,00 / 100 RAP");
  expect(byId("referral-panel").textContent).toContain("Бонус 25 RAP начислен");
  await act(async () => byId("referral-copy").click());
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://example.test/?ref=0123456789abcdef");
});

test("failed requests show a retry instead of an invented referral link", async () => {
  api.referrals.mockRejectedValueOnce(new Error("Network"));
  await render();
  expect(byId("referral-link")).toBeNull();
  await act(async () => byId("referral-retry").click());
  expect(byId("referral-link").value).toBe("https://example.test/?ref=0123456789abcdef");
});
