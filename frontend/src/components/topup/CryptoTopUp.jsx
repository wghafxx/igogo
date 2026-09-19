import React, { useState } from "react";
import { useLang } from "../../lib/i18n";
import XrocketTopUp from "./XrocketTopUp";

const METHODS = [
  ["cryptobot", "CryptoBot", "/payments/cryptobot.png", "cryptobot.crypto"],
  ["xrocket", "xRocket", "/payments/xrocket.jpg", "xrocket.crypto"],
];

export default function CryptoTopUp({ onChanged }) {
  const [method, setMethod] = useState("cryptobot");
  const { t } = useLang();
  return <div data-testid="crypto-topup">
    <div className="grid grid-cols-2 gap-1.5" role="group" aria-label={t("crypto.method")}>
      {METHODS.map(([key, name, logo, sub]) => (
        <button type="button" key={key} onClick={() => setMethod(key)} aria-pressed={method === key} className="m-tile min-h-[100px] flex items-center justify-center gap-3 px-3 text-left" data-testid={`payment-method-${key}`}>
          <img src={logo} alt="" width={44} height={44} className="w-11 h-11 shrink-0 rounded-xl" />
          <span className="min-w-0"><b className="block text-[16px] font-bold">{name}</b><span className="block text-[11px] text-white/50">{t(sub)}</span></span>
        </button>
      ))}
    </div>
    <XrocketTopUp key={method} provider={method} onChanged={onChanged} />
  </div>;
}
