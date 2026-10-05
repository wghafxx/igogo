import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { api } from "../lib/api";
import { useLiveChat } from "./useLiveChat";

jest.mock("../lib/api", () => ({ api: { chats: jest.fn(), chatMessages: jest.fn(), sendChatMessage: jest.fn() } }));
jest.mock("./useAuth", () => ({ useAuth: () => ({ authUser: { session_id: "player" } }) }));
let state, root, container;
const chat = { id: "chat", status: "active" };
function Harness() { state = useLiveChat(); return null; }

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.useFakeTimers(); jest.clearAllMocks();
  api.chats.mockResolvedValue({ chats: [chat], unread: 0 });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.useRealTimers(); });

test("slow message requests are not continuously replaced by polling", async () => {
  let finish;
  api.chatMessages.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  await act(async () => root.render(<Harness />));
  await act(async () => state.setOpen(true));
  await act(async () => jest.advanceTimersByTime(9000));
  expect(api.chatMessages).toHaveBeenCalledTimes(1);
  await act(async () => finish({ chat, messages: [{ id: "latest", text: "Последнее сообщение" }] }));
  expect(state.messages[0].id).toBe("latest");
});

test("sending preserves a bounded latest window and ignores an older in-flight response", async () => {
  const messages = Array.from({ length: 200 }, (_, i) => ({ id: String(i), text: String(i) }));
  api.chatMessages.mockResolvedValueOnce({ chat, messages });
  await act(async () => root.render(<Harness />));
  await act(async () => state.setOpen(true));
  let finish;
  api.chatMessages.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  await act(async () => jest.advanceTimersByTime(3000));
  api.sendChatMessage.mockResolvedValue({ id: "new", text: "Новое", created_at: "2026-09-23" });
  await act(async () => state.send("Новое"));
  await act(async () => finish({ chat, messages }));
  expect(state.messages).toHaveLength(200);
  expect(state.messages[199].id).toBe("new");
  expect(state.messages[0].id).toBe("1");
});
