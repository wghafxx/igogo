import React, { useEffect, useState } from "react";
import { SettingsIcon } from "./icons/settings";
import { RefreshCWIcon } from "./icons/refresh-cw";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { RadioGroup, RadioGroupItem } from "./ui/radio-group";
import { DEFAULT_SETTINGS } from "../hooks/useSession";
import { prepareResultSounds } from "../lib/sound";
import { useLang } from "../lib/i18n";

const NumInput = ({ prefix, suffix, value, onChange, testId }) => (
  <div className="h-9 w-[46px] shrink-0 rounded-md bg-[#0f1015] border-0 flex items-center justify-center text-[13px] font-bold focus-within:border-[#00a2ff]">
    {prefix && <span className="text-[#8e91a3] text-[11px]">{prefix}</span>}
    <input
      value={value}
      inputMode="numeric"
      aria-label={testId}
      onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 3))}
      className="w-6 bg-transparent outline-none text-center"
      data-testid={testId}
    />
    {suffix && <span className="text-[#8e91a3] text-[11px]">{suffix}</span>}
  </div>
);

const RadioOption = ({ value, title, desc }) => (
  <label className="flex items-start gap-2 cursor-pointer">
    <RadioGroupItem value={value} data-testid={`settings-radio-${value}`} className="mt-0.5 border-[#6b6f85] text-[#00a2ff] data-[state=checked]:border-[#00a2ff]" />
    <div>
      <div className="text-[13px] font-bold">{title}</div>
      <div className="text-[11px] text-[#8e91a3] mt-0.5">{desc}</div>
    </div>
  </label>
);

export default function SettingsModal({ open, onOpenChange, settings, onSave }) {
  const { t } = useLang();
  const [draft, setDraft] = useState(settings);

  useEffect(() => {
    if (open) setDraft(settings);
  }, [open, settings]);

  const setMult = (i, v) => setDraft((d) => ({ ...d, multipliers: d.multipliers.map((m, idx) => (idx === i ? v : m)) }));
  const setPct = (i, v) => setDraft((d) => ({ ...d, percents: d.percents.map((m, idx) => (idx === i ? v : m)) }));

  const save = () => {
    if (draft.sound) prepareResultSounds();
    const clean = {
      ...draft,
      multipliers: draft.multipliers.map((m) => Math.max(2, Math.min(100, Number(m) || 2))),
      percents: draft.percents.map((p) => Math.max(1, Math.min(75, Number(p) || 1))),
    };
    onSave(clean);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#16171d] border-0 text-white sm:max-w-[470px] p-0 max-h-[92dvh] overflow-y-auto" data-testid="settings-modal">
        <DialogHeader className="px-5 py-4 border-b border-[#262833]">
          <DialogTitle className="flex items-center gap-2 text-[16px]">
            <SettingsIcon size={16} /> {t("settings.title")}
          </DialogTitle>
        </DialogHeader>

        <div className="px-5 py-4 space-y-5">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="font-bold text-[14px]">{t("settings.quick")}</div>
              <button
                className="text-[12px] text-[#00a2ff] font-semibold hover:underline"
                onClick={() => setDraft((d) => ({ ...d, multipliers: DEFAULT_SETTINGS.multipliers, percents: DEFAULT_SETTINGS.percents }))}
                data-testid="settings-reset-all"
              >
                {t("settings.default")}
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="rounded-lg bg-[#1c1d25] border-0 p-3">
                <div className="text-[11px] text-[#8e91a3] mb-3 leading-snug">{t("settings.mult_hint")}</div>
                <div className="flex items-center gap-1.5">
                  {draft.multipliers.map((m, i) => (
                    <NumInput key={i} prefix="x" value={m} onChange={(v) => setMult(i, v)} testId={`settings-mult-${i}`} />
                  ))}
                  <button data-testid="settings-reset-multipliers" aria-label={t("settings.reset_mult")} className="ml-auto text-[#00a2ff] hover:rotate-[-90deg] transition-transform" onClick={() => setDraft((d) => ({ ...d, multipliers: DEFAULT_SETTINGS.multipliers }))}>
                    <RefreshCWIcon size={16} />
                  </button>
                </div>
              </div>
              <div className="rounded-lg bg-[#1c1d25] border-0 p-3">
                <div className="text-[11px] text-[#8e91a3] mb-3 leading-snug">{t("settings.pct_hint")}</div>
                <div className="flex items-center gap-1.5">
                  {draft.percents.map((p, i) => (
                    <NumInput key={i} suffix="%" value={p} onChange={(v) => setPct(i, v)} testId={`settings-pct-${i}`} />
                  ))}
                  <button data-testid="settings-reset-percents" aria-label={t("settings.reset_pct")} className="ml-auto text-[#00a2ff] hover:rotate-[-90deg] transition-transform" onClick={() => setDraft((d) => ({ ...d, percents: DEFAULT_SETTINGS.percents }))}>
                    <RefreshCWIcon size={16} />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div>
            <div className="font-bold text-[14px] mb-2">{t("settings.sound")}</div>
            <RadioGroup value={draft.sound ? "on" : "off"} onValueChange={(v) => setDraft((d) => ({ ...d, sound: v === "on" }))} className="space-y-2" data-testid="sound-radio">
              <RadioOption value="on" title={t("settings.sound_on")} desc={t("settings.sound_on_desc")} />
              <RadioOption value="off" title={t("settings.sound_off")} desc={t("settings.sound_off_desc")} />
            </RadioGroup>
          </div>

          <div>
            <div className="font-bold text-[14px] mb-2">{t("settings.spin")}</div>
            <RadioGroup value={draft.fastSpin ? "fast" : "normal"} onValueChange={(v) => setDraft((d) => ({ ...d, fastSpin: v === "fast" }))} className="space-y-2" data-testid="spin-radio">
              <RadioOption value="normal" title={t("settings.spin_normal")} desc={t("settings.spin_normal_desc")} />
              <RadioOption value="fast" title={t("settings.spin_fast")} desc={t("settings.spin_fast_desc")} />
            </RadioGroup>
          </div>

          <div className="flex justify-center pt-1">
            <button className="blox-btn-primary h-10 px-6 text-[13px]" onClick={save} data-testid="settings-save">
              {t("settings.save")}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
