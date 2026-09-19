import React, { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { adminApi } from "../../../lib/api";

export function commandPreview(text, commands) {
  const input = text.trim();
  if (!input.startsWith("/")) return null;
  const match = input.slice(1).match(/^(\S+)(?:\s+([\s\S]*))?$/);
  const name = match?.[1]?.toLowerCase() || "";
  const args = match?.[2]?.trim() || "";
  const command = commands.find((c) => c.command === name);
  if (!command) return { error: "Выберите команду из списка или создайте её в разделе «Быстрые команды»." };
  const needsArgs = /\{(?:nick|args)\}/.test(command.text);
  if (needsArgs && !args) return { error: `После /${name} укажите ${command.text.includes("{nick}") ? "ник" : "текст"}.` };
  if (!needsArgs && args) return { error: `Команда /${name} используется без дополнительного текста.` };
  const result = command.text.replace(/\{(?:nick|args)\}/g, () => args);
  return result.length > 2000 ? { error: "Ответ команды длиннее 2000 символов." } : { text: result };
}

export default function CommandComposer({ text, setText, busy, onSend, placeholder }) {
  const [commands, setCommands] = useState([]);
  const [error, setError] = useState(false);
  const input = useRef(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try { const rows = await adminApi.commands(); if (alive) { setCommands(rows); setError(false); } }
      catch { if (alive) setError(true); }
    };
    load();
    const timer = setInterval(load, 20000);
    return () => { alive = false; clearInterval(timer); };
  }, []);
  const preview = commandPreview(text, commands);
  const prefix = text.trim().slice(1).split(/\s/)[0].toLowerCase();
  const suggestions = text.trim().startsWith("/") && !/\s/.test(text.trim().slice(1)) ? commands.filter((c) => c.command.startsWith(prefix)) : [];
  const disabled = busy || !text.trim() || Boolean(preview?.error);
  return <footer className="p-3 border-t border-white/[0.05] space-y-2 shrink-0">
    {suggestions.length > 0 && <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto" aria-label="Быстрые команды">
      {suggestions.map((c) => <button type="button" disabled={busy} key={c.id} onClick={() => { setText(`/${c.command}${/\{(?:nick|args)\}/.test(c.text) ? " " : ""}`); input.current?.focus(); }} className="rounded-lg bg-white/[0.08] hover:bg-white/[0.15] text-[#ffcf5a] text-[12px] px-3 py-2">/{c.command}{c.text.includes("{nick}") ? " <ник>" : c.text.includes("{args}") ? " <текст>" : ""}</button>)}
    </div>}
    {preview && <div className={`rounded-xl p-3 text-[12px] whitespace-pre-wrap break-words max-h-40 overflow-y-auto ${preview.error ? "bg-[#ffb000]/10 text-[#ffcf5a]" : "bg-white/[0.04] text-[#b4b7c7]"}`} data-testid="command-preview">
      {error && !preview.text ? "Не удалось загрузить команды. Повторяем загрузку…" : preview.error || <><b className="block mb-1">Игрок получит:</b>{preview.text}</>}
    </div>}
    <div className="flex items-end gap-2">
      <textarea ref={input} value={text} disabled={busy} onChange={(e) => setText(e.target.value.slice(0, 2000))} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!disabled) onSend(); } }} rows={1} placeholder={placeholder} className="flex-1 min-w-0 min-h-[46px] max-h-32 resize-none rounded-xl bg-white/[0.05] px-4 py-3 text-[13px] outline-none focus:bg-white/[0.08] placeholder:text-[#6b6f84]" data-testid="admin-chat-input" />
      <button onClick={onSend} disabled={disabled} className="w-[46px] h-[46px] shrink-0 rounded-xl bg-[#ffb000] hover:bg-[#ffc233] disabled:opacity-40 text-black flex items-center justify-center" aria-label="Отправить" data-testid="admin-chat-send-button"><Send size={17} /></button>
    </div>
    <p className="text-[10px] text-[#6b6f84]">/ — быстрые команды · Shift+Enter — новая строка</p>
  </footer>;
}
