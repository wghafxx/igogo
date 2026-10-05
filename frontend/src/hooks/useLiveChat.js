import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { compressScreenshot } from "../lib/image-compress";
import { EVENTS, onEvent } from "../lib/events";
import { useAuth } from "./useAuth";
import { usePolling } from "./usePolling";

const WINDOW = 200;
const mergeMessages = (rows, extra) => {
  const seen = new Set(extra.map((m) => m.id));
  return [...rows.filter((m) => !seen.has(m.id)), ...extra].slice(-WINDOW);
};

export function useLiveChat() {
  const { authUser } = useAuth();
  const [open, setOpen] = useState(false);
  const [chat, setChat] = useState(null);
  const [unread, setUnread] = useState(0);
  const [messages, setMessages] = useState([]);
  const [cooldownUntil, setCooldownUntil] = useState(0);
  const [error, setError] = useState(false);
  const openRef = useRef(open);
  const messagesVersion = useRef(0);
  const accountVersion = useRef(0);
  const fetchingMessages = useRef(false);
  const requestedChatId = useRef(null);
  const loaded = useRef({ chatId: null, status: null, last: null });
  openRef.current = open;
  const chatId = chat?.id || null;

  const applyCooldown = useCallback((seconds) => setCooldownUntil(seconds > 0 ? Date.now() + seconds * 1000 : 0), []);

  const loadMessages = useCallback(async (id) => {
    if (!id || fetchingMessages.current) return;
    fetchingMessages.current = true;
    const version = ++messagesVersion.current;
    const account = accountVersion.current;
    const prev = loaded.current;
    const after = prev.chatId === id && prev.last ? prev.last : undefined;
    try {
      const data = await api.chatMessages(id, after);
      if (version !== messagesVersion.current || account !== accountVersion.current) return;
      const statusChanged = Boolean(after) && data.chat?.status !== prev.status;
      const rows = data.messages || [];
      if (after && !statusChanged) setMessages((old) => mergeMessages(old, rows));
      else setMessages(rows.slice(-WINDOW));
      loaded.current = { chatId: id, status: data.chat?.status, last: rows.length ? rows[rows.length - 1].created_at : after && !statusChanged ? prev.last : null };
      setChat(data.chat);
      setUnread(0);
      setError(false);
      // A reopen/accept may have archived the old conversation: take a full snapshot once.
      if (statusChanged) { loaded.current = { chatId: id, status: data.chat?.status, last: null }; fetchingMessages.current = false; await loadMessages(id); }
    } catch (e) {
      if (version !== messagesVersion.current || account !== accountVersion.current) return;
      if (e?.response?.status === 404) { setChat(null); setMessages([]); loaded.current = { chatId: null, status: null, last: null }; }
      else setError(true);
    } finally { fetchingMessages.current = false; }
  }, []);

  const loadChats = useCallback(async () => {
    const account = accountVersion.current;
    try {
      const data = await api.chats();
      // A response for the previous account must not bring its chat back.
      if (account !== accountVersion.current) return null;
      const wanted = requestedChatId.current;
      const first = (wanted && data.chats.find((c) => c.id === wanted)) || data.chats[0] || null;
      if (wanted && first?.id !== wanted) {
        requestedChatId.current = null;
        await loadMessages(wanted);
        return null;
      }
      requestedChatId.current = null;
      setChat((prev) => (first && prev && prev.id === first.id && prev.status === first.status && prev.updated_at === first.updated_at ? prev : first));
      setUnread(data.unread);
      applyCooldown(Number(data.cooldown_seconds) || 0);
      setError(false);
      return first;
    } catch {
      if (account === accountVersion.current) setError(true);
      return null;
    }
  }, [applyCooldown, loadMessages]);

  useEffect(() => {
    accountVersion.current += 1;
    messagesVersion.current += 1;
    loaded.current = { chatId: null, status: null, last: null };
    setChat(null);
    setMessages([]);
    loadChats();
  }, [authUser?.session_id, loadChats]);

  usePolling(() => (openRef.current && chatId ? loadMessages(chatId) : loadChats()), open ? 3000 : 12000);

  useEffect(() => {
    if (open && chatId) loadMessages(chatId);
  }, [open, chatId, loadMessages]);

  useEffect(() => onEvent(EVENTS.openLiveChat, (event) => {
    requestedChatId.current = event?.detail?.chatId || null;
    setOpen(true);
    loadChats();
  }), [loadChats]);

  const send = useCallback(async (text) => {
    if (!text.trim()) return;
    if (!chatId) {
      const created = await api.createChat({ kind: "support", text: text.trim() });
      setChat(created);
      await Promise.all([loadMessages(created.id), loadChats()]);
      return;
    }
    const msg = await api.sendChatMessage(chatId, text.trim());
    messagesVersion.current += 1;
    setMessages((rows) => mergeMessages(rows, [msg]));
    setChat((c) => (c ? { ...c, updated_at: msg.created_at } : c));
  }, [chatId, loadMessages, loadChats]);

  const attach = useCallback(async (file) => {
    if (!chatId) return;
    const blob = await compressScreenshot(file);
    const msg = await api.chatAttach(chatId, blob);
    messagesVersion.current += 1;
    setMessages((rows) => mergeMessages(rows, [msg]));
  }, [chatId]);

  const markPaid = useCallback(async (depositId) => {
    await api.donationPaid(depositId);
    if (chatId) await loadMessages(chatId);
  }, [chatId, loadMessages]);

  const close = useCallback(async () => {
    if (!chatId) return;
    const updated = await api.closeChat(chatId);
    setChat(updated);
    await loadMessages(chatId);
    await loadChats();
  }, [chatId, loadMessages, loadChats]);

  const reopen = useCallback(async () => {
    if (!chatId) return;
    const updated = await api.reopenChat(chatId);
    messagesVersion.current += 1;
    loaded.current = { chatId: null, status: null, last: null };
    setMessages([]);
    setChat(updated);
    await loadMessages(chatId);
    await loadChats();
  }, [chatId, loadMessages, loadChats]);

  return { open, setOpen, chat, unread, messages, send, attach, markPaid, close, reopen, cooldownUntil, error, retry: () => (chatId ? loadMessages(chatId) : loadChats()) };
}
