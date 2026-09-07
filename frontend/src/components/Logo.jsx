import React from "react";

export const Logo = ({ size = 28, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 100 100"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    aria-label="BLOXGRADE logo"
  >
    <defs>
      <linearGradient id="lg-blue" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#38bdff" />
        <stop offset="1" stopColor="#0090e6" />
      </linearGradient>
      <linearGradient id="lg-orange" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#ffa21f" />
        <stop offset="1" stopColor="#f07a00" />
      </linearGradient>
    </defs>
    <path d="M50 6 L92 34 L92 58 L50 30 L8 58 L8 34 Z" fill="url(#lg-blue)" />
    <path d="M50 46 L86 70 L86 94 L50 70 L14 94 L14 70 Z" fill="url(#lg-orange)" />
  </svg>
);

export const RobuxIcon = ({ size = 14, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    aria-label="Robux"
  >
    <path d="M12 1.5 21.1 6.75v10.5L12 22.5 2.9 17.25V6.75L12 1.5Z" fill="#ffb000" />
    <path d="M12 4 18.9 8v8L12 20 5.1 16V8L12 4Z" fill="#ff8a00" />
    <rect x="8.5" y="8.5" width="7" height="7" rx="1" fill="#ffd27a" />
  </svg>
);

export const TelegramIcon = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-label="Telegram">
    <path d="M9.04 15.47 8.7 20.2c.48 0 .69-.2.94-.45l2.26-2.16 4.68 3.43c.86.47 1.47.22 1.7-.79L21.9 5.1c.28-1.25-.45-1.74-1.29-1.43L3.26 10.36c-1.22.47-1.2 1.15-.21 1.46l4.43 1.38 10.3-6.5c.48-.29.92-.13.56.16L9.04 15.47Z" />
  </svg>
);

export const VkIcon = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-label="VK">
    <path d="M13.16 19.5c-7.2 0-11.3-4.93-11.47-13.14h3.6c.12 6.02 2.78 8.57 4.88 9.1V6.36h3.4v5.2c2.07-.23 4.25-2.6 4.99-5.2h3.4c-.57 3.2-2.93 5.57-4.6 6.55 1.67.79 4.36 2.86 5.38 6.6h-3.74c-.8-2.5-2.8-4.44-5.43-4.7v4.7h-.41Z" />
  </svg>
);
