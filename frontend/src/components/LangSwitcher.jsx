import React from "react";
import { useLang } from "../lib/i18n";

const FlagRU = () => (
  <svg width="16" height="12" viewBox="0 0 18 13" className="rounded-[2px] overflow-hidden shrink-0" aria-hidden="true">
    <rect width="18" height="13" rx="2" fill="#f5f5f5" />
    <rect y="4.33" width="18" height="4.34" fill="#0039a6" />
    <rect y="8.67" width="18" height="4.33" fill="#d52b1e" />
  </svg>
);

const FlagGB = () => (
  <svg width="16" height="12" viewBox="0 0 18 13" className="rounded-[2px] overflow-hidden shrink-0" aria-hidden="true">
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
      title={label}
      data-testid={`lang-${code}`}
      className={`relative z-10 flex min-w-0 items-center justify-center gap-1.5 rounded-full text-[11px] font-semibold tracking-wide transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#00a2ff]/70 ${lang === code ? "text-[#f3f4f7]" : "text-[#8e91a3] hover:text-[#d7dae3]"}`}
    >
      <Flag />
      {code.toUpperCase()}
    </button>
  );
  return (
    <div className="relative isolate grid h-9 w-[124px] shrink-0 grid-cols-2 rounded-full border border-white/[0.07] bg-[#13151b] p-[3px] shadow-[inset_0_1px_3px_#0003]" role="group" aria-label={lang === "ru" ? "Язык интерфейса" : "Interface language"} data-testid="lang-switcher">
      <span aria-hidden="true" className={`pointer-events-none absolute inset-y-[3px] left-[3px] w-[calc(50%-3px)] rounded-full border border-white/[0.08] bg-gradient-to-b from-[#30343f] to-[#252831] shadow-[0_1px_4px_#0005] transition-transform duration-200 ease-out motion-reduce:transition-none ${lang === "en" ? "translate-x-full" : "translate-x-0"}`} />
      {btn("ru", FlagRU, "Русский")}
      {btn("en", FlagGB, "English")}
    </div>
  );
}
