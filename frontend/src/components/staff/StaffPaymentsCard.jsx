import React from "react";
import { Banknote } from "lucide-react";
import { Card, ago } from "../admin/chat/ui";

const METHOD = { donationalerts: "СБП / DonationAlerts", xrocket: "xRocket", cryptobot: "CryptoBot" };

// Read-only: staff sees money top-ups to guide the player; confirmation stays with the owner.
export default function StaffPaymentsCard({ payments }) {
  return (
    <Card title="Пополнение деньгами" icon={Banknote} testId="staff-payments-card">
      {payments.length === 0 ? <div className="text-[12px] text-[#6b6f84]" data-testid="staff-payments-empty">Нет открытых оплат</div> : (
        <div className="space-y-2">
          {payments.map((p) => (
            <div key={p.id} className="rounded-xl bg-white/[0.04] px-3 py-2 text-[12px] space-y-0.5" data-testid={`staff-payment-${p.id}`}>
              <div className="flex items-center gap-2"><b>{METHOD[p.payment_method] || p.payment_method}</b><span className="ml-auto text-[#8e91a3]">{ago(p.created_at)}</span></div>
              {p.declared_amount != null && <div>Сумма: {p.declared_amount} {p.declared_currency || ""}</div>}
              {p.da_code && <div>Код в комментарии доната: <b className="font-mono">{p.da_code}</b></div>}
              <div className={p.paid_claimed_at ? "text-[#7ee2a8]" : "text-[#ffcf5a]"}>{p.paid_claimed_at ? "Игрок нажал «Оплатил» — ждёт проверки главным" : "Ещё не оплачено"}</div>
            </div>
          ))}
        </div>
      )}
      <div className="mt-2 text-[11px] text-[#8e91a3] leading-snug">Если СБП не зачислилось автоматически — объясните оплату через донат (DonationAlerts) с кодом в комментарии и позовите главного.</div>
    </Card>
  );
}
