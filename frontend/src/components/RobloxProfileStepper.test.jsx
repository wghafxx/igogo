import React, { act } from "react";
import { createRoot } from "react-dom/client";
import RobloxProfileStepper from "./RobloxProfileStepper";
import TopUpModal from "./TopUpModal";
import MyRequests from "./topup/MyRequests";
import CommandComposer from "./admin/chat/CommandComposer";
import { api, adminApi } from "../lib/api";
import { useAuth } from "../hooks/useAuth";
import { validRobloxLink } from "../lib/roblox";
import LiveChatWidget from "./chat/LiveChatWidget";
import ChatMessages from "./chat/ChatMessages";
import { useLiveChat } from "../hooks/useLiveChat";

jest.mock("@/lib/utils", () => jest.requireActual("../lib/utils"), { virtual: true });
jest.mock("../lib/api", () => ({
  api: { saveRoblox: jest.fn(), depositInfo: jest.fn(), myDeposits: jest.fn() },
  adminApi: { commands: jest.fn() },
  formatMoney: String, parseServerDate: (v) => new Date(v), rejectionReasonText: (v) => v,
}));
jest.mock("../hooks/useAuth", () => ({ useAuth: jest.fn() }));
jest.mock("../hooks/useLiveChat", () => ({ useLiveChat: jest.fn() }));
jest.mock("../lib/i18n", () => ({ useLang: () => ({ t: (key) => key, lang: "ru" }) }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("motion/react", () => {
  const React = require("react");
  const actual = jest.requireActual("motion/react");
  const component = (tag) => React.forwardRef(({ children, initial, animate, exit, transition, custom, variants, ...rest }, ref) => React.createElement(tag, { ...rest, ref }, children));
  const overrides = { div: component("div"), path: component("path") };
  return { ...actual, AnimatePresence: ({ children }) => children, motion: new Proxy(actual.motion, { get: (target, key) => overrides[key] || target[key] }), useReducedMotion: () => true };
});

let container, root, user, setAuthUser;
const byId = (id) => document.querySelector(`[data-testid="${id}"]`);
const render = async (element) => act(async () => root.render(element));
const type = async (id, value) => act(async () => {
  const input = byId(id);
  const prototype = input.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, "value").set.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
});
const next = async () => act(async () => byId("roblox-step-next").click());

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.clearAllMocks();
  user = { session_id: "player", nickname: "Player" };
  setAuthUser = jest.fn();
  useAuth.mockImplementation(() => ({ authUser: user, setAuthUser, openAuth: jest.fn() }));
  api.depositInfo.mockResolvedValue({ receivers: [{ id: "support" }], min_rap: 200 });
  api.myDeposits.mockResolvedValue([]);
  adminApi.commands.mockResolvedValue([]);
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("all three fields are required, typing preserves focus and going back preserves values", async () => {
  await render(<RobloxProfileStepper required />);
  expect(byId("roblox-step-next").disabled).toBe(true);
  const input = byId("roblox-display-name-input");
  input.focus();
  for (const value of ["B", "Bl", "Blox", "Blox Player"]) {
    await type("roblox-display-name-input", value);
    expect(document.activeElement).toBe(input);
    expect(byId("roblox-display-name-input")).toBe(input);
  }
  await next();
  expect(byId("roblox-step-next").disabled).toBe(true);
  await type("roblox-nick-input", "@Builder_123");
  await next();
  await type("roblox-link-input", "https://www.roblox.com.evil.test/users/1/profile");
  expect(byId("roblox-step-next").disabled).toBe(true);
  await act(async () => byId("roblox-step-back").click());
  expect(byId("roblox-nick-input").value).toBe("@Builder_123");
  await next();
  expect(byId("roblox-link-input").value).toContain("evil.test");
  expect(api.saveRoblox).not.toHaveBeenCalled();
});

test("failed save keeps the final step and data; retry persists normalized profile", async () => {
  const onSaved = jest.fn();
  await render(<RobloxProfileStepper required onSaved={onSaved} />);
  await type("roblox-display-name-input", "Blox Player"); await next();
  await type("roblox-nick-input", "@Builder_123"); await next();
  await type("roblox-link-input", "https://www.roblox.com/users/123/profile");
  api.saveRoblox.mockRejectedValueOnce({ response: { data: { detail: "Профиль уже привязан" } } });
  await next();
  expect(container.querySelector('[role="alert"]').textContent).toContain("Профиль уже привязан");
  expect(byId("roblox-link-input").value).toContain("/123/profile");
  const profile = { roblox_display_name: "Blox Player", roblox_nick: "Builder_123", roblox_link: "https://www.roblox.com/users/123/profile" };
  api.saveRoblox.mockResolvedValueOnce({ ...user, ...profile });
  await next();
  expect(api.saveRoblox).toHaveBeenLastCalledWith(profile);
  expect(setAuthUser).toHaveBeenCalledWith({ ...user, ...profile });
  expect(onSaved).toHaveBeenCalledTimes(1);
});

test("all payment tabs require a complete profile, requests remain available", async () => {
  user = { ...user, roblox_nick: "Builder_123", roblox_link: "https://www.roblox.com/users/123/profile" };
  await render(<TopUpModal open onOpenChange={() => {}} />);
  for (const tab of ["skins", "rubles", "crypto"]) {
    await act(async () => byId(`topup-tab-${tab}`).click());
    expect(byId("roblox-profile-stepper")).not.toBeNull();
    expect(byId("topup-amount-step")).toBeNull();
    expect(byId("topup-rub-step")).toBeNull();
    expect(byId("crypto-topup")).toBeNull();
  }
  await act(async () => byId("topup-tab-requests").click());
  expect(byId("my-requests")).not.toBeNull();
});

test("completed requests are out of the active list but remain in history", async () => {
  await render(<MyRequests items={[{ id: "pending", status: "pending", expected_rap: 300, created_at: "2026-09-22", description: "Активная" }, { id: "old", status: "rejected", expected_rap: 200, created_at: "2026-09-21", description: "Старая", rejection_reason: "Долгое ожидание" }]} onChanged={() => {}} onNew={() => {}} />);
  expect(container.textContent).toContain("Активная");
  expect(container.textContent).not.toContain("Старая");
  await act(async () => byId("my-requests-tab-done").click());
  expect(container.textContent).toContain("Старая");
  expect(container.textContent).toContain("Долгое ожидание");
});

test("admin composer keeps input focus during send and polling renders", async () => {
  const send = jest.fn();
  await render(<CommandComposer text="Тест" setText={() => {}} onSend={send} busy={false} />);
  const input = byId("admin-chat-input"); input.focus();
  await act(async () => byId("admin-chat-send-button").click());
  expect(send).toHaveBeenCalledTimes(1);
  await render(<CommandComposer text="Тест" setText={() => {}} onSend={send} busy />);
  expect(document.activeElement).toBe(input);
  expect(input.disabled).toBe(false);
  await render(<CommandComposer text="" setText={() => {}} onSend={send} busy={false} />);
  expect(document.activeElement).toBe(input);
});

test("accepts Roblox profile sharing URLs and rejects unrelated Roblox pages", () => {
  expect(validRobloxLink("https://www.roblox.com/share?code=abcdef123&type=Profile")).toBe(true);
  expect(validRobloxLink("https://roblox.com/users/123/profile")).toBe(true);
  expect(validRobloxLink("https://www.roblox.com/games/123")).toBe(false);
  expect(validRobloxLink("https://www.roblox.com/share?code=abc&type=Game")).toBe(false);
});

test("creating the first chat preserves the same focused composer", async () => {
  const chatState = { open: true, chat: null, messages: [], cooldownUntil: 0, send: jest.fn().mockResolvedValue({}) };
  useLiveChat.mockImplementation(() => chatState);
  await render(<LiveChatWidget />);
  const input = byId("chat-input"); input.focus();
  await type("chat-input", "Здравствуйте");
  await act(async () => byId("chat-send-button").click());
  chatState.chat = { id: "created", status: "open" };
  await render(<LiveChatWidget />);
  expect(byId("chat-input")).toBe(input);
  expect(document.activeElement).toBe(input);
});

test("new messages scroll into view even when the retained message count stays constant", async () => {
  const scroll = jest.fn();
  Element.prototype.scrollIntoView = scroll;
  const message = (id) => ({ id, sender: "user", text: id, created_at: "2026-09-22" });
  await render(<ChatMessages messages={[message("first"), message("second")]} />);
  scroll.mockClear();
  await render(<ChatMessages messages={[message("second"), message("third")]} />);
  expect(scroll).toHaveBeenCalledTimes(1);
  delete Element.prototype.scrollIntoView;
});
