import React, { useState } from "react";
import { useLang } from "../../lib/i18n";
import SbpTopUp from "./SbpTopUp";
import XrocketTopUp from "./XrocketTopUp";

export default function RubTopUp({ onChanged }) {
  const [method, setMethod] = useState("xrocket");
  const { t } = useLang();
  return <div className="space-y-4">
    <div className="grid grid-cols-2 gap-2" role="group" aria-label={t("xrocket.method")}>
      <button type="button" onClick={() => setMethod("xrocket")} aria-pressed={method === "xrocket"} className={`flex items-center gap-2.5 rounded-xl border p-3 text-left transition-colors ${method === "xrocket" ? "border-[#00a2ff]/70 bg-[#00a2ff]/10" : "border-transparent bg-[#15161c] hover:bg-[#252630]"}`} data-testid="payment-method-xrocket">
        <img src="/payments/xrocket.jpg" alt="" className="w-9 h-9 rounded-xl" />
        <span className="min-w-0"><b className="block text-[13px]">xRocket</b><span className="block text-[10px] text-[#8e91a3]">{t("xrocket.crypto")}</span></span>
      </button>
      <button type="button" onClick={() => setMethod("sbp")} aria-pressed={method === "sbp"} className={`flex items-center gap-2.5 rounded-xl border p-3 text-left transition-colors ${method === "sbp" ? "border-[#ffb000]/70 bg-[#ffb000]/10" : "border-transparent bg-[#15161c] hover:bg-[#252630]"}`} data-testid="payment-method-sbp">
        <span className="w-9 h-9 shrink-0 rounded-xl bg-[#ffb000]/10 text-[#ffb000] flex items-center justify-center font-black text-xl">₽</span>
        <span><b className="block text-[13px]">{t("xrocket.sbp")}</b><span className="block text-[10px] text-[#8e91a3]">{t("xrocket.via_support")}</span></span>
      </button>
    </div>
    {method === "xrocket" ? <XrocketTopUp onChanged={onChanged} /> : <SbpTopUp />}
  </div>;
}
