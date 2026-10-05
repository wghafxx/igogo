import React from "react";

// Use the supplied image's visible bounds; its transparent margins stay outside the icon.
export default function TelegramIcon({ size = 18, className = "" }) {
  return <svg width={size} height={size} viewBox="832 333 1336 1334" className={`shrink-0 ${className}`} aria-hidden="true">
    <image href="/telegram-logo.png" width="3000" height="2000" />
  </svg>;
}
