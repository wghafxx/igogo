import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { LangProvider } from "../lib/i18n";
import WithdrawalHistory from "./WithdrawalHistory";
import { SupportDialog, SUPPORT_HANDLE } from "./SupportDialog";
import MyRequests from "./topup/MyRequests";

jest.mock("@/lib/utils", () => jest.requireActual("../lib/utils"), { virtual: true });
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("../hooks/useAuth", () => ({ useAuth: () => ({ refresh: jest.fn() }) }));

const byId = (id) => document.querySelector(`[data-testid="${id}"]`);
let root, container;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.setItem("bloxgrade_lang", "ru");
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: jest.fn().mockResolvedValue() } });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = async (content) => act(async () => root.render(<LangProvider>{content}</LangProvider>));

test("player sees custom cancellation reason and returned inventory status", async () => {
  const onInstructions = jest.fn();
  await render(<WithdrawalHistory items={[{ id: "w1", item: { name: "Skin", price: 100 }, status: "cancelled", created_at: "2026-09-13T00:00:00Z", cancellation_reason: "Нужного скина пока нет\nПопробуйте позже" }]} onInstructions={onInstructions} />);
  expect(byId("profile-withdrawal-reason").textContent).toContain("Нужного скина пока нет\nПопробуйте позже");
  expect(byId("profile-withdrawals").textContent).toContain("Скин возвращён в ваш инвентарь.");
  expect(byId("profile-withdrawal-instructions")).toBeNull();
});

test("pending withdrawal opens the trade instructions without creating another request", async () => {
  const onInstructions = jest.fn();
  await render(<WithdrawalHistory items={[{ id: "w1", item: { name: "Skin", price: 100 }, status: "pending", created_at: "2026-09-13T00:00:00Z" }]} onInstructions={onInstructions} />);
  await act(async () => byId("profile-withdrawal-instructions").click());
  expect(onInstructions).toHaveBeenCalledWith(1);
});

test("withdrawal dialog shows Trade Plaza steps and copies the Roblox account", async () => {
  await render(<SupportDialog request={{ kind: "withdrawal", count: 2 }} onClose={jest.fn()} />);
  expect(byId("support-withdrawal-instructions").textContent).toContain("трейд-плазу");
  expect(byId("support-withdrawal-instructions").textContent).toContain("выигранному RAP");
  expect(byId("support-withdrawal-account").textContent).toBe("ysrent1");
  expect(byId("support-withdrawal-history").getAttribute("href")).toBe("/profile?tab=withdrawals");
  await act(async () => byId("support-copy-handle").click());
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith("ysrent1");
  await render(<SupportDialog request={{ kind: "support" }} onClose={jest.fn()} />);
  await act(async () => byId("support-copy-handle").click());
  expect(navigator.clipboard.writeText).toHaveBeenLastCalledWith(SUPPORT_HANDLE);
});

test.each([
  ["yellow_tag", "Жёлтая табличка на скине"],
  ["Не поступил трейд\nПроверьте получателя", "Не поступил трейд\nПроверьте получателя"],
])("deposit history displays preset or custom reason: %s", async (reason, expected) => {
  await render(<MyRequests items={[{ id: "d1", status: "rejected", expected_rap: 100, description: "Skin", created_at: "2026-09-13T00:00:00Z", rejection_reason: reason }]} onChanged={jest.fn()} onNew={jest.fn()} />);
  expect(byId("my-request-rejection-reason").textContent).toContain(expected);
});
