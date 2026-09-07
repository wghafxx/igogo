import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Logo, RobuxIcon } from "../components/Logo";
import { LockIcon } from "../components/icons/lock";
import { RefreshCWIcon } from "../components/icons/refresh-cw";
import { CheckIcon } from "../components/icons/check";
import { XIcon } from "../components/icons/x";
import { ExternalLinkIcon } from "../components/icons/external-link";
import { adminApi, getAdminToken, setAdminToken, formatMoney, DEPOSIT_FEE } from "../lib/api";
import BankTab from "../components/admin/BankTab";
import PlayersTab from "../components/admin/PlayersTab";
import { DepositAllocationPreview } from "../components/admin/DepositAllocationPreview";
import { DepositReceipt } from "../components/DepositReceipt";

const waitingFor = (iso) => {
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins} мин`;
  const h = Math.floor(mins / 60);
  return h < 48 ? `${h} ч ${mins % 60} мин` : `${Math.floor(h / 24)} дн`;
};
const fmtDate = (d) => new Date(d).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

const WORDS = 10;
const splitWords = (text) => text.trim().split(/[\s,;]+/).filter(Boolean);

const AdminLogin = ({ onDone }) => {
  const [words, setWords] = useState(Array(WORDS).fill(""));
  const [busy, setBusy] = useState(false);
  const refs = useRef([]);
  const filled = words.every((w) => w.trim().length > 0);

  const setWord = (i, v) => setWords((ws) => ws.map((w, j) => (j === i ? v.replace(/\s/g, "") : w)));
  const onPaste = (i, e) => {
    const parts = splitWords(e.clipboardData.getData("text"));
    if (parts.length < 2) return;
    e.preventDefault();
    setWords((ws) => ws.map((w, j) => (j >= i && parts[j - i] !== undefined ? parts[j - i] : w)));
    refs.current[Math.min(WORDS - 1, i + parts.length - 1)]?.focus();
  };
  const onKey = (i, e) => {
    if (e.key === "Enter") return filled ? submit() : refs.current[i + 1]?.focus();
    if (e.key === " " && words[i]) {
      e.preventDefault();
      refs.current[i + 1]?.focus();
    }
    if (e.key === "Backspace" && !words[i] && i > 0) refs.current[i - 1]?.focus();
  };

  const submit = async () => {
    if (!filled || busy) return;
    setBusy(true);
    try {
      const { token } = await adminApi.login(words.map((w) => w.trim()));
      setAdminToken(token);
      onDone();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Неверная сид-фраза");
      setWords(Array(WORDS).fill(""));
      refs.current[0]?.focus();
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="min-h-screen bg-[#0d0e12] text-white flex items-center justify-center px-4" data-testid="admin-login-page">
      <div className="blox-panel w-full max-w-[520px] p-7 space-y-5">
        <div className="flex items-center gap-2">
          <Logo size={30} />
          <span className="font-black uppercase tracking-wide text-[18px]">BLOXGRADE</span>
          <span className="ml-auto text-[10px] uppercase tracking-widest text-[#5f6377]">admin</span>
        </div>
        <div>
          <div className="text-[20px] font-black">Админ-панель</div>
          <div className="text-[12px] text-[#8e91a3] mt-1">Введите все {WORDS} слов сид-фразы по порядку. Можно вставить всю фразу целиком в любое поле.</div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2" data-testid="admin-seed-grid">
          {words.map((w, i) => (
            <div key={i} className="flex items-center gap-1.5 h-11 px-2.5 rounded-lg bg-[#0f1015] focus-within:ring-1 focus-within:ring-[#00a2ff]">
              <span className="text-[10px] text-[#5f6377] w-4 text-right">{i + 1}</span>
              <input
                ref={(el) => (refs.current[i] = el)}
                type="password"
                value={w}
                onChange={(e) => setWord(i, e.target.value)}
                onPaste={(e) => onPaste(i, e)}
                onKeyDown={(e) => onKey(i, e)}
                autoComplete="off"
                spellCheck={false}
                autoFocus={i === 0}
                className="flex-1 min-w-0 bg-transparent outline-none text-[13px] font-mono"
                data-testid={`admin-seed-word-${i + 1}`}
              />
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={submit} disabled={busy || !filled} className="blox-btn-primary h-11 flex-1 text-[14px] disabled:opacity-40" data-testid="admin-login-button">
            <LockIcon size={15} className="inline mr-1.5 -mt-0.5" /> Войти
          </button>
          <button onClick={() => { setWords(Array(WORDS).fill("")); refs.current[0]?.focus(); }} className="blox-chip h-11 px-4 text-[12px] font-bold text-[#9a9db0] hover:text-white" data-testid="admin-seed-clear">
            Очистить
          </button>
        </div>
        <div className="text-[11px] text-[#5f6377]">Введено {words.filter((x) => x.trim()).length} из {WORDS}. После 5 неверных попыток вход блокируется на 15 минут.</div>
      </div>
    </div>
  );
};

const DepositRow = ({ d, onConfirm, onReject, busy }) => {
  const [amount, setAmount] = useState(d.status === "processing" ? String(d.rap) : d.expected_rap ? String(d.expected_rap) : "");
  const [note, setNote] = useState("");
  const [allocationReady, setAllocationReady] = useState(false);
  const rap = Number(amount) || 0;
  const net = rap * (1 - DEPOSIT_FEE);
  const credited = Math.round(net * (1 + Math.min(0.5, Math.max(0, d.promo_bonus || 0))) * 100) / 100;
  return (
    <div className="blox-panel p-4 grid grid-cols-1 lg:grid-cols-[110px_1fr_320px] gap-4 items-start" data-testid="admin-deposit-row">
      <div>
        <div className="text-[10px] uppercase text-[#7d8194]">Ждёт</div>
        <div className="text-[18px] font-black text-[#ffb000]" data-testid="admin-deposit-wait">{waitingFor(d.created_at)}</div>
        <div className="text-[11px] text-[#5f6377]">{fmtDate(d.created_at)}</div>
      </div>
      <div className="min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="font-bold" data-testid="admin-deposit-nick">{d.nickname}</span>
          <span className="text-[11px] text-[#8e91a3] bg-[#1c1d25] rounded px-1.5 py-0.5">Discord {d.discord_id}</span>
          {d.roblox_nick ? (
            <span className="text-[11px] text-[#b4d9ff] bg-[#00a2ff]/15 rounded px-1.5 py-0.5 inline-flex items-center gap-1">
              Roblox: {d.roblox_nick}
              {d.roblox_link && (
                <a href={d.roblox_link} target="_blank" rel="noopener noreferrer" className="hover:text-white">
                  <ExternalLinkIcon size={11} />
                </a>
              )}
            </span>
          ) : (
            <span className="text-[11px] text-[#ff9b9b]">Roblox-ник не указан</span>
          )}
          {d.promo_bonus > 0 && <span className="text-[11px] text-[#ffb000] bg-[#ffb000]/15 rounded px-1.5 py-0.5">промо +{Math.round(d.promo_bonus * 100)}%</span>}
          {d.expected_rap > 0 && <span className="text-[11px] text-[#2ecc71] bg-[#2ecc71]/15 rounded px-1.5 py-0.5" data-testid="admin-deposit-expected">заявлено {formatMoney(d.expected_rap)} RAP</span>}
          {d.receiver_nick && <span className="text-[11px] text-[#b4b7c7] bg-[#1c1d25] rounded px-1.5 py-0.5" data-testid="admin-deposit-receiver">→ {d.receiver_nick}</span>}
        </div>
        <div className="text-[13px] text-[#d5d7e2] bg-[#0f1015] rounded-lg px-3 py-2 break-words" data-testid="admin-deposit-description">{d.description}</div>
      </div>
      <div className="space-y-2">
        <div className="flex items-center gap-2 h-10 px-3 rounded-lg bg-[#0f1015] focus-within:ring-1 focus-within:ring-[#2ecc71]">
          <RobuxIcon size={13} />
          <input
            value={amount}
            disabled={busy || d.status === "processing"}
            inputMode="decimal"
            onChange={(e) => { const next = e.target.value.replace(",", "."); if (/^\d{0,7}(\.\d{0,2})?$/.test(next)) setAmount(next); }}
            placeholder="Полный RAP скина (как в игре)"
            className="flex-1 min-w-0 bg-transparent outline-none text-[13px] font-bold"
            data-testid="admin-amount-input"
          />
        </div>
        {rap > 0 && rap < 20 && (
          <div className="text-[11px] text-[#ff8a8a] px-1" data-testid="admin-credit-preview">Меньше 20 RAP — зачислить нельзя, отклоните заявку</div>
        )}
        {rap >= 20 && (
          <div className="text-[11px] text-[#8e91a3] px-1" data-testid="admin-credit-preview">
            {formatMoney(rap)} − 20% = {formatMoney(net)}
            {d.promo_bonus > 0 && <> → +{Math.round(d.promo_bonus * 100)}% промо = <b className="text-[#2ecc71]">{formatMoney(credited)}</b></>}
          </div>
        )}
        <DepositAllocationPreview depositId={d.id} rap={rap} onReady={setAllocationReady} />
        <input value={note} disabled={busy || d.status === "processing"} onChange={(e) => setNote(e.target.value.slice(0, 200))} placeholder="Заметка (необязательно)" className="w-full h-9 px-3 rounded-lg bg-[#0f1015] outline-none text-[12px]" data-testid="admin-note-input" />
        <div className="flex items-center gap-2">
          <button
            onClick={() => onConfirm(d.id, Number(amount), note)}
            disabled={busy || rap < 20 || rap > 1000000 || !allocationReady}
            className="flex-1 min-h-10 py-2 px-2 rounded-lg bg-[#2ecc71] hover:bg-[#3ddb80] text-black font-bold text-[12px] flex items-center justify-center gap-1.5 disabled:opacity-40 transition-colors"
            data-testid="admin-confirm-button"
          >
            <CheckIcon size={14} /> {d.status === "processing" ? "Завершить выдачу" : "Подтвердить и выдать скины"}
          </button>
          <button onClick={() => onReject(d.id)} disabled={busy || d.status === "processing"} className="h-10 px-3 rounded-lg bg-[#ff5c5c]/15 text-[#ff8a8a] hover:bg-[#ff5c5c] hover:text-white font-bold text-[12px] flex items-center gap-1 transition-colors" data-testid="admin-reject-button">
            <XIcon size={13} /> Отклонить
          </button>
        </div>
      </div>
    </div>
  );
};

export default function AdminPage() {
  const [authed, setAuthed] = useState(Boolean(getAdminToken()));
  const [tab, setTab] = useState("pending");
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const currentTab = useRef(tab);
  currentTab.current = tab;

  const load = useCallback(async () => {
    try {
      if (tab === "bank" || tab === "players") return;
      const result = tab === "withdrawals" ? await adminApi.withdrawals("pending") : await adminApi.deposits(tab);
      if (currentTab.current === tab) setRows(result);
    } catch (e) {
      if (e?.response?.status === 403) {
        setAdminToken(null);
        setAuthed(false);
      } else toast.error("Не удалось загрузить заявки");
    }
  }, [tab]);

  useEffect(() => {
    if (!authed) return;
    setRows([]);
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [authed, load]);

  useEffect(() => {
    if (!authed) return;
    const check = () => adminApi.session().catch((e) => {
      if (e?.response?.status === 403) { setAdminToken(null); setAuthed(false); }
    });
    check();
    const timer = setInterval(check, 30000);
    return () => clearInterval(timer);
  }, [authed]);

  if (!authed) return <AdminLogin onDone={() => setAuthed(true)} />;

  const run = async (fn, msg) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
      toast.success(msg);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ошибка");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0d0e12] text-white" data-testid="admin-page">
      <header className="h-[54px] flex items-center justify-between px-4 border-b border-[#15161b] bg-[#0f1015] sticky top-0 z-40">
        <div className="flex items-center gap-2">
          <Logo size={30} />
          <span className="hidden sm:inline font-black uppercase tracking-wide text-[20px]">BLOXGRADE</span>
          <span className="text-[10px] uppercase tracking-widest text-[#ffb000] bg-[#ffb000]/15 rounded px-2 py-0.5 ml-2">admin</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { load(); setRefreshKey((v) => v + 1); }} className="blox-chip w-9 h-9 flex items-center justify-center text-[#9a9db0] hover:text-white" title="Обновить" data-testid="admin-refresh-button">
            <RefreshCWIcon size={15} />
          </button>
          <button onClick={async () => { try { await adminApi.logout(); } catch (_) {} setAdminToken(null); setAuthed(false); }} className="blox-chip h-9 px-3 text-[12px] font-bold text-[#9a9db0] hover:text-white" data-testid="admin-logout-button">
            Выйти
          </button>
        </div>
      </header>

      <main className="max-w-[1100px] mx-auto px-4 py-6 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-1 rounded-lg bg-[#0f1015] p-1">
            {[
              ["pending", "Ожидают пополнения"],
              ["confirmed", "Зачислено"],
              ["rejected", "Отклонено"],
              ["cancelled", "Отменённые"],
              ["withdrawals", "Выводы скинов"],
              ["bank", "Банк"],
              ["players", "Игроки"],
            ].map(([k, label]) => (
              <button key={k} onClick={() => setTab(k)} className={`h-8 px-3 rounded-md text-[12px] font-bold transition-colors ${tab === k ? "bg-[#ffb000] text-black" : "text-[#8e91a3] hover:text-white"}`} data-testid={`admin-tab-${k}`}>
                {label}
              </button>
            ))}
          </div>
          {tab === "pending" && <div className="text-[12px] text-[#8e91a3]">Сверху — кто ждёт дольше всех. Проверьте, что скин пришёл на аккаунт, введите сумму и подтвердите.</div>}
        </div>

        {tab === "pending" && (
          <div className="rounded-lg bg-[#ffb000]/10 border border-[#ffb000]/40 px-3 py-2.5 text-[12px] text-[#ffd166] leading-snug" data-testid="admin-hint">
            Введите полный RAP полученных скинов. После комиссии 20% и промокода система подберёт до 5 разных предметов; остаток — на баланс. Сумма скинов и остатка строго равна рассчитанному зачислению. До подтверждения ничего не выдаётся.
          </div>
        )}

        {tab === "bank" && <BankTab refreshKey={refreshKey} />}
        {tab === "players" && <PlayersTab refreshKey={refreshKey} />}

        {tab !== "bank" && tab !== "players" && (
        <div className="space-y-3" data-testid="admin-list">
          {rows.length === 0 && <div className="blox-panel h-[160px] flex items-center justify-center text-[13px] text-[#5f6377]" data-testid="admin-empty">Пусто</div>}

          {tab === "pending" &&
            rows.map((d) => (
              <DepositRow
                key={d.id}
                d={d}
                busy={busy}
                onConfirm={(id, rap, note) => run(() => adminApi.confirm(id, rap, note), "Депозит обработан: скины в инвентаре, остаток на балансе")}
                onReject={(id) => run(() => adminApi.reject(id), "Заявка отклонена")}
              />
            ))}

          {(tab === "confirmed" || tab === "rejected" || tab === "cancelled") &&
            rows.map((d) => (
              <div key={d.id} className="blox-panel px-4 py-3 flex flex-wrap items-center gap-3 text-[12px]" data-testid="admin-history-row">
                <span className="font-bold w-40 truncate">{d.nickname}</span>
                <span className="text-[#8e91a3] w-36">Discord {d.discord_id}</span>
                <span className="flex-1 min-w-[200px] text-[#b4b7c7] truncate">{d.description}</span>
                {d.expected_rap > 0 && <span className="text-[11px] text-[#8e91a3]">заявлено {formatMoney(d.expected_rap)} RAP{d.receiver_nick ? ` → ${d.receiver_nick}` : ""}</span>}
                {tab === "confirmed" && <DepositReceipt deposit={d} compact testId={`admin-deposit-receipt-${d.id}`} />}
                <span className="text-[#5f6377] w-24 text-right">{fmtDate(d.resolved_at || d.created_at)}</span>
              </div>
            ))}

          {tab === "withdrawals" &&
            rows.map((w) => (
              <div key={w.id} className="blox-panel px-4 py-3 flex flex-wrap items-center gap-3 text-[12px]" data-testid="admin-withdrawal-row">
                <span className="font-bold text-[#ffb000] w-20">{waitingFor(w.created_at)}</span>
                {w.item?.image && <img src={w.item.image} alt="" className="w-10 h-10 object-contain" />}
                <span className="flex-1 min-w-[160px]"><b>{w.item?.name}</b> <span className="text-[#7d8194]">{w.item?.type}</span> · {formatMoney(w.item?.price)} RAP</span>
                <span className="w-44 truncate">{w.user?.nickname} {w.user?.roblox_nick ? `· Roblox: ${w.user.roblox_nick}` : ""}</span>
                {w.user?.roblox_link && (
                  <a href={w.user.roblox_link} target="_blank" rel="noopener noreferrer" className="text-[#00a2ff] hover:text-white"><ExternalLinkIcon size={13} /></a>
                )}
                <button onClick={() => run(() => adminApi.withdrawalDone(w.id), "Вывод отмечен выполненным")} disabled={busy} className="h-8 px-3 rounded-md bg-[#2ecc71] text-black font-bold text-[12px] disabled:opacity-40" data-testid="admin-withdrawal-done-button">
                  Скин отправлен
                </button>
              </div>
            ))}
        </div>
        )}
      </main>
    </div>
  );
}
