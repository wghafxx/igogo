import React from "react";
import { parseServerDate } from "../../../lib/api";

export const STATUS = {
  open: { label: "Ждёт ответа", dot: "bg-[#ffb000]", pill: "bg-[#ffb000]/15 text-[#ffcf5a]" },
  active: { label: "В работе", dot: "bg-[#2ecc71]", pill: "bg-[#2ecc71]/15 text-[#7ee2a8]" },
  closed: { label: "Закрыт", dot: "bg-[#5f6377]", pill: "bg-white/[0.06] text-[#8e91a3]" },
};

export const fmtTime = (d) => {
  const date = parseServerDate(d);
  const sameDay = new Date().toDateString() === date.toDateString();
  return date.toLocaleString("ru-RU", sameDay ? { hour: "2-digit", minute: "2-digit" } : { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
};

export const ago = (iso) => {
  const mins = Math.max(0, Math.floor((Date.now() - parseServerDate(iso).getTime()) / 60000));
  if (mins < 1) return "только что";
  if (mins < 60) return `${mins} мин`;
  const h = Math.floor(mins / 60);
  return h < 48 ? `${h} ч` : `${Math.floor(h / 24)} дн`;
};

export const Avatar = ({ src, name = "", size = 40, className = "" }) => (
  src ? (
    <img src={src} alt="" width={size} height={size} style={{ width: size, height: size }} className={`rounded-full object-cover bg-[#23242c] shrink-0 ${className}`} />
  ) : (
    <span style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }} className={`rounded-full bg-[#23242c] text-[#a4a7b8] font-black flex items-center justify-center shrink-0 uppercase ${className}`}>{(name || "?").trim().slice(0, 1)}</span>
  )
);

export const StatusPill = ({ status, testId }) => {
  const s = STATUS[status] || STATUS.closed;
  return <span className={`inline-flex items-center gap-1.5 h-6 px-2 rounded-full text-[11px] font-bold ${s.pill}`} data-testid={testId}><span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />{s.label}</span>;
};

export const Card = ({ title, icon: Icon, right, children, className = "", testId }) => (
  <section className={`rounded-2xl bg-[#13141a] border border-white/[0.05] ${className}`} data-testid={testId}>
    {title && (
      <header className="h-11 px-4 flex items-center gap-2 border-b border-white/[0.05]">
        {Icon && <Icon size={15} className="text-[#a4a7b8]" />}
        <span className="text-[12px] font-bold uppercase tracking-wide text-[#c9ccd6]">{title}</span>
        <span className="ml-auto flex items-center gap-2">{right}</span>
      </header>
    )}
    <div className="p-4">{children}</div>
  </section>
);

export const Field = ({ label, children }) => (
  <label className="block space-y-1.5">
    <span className="text-[11px] font-semibold text-[#8e91a3]">{label}</span>
    {children}
  </label>
);

export const Btn = ({ tone = "neutral", size = "md", className = "", ...props }) => {
  const tones = {
    primary: "bg-[#ffb000] hover:bg-[#ffc233] text-black",
    success: "bg-[#2ecc71] hover:bg-[#3ddb80] text-black",
    danger: "bg-[#ff5c5c]/12 text-[#ff8a8a] hover:bg-[#ff5c5c] hover:text-white",
    neutral: "bg-white/[0.06] hover:bg-white/[0.1] text-white",
    ghost: "text-[#8e91a3] hover:text-white hover:bg-white/[0.06]",
  };
  const sizes = { sm: "h-8 px-3 text-[12px] rounded-lg", md: "h-10 px-4 text-[13px] rounded-xl", lg: "h-12 px-5 text-[14px] rounded-xl" };
  return <button type="button" className={`inline-flex items-center justify-center gap-1.5 font-bold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${tones[tone]} ${sizes[size]} ${className}`} {...props} />;
};
