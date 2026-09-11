import React from "react";
import { useLang } from "../lib/i18n";

const FlagRU = () => (
  <svg width="18" height="13" viewBox="0 0 18 13" className="rounded-[2px] shrink-0" aria-hidden="true">
    <rect width="18" height="13" rx="2" fill="#f5f5f5" />
    <rect y="4.33" width="18" height="4.34" fill="#0039a6" />
    <rect y="8.67" width="18" height="4.33" fill="#d52b1e" />
  </svg>
);

const FlagGB = () => (
  <svg width="18" height="13" viewBox="0 0 18 13" className="rounded-[2px] shrink-0" aria-hidden="true">
    <rect width="18" height="13" rx="2" fill="#012169" />
    <path d="M0 0l18 13M18 0L0 13" stroke="#fff" strokeWidth="2.4" />
    <path d="M0 0l18 13M18 0L0 13" stroke="#C8102E" strokeWidth="1" />
    <path d="M9 0v13M0 6.5h18" stroke="#fff" strokeWidth="3.6" />
    <path d="M9 0v13M0 6.5h18" stroke="#C8102E" strokeWidth="2" />
  </svg>
);

export default function LangSwitcher() {
  const { lang, setLang } = useLang();
  const btn = (code, Flag, label) => (
    <button
      key={code}
      type="button"
      onClick={() => setLang(code)}
      aria-label={label}
      aria-pressed={lang === code}
      data-testid={`lang-${code}`}
      className={`h-9 px-2 flex items-center gap-1.5 rounded-md text-[12px] font-black transition-colors ${lang === code ? "bg-[#ffb000] text-black" : "text-[#8e91a3] hover:text-white"}`}
    >
      <Flag />
      {code.toUpperCase()}
    </button>
  );
  return (
    <div className="flex items-center gap-0.5 rounded-lg bg-[#0f1015] p-1" data-testid="lang-switcher" title="RU / EN">
      {btn("ru", FlagRU, "Русский")}
      {btn("en", FlagGB, "English")}
    </div>
  );
}
