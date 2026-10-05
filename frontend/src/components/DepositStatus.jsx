import React from "react";
import { useLang } from "../lib/i18n";

const STATES = {
  creating: ["xrocket.creating", "text-[#ffb000]"],
  awaiting_payment: ["xrocket.waiting", "text-[#ffb000]"],
  expired: ["xrocket.expired", "text-[#9a9db0]"],
  payment_error: ["xrocket.failed", "text-[#ff5c5c]"],
  pending: ["topup.status_pending", "text-[#ffb000]"],
  processing: ["topup.status_processing", "text-[#ffb000]"],
  confirmed: ["topup.status_confirmed", "text-[#2ecc71]"],
  rejected: ["topup.status_rejected", "text-[#ff5c5c]"],
  cancelled: ["topup.status_cancelled", "text-[#9a9db0]"],
};

export const DepositStatus = ({ status }) => {
  const { t } = useLang();
  const state = STATES[status];
  return <span className={`font-bold ${state?.[1] || ""}`}>{state ? t(state[0]) : status}</span>;
};
