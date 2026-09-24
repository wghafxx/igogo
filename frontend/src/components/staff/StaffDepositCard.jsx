import React, { useState } from "react";
import { toast } from "sonner";
import { Camera, PackageCheck } from "lucide-react";
import { staffApi, errText, fmtRap, StatePill } from "../../lib/staff-api";
import { Btn, Card } from "../admin/chat/ui";
import ItemsEditor, { emptyItem, itemsTotal, itemsValid, toPayload } from "./ItemsEditor";
import EvidenceUploader from "./EvidenceUploader";
import { EvidenceGallery } from "./EvidenceImage";

const Check = ({ checked, onChange, label, testId }) => (
  <label className="flex items-center gap-2.5 cursor-pointer text-[13px]">
    <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="w-4 h-4 accent-[#ffb000]" data-testid={testId} />{label}
  </label>
);

const note = "w-full rounded-lg bg-white/[0.05] p-3 text-[13px] outline-none";

// Every RAP credit needs a trade screenshot: the report goes to the owner, the server credits only after approval.
const IntakeForm = ({ chatId, user, previous, onDone }) => {
  const [items, setItems] = useState(() => previous?.items?.map((i) => ({ ...i })) || [emptyItem()]);
  const [evidence, setEvidence] = useState(() => previous?.evidence || []);
  const [received, setReceived] = useState(false);
  const [checked, setChecked] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const total = itemsTotal(items);
  const bonus = Number(user.promo_bonus || 0);
  const ok = itemsValid(items) && total >= 200 && evidence.length > 0 && received && checked;
  const submit = async () => {
    setBusy(true);
    try {
      const rep = await staffApi.chatReport(chatId, { items: toPayload(items), evidence, received, value_checked: checked, note: comment });
      toast.success(`Отправлено на подтверждение: ${fmtRap(rep.plan.credited)} RAP`);
      onDone();
    } catch (e) { toast.error(errText(e, "Не удалось отправить")); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-3" data-testid="staff-intake-form">
      {previous?.decision?.reason && <div className="m-note-warn rounded-lg px-3 py-2 text-[12px]" data-testid="staff-revision-reason">На доработку: {previous.decision.reason}</div>}
      <ItemsEditor items={items} onChange={setItems} />
      <div className="text-[12px] font-semibold text-[#8e91a3] inline-flex items-center gap-1.5"><Camera size={13} /> Скриншот трейда — обязательно</div>
      <EvidenceUploader value={evidence} onChange={setEvidence} upload={(file) => staffApi.chatEvidence(chatId, file, "intake")} testId="staff-intake-evidence" />
      <Check checked={received} onChange={setReceived} label="Скины получил" testId="staff-check-received" />
      <Check checked={checked} onChange={setChecked} label="Стоимость проверил" testId="staff-check-value" />
      <textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} rows={2} placeholder="Комментарий (необязательно)" className={note} data-testid="staff-intake-note" />
      <div className="rounded-xl bg-white/[0.04] p-3 text-[12px]" data-testid="staff-intake-estimate">
        {total > 0 && total < 200 ? <span className="text-[#ff9b9b]">Минимум 200 RAP</span>
          : <>Комиссия 20%{bonus ? ` · промо +${Math.round(bonus * 100)}%` : ""} · к выдаче ≈ <b className="text-[#7ee2a8]">{fmtRap(total * 0.8 * (1 + bonus))} RAP</b></>}
      </div>
      <Btn tone="primary" className="w-full" disabled={busy || !ok} onClick={submit} data-testid="staff-intake-submit">{busy ? "Отправка…" : "Отправить на подтверждение"}</Btn>
    </div>
  );
};

const ReturnForm = ({ chatId, dep, onDone }) => {
  const [evidence, setEvidence] = useState([]);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await staffApi.chatReturn(chatId, { evidence, note: "" }); toast.success("Возврат отправлен владельцу"); onDone(); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-3" data-testid="staff-return-form">
      <div className="m-note-err rounded-lg px-3 py-2 text-[12px]">Отклонено: {dep.staff_reason}. Верните скины игроку и приложите скриншот возврата.</div>
      <EvidenceUploader value={evidence} onChange={setEvidence} upload={(file) => staffApi.chatEvidence(chatId, file, "return")} testId="staff-return-evidence" />
      <Btn tone="primary" className="w-full" disabled={busy || !evidence.length} onClick={submit} data-testid="staff-return-submit">Подтвердить возврат</Btn>
    </div>
  );
};

export default function StaffDepositCard({ detail, onChanged }) {
  const { chat, user, deposit: dep, reports } = detail;
  const latest = reports?.[0];
  const state = dep?.staff_state;
  return (
    <Card title="Пополнение скинами" icon={PackageCheck} testId="staff-deposit-card" right={dep ? <StatePill state={state} testId="staff-deposit-state" /> : null}>
      {!detail.mine && <div className="text-[12px] text-[#8e91a3]">Примите чат, чтобы оформить пополнение.</div>}
      {detail.mine && (!dep || ["assigned", "revision"].includes(state)) && <IntakeForm key={latest?.id || chat.id} chatId={chat.id} user={user} previous={state === "revision" ? latest : null} onDone={onChanged} />}
      {detail.mine && state === "review" && (
        <div className="space-y-2 text-[13px]" data-testid="staff-deposit-review">
          <div className="text-[#ffcf5a]">v{latest?.version} на подтверждении у владельца: {fmtRap(latest?.total_rap)} RAP → {fmtRap(latest?.plan?.credited)} RAP. Можно вести другие чаты.</div>
          {latest && <EvidenceGallery ids={latest.evidence} load={staffApi.evidence} testId="staff-deposit-review-evidence" />}
        </div>
      )}
      {detail.mine && state === "return_required" && <ReturnForm chatId={chat.id} dep={dep} onDone={onChanged} />}
      {detail.mine && state === "return_review" && <div className="text-[13px] text-[#ff9b9b]">Возврат на проверке у владельца.</div>}
      {detail.mine && state === "approving" && <div className="text-[13px] text-[#7ee2a8]">Зачисляется…</div>}
    </Card>
  );
}
