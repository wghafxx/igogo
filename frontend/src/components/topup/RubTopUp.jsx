import React, { useState } from "react";
import { toast } from "sonner";
import { RobuxIcon } from "../Logo";
import { useAuth } from "../../hooks/useAuth";
import { SUPPORT_HANDLE } from "../SupportDialog";

const SUPPORT_URL = process.env.REACT_APP_TELEGRAM_SUPPORT_URL;

// Тариф: 1 RAP = 0,50 ₽. Минимальный платёж — 35 ₽ (70 RAP).
export const RAP_RUB_RATE = 0.5;
export const PACKAGES = [
  { rap: 70, rub: 35 },
  { rap: 100, rub: 50 },
  { rap: 200, rub: 100 },
  { rap: 500, rub: 250 },
  { rap: 1000, rub: 500 },
  { rap: 2000, rub: 1000 },
];

export default function RubTopUp() {
  const { authUser, openAuth } = useAuth();
  const [pending, setPending] = useState(null);

  const pay = (p) => {
    if (!authUser) return openAuth();
    // Онлайн-приём СБП на согласовании: фиксируем выбранный пакет и ведём в поддержку.
    setPending(p);
    toast.info("Онлайн-оплата подключается. Тариф зафиксирован — напишите в поддержку для оплаты.");
  };

  return (
    <div className="space-y-4" data-testid="topup-rub-step">
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-bold">Пополнение рублями через СБП</span>
        <span className="text-[11px] text-[#7d8194] font-bold">1 RAP = 0,50 ₽</span>
      </div>

      <div className="space-y-2" data-testid="rub-packages">
        {PACKAGES.map((p) => (
          <button
            key={p.rap}
            onClick={() => pay(p)}
            className="w-full rounded-xl bg-[#0f1015] border border-[#2a2b31] hover:border-[#ffb000] px-4 py-3 flex items-center justify-between gap-3 transition-colors"
            data-testid={`rub-package-${p.rap}`}
          >
            <span className="flex items-center gap-1.5 font-black text-[15px]">
              {p.rap} <RobuxIcon size={13} />
            </span>
            <span className="h-8 px-4 rounded-lg bg-[#ffb000] text-black font-black text-[13px] flex items-center" data-testid={`rub-pay-${p.rap}`}>
              Оплатить {p.rub} ₽
            </span>
          </button>
        ))}
      </div>

      {pending && (
        <div className="rounded-xl bg-[#00a2ff]/10 border border-[#00a2ff]/40 px-4 py-3 text-[12px] text-[#b4d9ff] leading-relaxed" data-testid="rub-pending-notice">
          Вы выбрали <b>{pending.rap} RAP за {pending.rub} ₽</b>. Онлайн-приём платежей через СБП сейчас подключается.
          Для оплаты напишите в поддержку{SUPPORT_HANDLE ? <>: <b>{SUPPORT_HANDLE}</b></> : ""} — менеджер примет платёж и зачислит RAP вручную.
          {SUPPORT_URL && (
            <a href={SUPPORT_URL} target="_blank" rel="noopener noreferrer" className="block mt-2 h-9 rounded-lg bg-[#00a2ff] hover:bg-[#1ab0ff] text-white font-bold text-[12px] items-center justify-center flex" data-testid="rub-support-link">
              Написать в поддержку
            </a>
          )}
        </div>
      )}

      <div className="text-[11px] text-[#8e91a3] text-center leading-snug" data-testid="rub-terms-note">
        Нажимая «Оплатить», вы принимаете условия раздела 8 Пользовательского соглашения (/tos): возврат после зачисления не производится, кроме технической вины сервиса (обращение в течение 24 часов).
      </div>
    </div>
  );
}
