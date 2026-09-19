import React, { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { adminApi } from "../../lib/api";
import QuickCommandsTab from "./QuickCommandsTab";
import CommandComposer from "./chat/CommandComposer";
import CoinGrantCard from "./CoinGrantCard";
import { LinkedMessage } from "../chat/ChatMessages";

jest.mock("../../lib/api", () => ({
  adminApi: { commands: jest.fn(), createCommand: jest.fn(), updateCommand: jest.fn(), deleteCommand: jest.fn(), grantCoins: jest.fn(), coinGrants: jest.fn() },
  formatMoney: (n) => String(n), parseServerDate: (s) => new Date(s),
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const user = { session_id: "player", nickname: "Builder", discord_id: "123", balance: 10 };
let root, container, commands;
const button = (label) => [...container.querySelectorAll("button")].find((el) => el.textContent === label);
const input = async (label, value) => act(async () => {
  const el = container.querySelector(`[aria-label="${label}"]`);
  const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
});
const render = async (element) => act(async () => root.render(element));

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.resetAllMocks();
  sessionStorage.clear();
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: jest.fn(() => "11223344-1122-4122-8122-112233445566") } });
  commands = [{ id: "nick", command: "nick", text: "Добавьте {nick} в Roblox. Ждём {nick}." }, { id: "donat", command: "donat", text: "Пополнить: https://www.donationalerts.com/r/bloxgrade" }];
  adminApi.commands.mockImplementation(async () => commands.map((c) => ({ ...c })));
  adminApi.coinGrants.mockResolvedValue([]);
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});

afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("create, edit and delete shared commands through the form", async () => {
  adminApi.createCommand.mockImplementation(async (p) => commands.push({ id: "new", ...p }));
  adminApi.updateCommand.mockImplementation(async (id, p) => { commands = commands.map((c) => c.id === id ? { id, ...p } : c); });
  adminApi.deleteCommand.mockImplementation(async (id) => { commands = commands.filter((c) => c.id !== id); });
  await render(<QuickCommandsTab />);
  await input("Название команды", "/WAIT"); await input("Текст ответа", "Ожидайте, пожалуйста.");
  await act(async () => container.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  expect(adminApi.createCommand).toHaveBeenCalledWith({ command: "wait", text: "Ожидайте, пожалуйста." });
  await act(async () => button("Редактировать /wait").click());
  await input("Текст ответа", "Ждите {args} минут.");
  await act(async () => container.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  expect(adminApi.updateCommand).toHaveBeenCalledWith("new", { command: "wait", text: "Ждите {args} минут." });
  await act(async () => button("Удалить /wait").click());
  expect(adminApi.deleteCommand).not.toHaveBeenCalled();
  await act(async () => button("Подтвердить удаление").click());
  expect(adminApi.deleteCommand).toHaveBeenCalledWith("new");
  expect(button("Редактировать /wait")).toBeUndefined();
});

function Composer({ onSend }) {
  const [text, setText] = useState("/");
  return <CommandComposer text={text} setText={setText} onSend={() => onSend(text)} />;
}
const chatInput = async (text) => act(async () => {
  const el = container.querySelector("textarea");
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(el, text);
  el.dispatchEvent(new Event("input", { bubbles: true }));
});

test("slash selection previews nick, requires argument and does not send until clicked", async () => {
  const send = jest.fn(); await render(<Composer onSend={send} />);
  await act(async () => button("/nick <ник>").click());
  expect(send).not.toHaveBeenCalled();
  expect(container.querySelector('[aria-label="Отправить"]').disabled).toBe(true);
  await chatInput("/nick Builder_123");
  expect(container.querySelector('[data-testid="command-preview"]').textContent).toContain("Добавьте Builder_123 в Roblox. Ждём Builder_123.");
  await act(async () => container.querySelector('[aria-label="Отправить"]').click());
  expect(send).toHaveBeenCalledWith("/nick Builder_123");
});

test("donation preview and ordinary replies work; unknown or extra arguments stay unsent", async () => {
  const send = jest.fn(); await render(<Composer onSend={send} />);
  await act(async () => button("/donat").click());
  expect(container.textContent).toContain("https://www.donationalerts.com/r/bloxgrade");
  expect(send).not.toHaveBeenCalled();
  const submit = () => container.querySelector('[aria-label="Отправить"]');
  expect(submit().disabled).toBe(false);
  for (const text of ["/missing", "/donat extra"]) { await chatInput(text); expect(submit().disabled).toBe(true); }
  await chatInput("Обычный ответ"); expect(submit().disabled).toBe(false);
  expect(container.querySelector('[data-testid="command-preview"]')).toBeNull();
});

test("large grant sends exact decimal amount and ignores a rapid second click", async () => {
  let finish;
  adminApi.grantCoins.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const changed = jest.fn(); await render(<CoinGrantCard user={user} onChanged={changed} />);
  await input("Количество монет", "2500000,25");
  await input("Заметка к начислению", "DonationAlerts");
  await act(async () => { const el = button("Начислить 2500000.25 монет"); el.click(); el.click(); });
  expect(adminApi.grantCoins).toHaveBeenCalledTimes(1);
  expect(adminApi.grantCoins).toHaveBeenCalledWith("player", expect.objectContaining({ amount: "2500000.25", note: "DonationAlerts" }));
  expect(container.querySelector('[aria-label="Количество монет"]').disabled).toBe(true);
  await act(async () => finish({ amount: 2500000.25, balance: 2500010.25 }));
  expect(changed).toHaveBeenCalledTimes(1);
  expect(sessionStorage.getItem("admin-coin-grant:player")).toBeNull();
});

test("a timed out grant survives remount and retries with the same request ID", async () => {
  adminApi.grantCoins.mockRejectedValueOnce(new Error("timeout")).mockResolvedValueOnce({ amount: 50, balance: 60 });
  await render(<CoinGrantCard key="first" user={user} />);
  await input("Количество монет", "50");
  await act(async () => button("Начислить 50 монет").click());
  const original = adminApi.grantCoins.mock.calls[0][1];
  await render(<CoinGrantCard key="remount" user={user} />);
  expect(container.querySelector('[aria-label="Количество монет"]').value).toBe("50");
  expect(container.querySelector('[aria-label="Количество монет"]').disabled).toBe(true);
  await act(async () => button("Повторить запрос").click());
  expect(adminApi.grantCoins.mock.calls[1][1]).toEqual(original);
  expect(sessionStorage.getItem("admin-coin-grant:player")).toBeNull();
});

test("donation URL is clickable, markup and unsafe schemes remain literal text", async () => {
  await render(<LinkedMessage text={'https://www.donationalerts.com/r/bloxgrade. <img src=x onerror=alert(1)> javascript:alert(1)'} />);
  const links = container.querySelectorAll("a");
  expect(links.length).toBe(1);
  expect(links[0].href).toBe("https://www.donationalerts.com/r/bloxgrade");
  expect(links[0].rel).toBe("noopener noreferrer");
  expect(container.querySelector("img")).toBeNull();
  expect(container.textContent).toContain("javascript:alert(1)");
});
