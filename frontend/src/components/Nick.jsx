import React from "react";

// Nickname with optional gold (promo) styling
export default function Nick({ children, gold = false, className = "", testId }) {
  return (
    <span className={`${gold ? "gold-nick" : ""} ${className}`} data-testid={testId} data-gold={gold ? "true" : "false"}>
      {children}
    </span>
  );
}
