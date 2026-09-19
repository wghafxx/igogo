import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "./useAuth";

export function useLiveChat() {
  const { authUser } = useAuth();
  const [open, setOpen] = useState(false);
  const [chat, setChat] = useState(null);
  const [unread, setUnread] = useState(0);
  const [messages, setMessages] = useState([]);
  const [cooldownUntil, setCooldownUntil] = useState(0);
  const [error, setError] = useState(false);
  const openRef = useRef(open);
  openRef.current = open;
  const chatId = chat?.id || null;

  const applyCooldown = useCallback((seconds) => setCooldownUntil(seconds > 0 ? Date.now() + seconds * 1000 : 0), []);

  const loadChats = useCallback(async () => {
    try {
      const data = await api.chats();
      const first = data.chats[0] || null;
      setChat((prev) => (first && prev && prev.id === first.id && prev.status === first.status && prev.updated_at === first.updated_at ? prev : first));
      setUnread(data.unread);
      applyCooldown(Number(data.cooldown_seconds) || 0);
      setError(false);
      return first;
    } catch {
      setError(true);
      return null;
    }
  }, [applyCooldown]);

  const loadMessages = useCallback(async (id) => {
    if (!id) return;
    try {
      const data = await api.chatMessages(id);
      setChat(data.chat);
      setMessages(data.messages);
      setUnread(0);
      setError(false);
    } catch (e) {
      if (e?.response?.status === 404) { setChat(null); setMessages([]); loadChats(); }
      else setError(true);
    }
  }, [loadChats]);

  useEffect(() => {
    setChat(null);
    setMessages([]);
    loadChats();
  }, [authUser?.session_id, loadChats]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (openRef.current && chatId) loadMessages(chatId);
      else loadChats();
    }, open ? 3000 : 12000);
    return () => clearInterval(timer);
  }, [open, chatId, loadChats, loadMessages]);

  useEffect(() => {
    if (open && chatId) loadMessages(chatId);
  }, [open, chatId, loadMessages]);

  useEffect(() => {
    const handler = () => { setOpen(true); loadChats(); };
    window.addEventListener("open-live-chat", handler);
    return () => window.removeEventListener("open-live-chat", handler);
  }, [loadChats]);

  const send = useCallback(async (text) => {
    if (!text.trim()) return;
    if (!chatId) {
      const created = await api.createChat({ kind: "support", text: text.trim() });
      setChat(created);
      await Promise.all([loadMessages(created.id), loadChats()]);
      return;
    }
    const msg = await api.sendChatMessage(chatId, text.trim());
    setMessages((rows) => [...rows, msg]);
    setChat((c) => (c ? { ...c, updated_at: msg.created_at } : c));
  }, [chatId, loadMessages, loadChats]);

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
    setChat(updated);
    await loadMessages(chatId);
    await loadChats();
  }, [chatId, loadMessages, loadChats]);

  return { open, setOpen, chat, unread, messages, send, close, reopen, cooldownUntil, error, retry: () => (chatId ? loadMessages(chatId) : loadChats()) };
}
