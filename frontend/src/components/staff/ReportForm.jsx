import React, { useState } from "react";
import { toast } from "sonner";
import Stepper, { Step } from "../Stepper";
import { staffApi, errText, fmtRap } from "../../lib/staff-api";
import ItemsEditor, { emptyItem, itemsTotal, itemsValid, toPayload } from "./ItemsEditor";
import EvidenceUploader from "./EvidenceUploader";

const FEE = 0.2;

const Check = ({ checked, onChange, label, testId }) => (
  <label className="flex items-center gap-2.5 cursor-pointer text-[13px]">
    <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="w-4 h-4 accent-[#ffb000]" data-testid={testId} />
    {label}
  </label>
);

const PlayerStep = ({ dep }) => (
  <div className="space-y-2 text-[13px]" data-testid="report-step-player">
    <div className="text-[12px] text-[#8e91a3]">Получатель пополнения подставлен из заявки и не меняется.</div>
    <div className="rounded-xl bg-white/[0.04] p-3 space-y-1">
      <div><span className="text-[#8e91a3]">Игрок:</span> <b>{dep.nickname}</b> · Discord {dep.discord_id}</div>
      <div><span className="text-[#8e91a3]">Roblox:</span> {dep.roblox_display_name} (@{dep.roblox_nick})</div>
      <a href={dep.roblox_link} target="_blank" rel="noopener noreferrer" className="text-[#60a5fa] underline break-all">{dep.roblox_link}</a>
      <div><span className="text-[#8e91a3]">Заявлено игроком:</span> ~{fmtRap(dep.expected_rap)} RAP{dep.promo_code ? ` · промокод ${dep.promo_code} (+${Math.round(dep.promo_bonus * 100)}%)` : ""}</div>
    </div>
  </div>
);

export default function ReportForm({ dep, previous, onSubmitted }) {
  const [items, setItems] = useState(() => previous?.items?.map((i) => ({ ...i })) || [emptyItem()]);
  const [evidence, setEvidence] = useState(() => previous?.evidence || []);
  const [received, setReceived] = useState(false);
  const [checked, setChecked] = useState(false);
  const [note, setNote] = useState("");
  const [step, setStep] = useState(1);
  const total = itemsTotal(items);
  const credited = total * (1 - FEE) * (1 + Number(dep.promo_bonus || 0));
  const canSubmit = itemsValid(items) && total >= 200 && evidence.length > 0 && received && checked;
  const submit = async () => {
    try {
      const rep = await staffApi.report(dep.id, { items: toPayload(items), evidence, received, value_checked: checked, note });
      toast.success(`Отчёт v${rep.version} отправлен на проверку`);
      onSubmitted?.(rep);
      return true;
    } catch (e) { toast.error(errText(e, "Не удалось отправить отчёт")); return false; }
  };
  const nextDisabled = (step === 2 && (!itemsValid(items) || total < 200)) || (step === 3 && !canSubmit);
  return (
    <div data-testid="report-form">
      {previous?.decision?.reason && <div className="m-note-warn rounded-lg px-3 py-2 text-[12px] mb-3" data-testid="report-revision-reason">На доработку: {previous.decision.reason}</div>}
      <Stepper onStepChange={setStep} onFinalStepCompleted={submit} disableStepIndicators completeButtonText="Отправить на проверку"
        nextButtonProps={{ disabled: nextDisabled, "data-testid": "report-next-button" }} backButtonProps={{ "data-testid": "report-back-button" }}>
        <Step><PlayerStep dep={dep} /></Step>
        <Step>
          <div className="space-y-3" data-testid="report-step-items">
            <ItemsEditor items={items} onChange={setItems} />
            {total > 0 && total < 200 && <div className="m-note-err rounded-lg px-3 py-2 text-[12px]">Минимум 200 RAP</div>}
            <div className="rounded-xl bg-white/[0.04] p-3 text-[12px] space-y-0.5" data-testid="report-estimate">
              <div>Комиссия 20%: −{fmtRap(total * FEE)} RAP{dep.promo_bonus ? ` · промобонус +${Math.round(dep.promo_bonus * 100)}%` : ""}</div>
              <div>Ориентировочно к выдаче: <b>{fmtRap(credited)} RAP</b> (точный расчёт делает сервер)</div>
            </div>
          </div>
        </Step>
        <Step>
          <div className="space-y-3" data-testid="report-step-evidence">
            <EvidenceUploader value={evidence} onChange={setEvidence} purpose="intake" depositId={dep.id} testId="report-evidence" />
            <Check checked={received} onChange={setReceived} label="Скины получил" testId="report-check-received" />
            <Check checked={checked} onChange={setChecked} label="Стоимость проверил" testId="report-check-value" />
            <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={2} placeholder="Комментарий (необязательно)" className="w-full rounded-lg bg-white/[0.05] p-3 text-[13px] outline-none" data-testid="report-note" />
          </div>
        </Step>
      </Stepper>
    </div>
  );
}
