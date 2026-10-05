import React, { useState } from "react";
import { toast } from "sonner";
import Stepper, { Step } from "./Stepper";
import { api } from "../lib/api";
import { useAuth } from "../hooks/useAuth";
import { useLang } from "../lib/i18n";
import { hasRobloxProfile, normalizeRobloxUsername, validDisplayName, validRobloxLink, validRobloxUsername } from "../lib/roblox";

export default function RobloxProfileStepper({ onSaved, required = false }) {
  const { authUser, setAuthUser } = useAuth();
  const { t } = useLang();
  const [displayName, setDisplayName] = useState(authUser?.roblox_display_name || "");
  const [username, setUsername] = useState(authUser?.roblox_nick || "");
  const [link, setLink] = useState(authUser?.roblox_link || "");
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const valid = [validDisplayName(displayName), validRobloxUsername(username), validRobloxLink(link)];
  const save = async () => {
    const profile = { roblox_display_name: displayName.trim(), roblox_nick: normalizeRobloxUsername(username), roblox_link: link.trim() };
    if (!hasRobloxProfile(profile)) return false;
    setBusy(true); setError("");
    try {
      const user = await api.saveRoblox(profile);
      setAuthUser(user);
      toast.success(t("roblox.saved"));
      onSaved?.(user);
      return true;
    } catch (e) {
      setError(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : t("roblox.save_fail"));
      return false;
    } finally { setBusy(false); }
  };
  return <div className="space-y-4" data-testid="roblox-profile-stepper">
    <div className="m-box p-4 text-[12px] leading-relaxed text-[#b4b7c7]">
      <b className="block text-white text-[14px] mb-1">{required ? t("roblox.title_required") : t("roblox.title")}</b>
      {t("roblox.intro")}
    </div>
    <Stepper onStepChange={(next) => { setStep(next); setError(""); }} onFinalStepCompleted={save} disableStepIndicators
      completeButtonText={busy ? t("roblox.saving") : required ? t("roblox.save_continue") : t("roblox.save")}
      nextButtonProps={{ disabled: busy || !valid[step - 1], "data-testid": "roblox-step-next" }} backButtonProps={{ disabled: busy, "data-testid": "roblox-step-back" }}>
      <Step>
        <div className="m-label mb-2">{t("roblox.step1_label")}</div>
        <h3 className="text-[19px] font-bold mb-2">{t("roblox.step1_title")}</h3>
        <p className="m-hint mb-4">{t("roblox.step1_hint")}</p>
        <label className="block"><span className="sr-only">{t("roblox.step1_input")}</span><div className="m-input m-input-sm"><input value={displayName} maxLength={20} onChange={(e) => setDisplayName(e.target.value)} placeholder={t("roblox.step1_placeholder")} autoComplete="off" data-testid="roblox-display-name-input" /></div></label>
        <p className="m-hint mt-2">{t("roblox.step1_rule")}</p>
      </Step>
      <Step>
        <div className="m-label mb-2">{t("roblox.step2_label")}</div>
        <h3 className="text-[19px] font-bold mb-2">{t("roblox.step2_title")}</h3>
        <p className="m-hint mb-4">{t("roblox.step2_hint")}</p>
        <label className="block"><span className="sr-only">{t("roblox.step2_input")}</span><div className="m-input m-input-sm"><span className="text-white/40">@</span><input value={username} maxLength={21} onChange={(e) => setUsername(e.target.value)} placeholder="BloxPlayer123" autoComplete="off" spellCheck={false} data-testid="roblox-nick-input" /></div></label>
        <p className="m-hint mt-2">{t("roblox.step2_rule")}</p>
      </Step>
      <Step>
        <div className="m-label mb-2">{t("roblox.step3_label")}</div>
        <h3 className="text-[19px] font-bold mb-2">{t("roblox.step3_title")}</h3>
        <p className="m-hint mb-4">{t("roblox.step3_hint")}</p>
        <label className="block"><span className="sr-only">{t("roblox.step3_input")}</span><div className="m-input m-input-sm"><input type="url" value={link} maxLength={400} onChange={(e) => { setLink(e.target.value); setError(""); }} placeholder="https://www.roblox.com/users/123/profile" autoComplete="off" data-testid="roblox-link-input" /></div></label>
        {link && !valid[2] && <p className="mt-2 text-[12px] text-[#ffb000]">{t("roblox.step3_invalid")}</p>}
        <div className="m-box p-3 mt-4 text-[12px]"><b className="block break-words">{displayName}</b><span className="text-white/50">@{normalizeRobloxUsername(username)}</span></div>
        {error && <p className="m-note-err rounded-lg p-3 mt-3 text-[12px]" role="alert">{error}</p>}
      </Step>
    </Stepper>
  </div>;
}
