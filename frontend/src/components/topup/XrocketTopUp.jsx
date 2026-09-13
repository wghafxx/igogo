import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, formatMoney, parseServerDate } from "../../lib/api";
import { useAuth } from "../../hooks/useAuth";
import { useLang } from "../../lib/i18n";
import { RobuxIcon } from "../Logo";
import { CheckIcon } from "../icons/check";
import { PromoInput } from "../TopUpModal";
import { openXrocketPayment } from "../../lib/payment-navigation";

const COINS = [
  ["GRAM", "GRAM", "✦", "#26a4f2"], ["USDT", "Tether", "₮", "#26a17b"],
  ["USDC", "USD Coin", "$", "#2775ca"], ["BTC", "Bitcoin", "₿", "#f7931a"],
  ["ETH", "Ethereum", "♦", "#697eea"], ["TRX", "TRON", "T", "#ef3340"],
  ["SOL", "Solana", "≋", "#9773ed"], ["BNB", "Binance Coin", "◈", "#e6b800"],
];
const PENDING = ["creating", "awaiting_payment", "processing"];
const stateKey = { creating: "preparing", awaiting_payment: "waiting", processing: "processing", confirmed: "confirmed", expired: "expired", cancelled: "cancelled", payment_error: "failed" };
const errorText = (error, fallback) => typeof error?.response?.data?.detail === "string" ? error.response.data.detail : fallback;

export default function XrocketTopUp({ onChanged }) {
  const { authUser, openAuth, refresh } = useAuth();
  const { t, lang } = useLang();
  const [info, setInfo] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [rub, setRub] = useState("35");
  const [currency, setCurrency] = useState("USDT");
  const [invoice, setInvoice] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef(null);
  const panelRef = useRef(null);
  const alertRef = useRef(null);
  const autoOpenRef = useRef(null);
  const confirmedRef = useRef(null);
  const changedRef = useRef(onChanged);
  changedRef.current = onChanged;
  const accountRef = useRef(authUser?.session_id);
  accountRef.current = authUser?.session_id;

  const loadInfo = useCallback(() => {
    setLoadError(false);
    api.xrocketInfo().then(setInfo).catch(() => setLoadError(true));
  }, []);
  useEffect(loadInfo, [loadInfo]);

  const loadHistory = useCallback(async () => {
    if (!authUser) return;
    const account = authUser.session_id;
    try {
      const rows = await api.xrocketInvoices();
      if (accountRef.current !== account) return;
      setHistory(rows);
      setHistoryError(false);
      return rows;
    } catch {
      if (accountRef.current === account) setHistoryError(true);
    }
  }, [authUser]);

  useEffect(() => {
    setInvoice(null);
    setHistory([]);
    setError("");
    requestRef.current = null;
    autoOpenRef.current = null;
    if (authUser) loadHistory();
    // Account changes reset invoices; refreshed balance must not reset the flow.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authUser?.session_id]);

  const invoiceId = invoice?.id;
  const invoiceStatus = invoice?.status;
  useEffect(() => {
    if (invoiceId) panelRef.current?.scrollIntoView?.({ block: "start" });
  }, [invoiceId]);
  useEffect(() => {
    if (error) alertRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [error]);
  useEffect(() => {
    if (invoice?.id !== autoOpenRef.current || invoice?.status !== "awaiting_payment" || !invoice?.invoice_url) return;
    autoOpenRef.current = null;
    openXrocketPayment(invoice.invoice_url);
  }, [invoice]);
  useEffect(() => {
    if (!invoiceId || !PENDING.includes(invoiceStatus)) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const latest = await api.xrocketInvoice(invoiceId);
        if (!cancelled) setInvoice(latest);
      } catch { /* A transient read error must not change an invoice's status. */ }
    }, 5000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [invoiceId, invoiceStatus, authUser?.session_id]);

  useEffect(() => {
    if (invoice?.status !== "confirmed" || confirmedRef.current === invoice.id) return;
    confirmedRef.current = invoice.id;
    toast.success(t("xrocket.confirmed"));
    refresh();
    loadHistory();
    changedRef.current?.();
    window.dispatchEvent(new Event("bloxgrade:payment-confirmed"));
  }, [invoice, refresh, loadHistory, t]);

  const num = Number(rub);
  const valid = Number.isFinite(num) && num >= (info?.min_rub ?? 35) && num <= (info?.max_rub ?? 1000000);
  const credit = Math.round(num / (info?.rap_rub_rate ?? 0.5) * (1 + (authUser?.promo_bonus || 0)) * 100) / 100;

  const pay = async (retryInvoice = null) => {
    if (!authUser) return openAuth();
    if ((!retryInvoice && !valid) || !info?.enabled || busy) return;
    const account = authUser.session_id;
    const amount = retryInvoice ? retryInvoice.amount_rub : num;
    const coin = retryInvoice ? retryInvoice.currency : currency;
    const identity = `${account}:${amount}:${coin}`;
    if (requestRef.current?.identity !== identity || retryInvoice) requestRef.current = {
      identity, id: retryInvoice ? retryInvoice.id.replace(/^xrocket:/, "") : crypto.randomUUID(),
    };
    setBusy(true);
    setError("");
    try {
      const result = await api.createXrocketInvoice({ request_id: requestRef.current.id, amount_rub: amount, currency: coin });
      if (accountRef.current !== account) return;
      autoOpenRef.current = result.id;
      setInvoice(result);
      loadHistory();
      changedRef.current?.();
    } catch (e) {
      if (accountRef.current === account) setError(errorText(e, t("xrocket.create_error")));
    } finally {
      setBusy(false);
    }
  };

  const check = async () => {
    if (busy || !invoice) return;
    const account = authUser?.session_id;
    setBusy(true);
    setError("");
    try {
      const result = await api.refreshXrocketInvoice(invoice.id);
      if (accountRef.current !== account) return;
      setInvoice(result);
      if (result.status === "awaiting_payment") toast.info(t("xrocket.not_paid"));
    } catch (e) {
      if (accountRef.current === account) setError(errorText(e, t("xrocket.check_error")));
    } finally {
      setBusy(false);
    }
  };

  return <div ref={panelRef} className="space-y-4" data-testid="xrocket-topup">
    <div className="flex items-start gap-3">
      <div className="min-w-0 flex-1"><h3 className="font-bold text-[15px]">{t("xrocket.title")}</h3><p className="text-[11px] leading-relaxed text-[#8e91a3] mt-1">{t("xrocket.subtitle")}</p></div>
      <span className="shrink-0 rounded-md bg-[#2ecc71]/10 px-2 py-1 text-[10px] font-bold text-[#61d899]">0%</span>
    </div>
    {loadError && <div role="alert" className="text-[12px] text-[#ff8a8a]">{t("xrocket.load_error")} <button onClick={loadInfo} className="underline">{t("xrocket.retry")}</button></div>}
    {info && !info.enabled && <p role="status" className="rounded-lg bg-[#ffb000]/10 p-3 text-[12px] text-[#ffcf66]">{t("xrocket.unavailable")}</p>}

    {invoice ? <div className="rounded-xl border border-[#00a2ff]/30 bg-[#0f1015] p-4 space-y-4" data-testid="xrocket-invoice">
      <div className="flex items-center gap-3"><img src="/payments/xrocket.jpg" alt="" className="w-10 h-10 rounded-xl" /><div><span className="text-[11px] text-[#8e91a3]">{t("xrocket.invoice")}</span><div className="text-xl font-black">{formatMoney(invoice.amount_rub)} ₽ <span className="text-[12px] text-[#8e91a3]">· {invoice.currency}</span></div></div></div>
      <div className={`text-[13px] font-bold ${invoice.status === "confirmed" ? "text-[#61d899]" : "text-[#ffcf66]"}`} role="status" data-testid="xrocket-status">{t(`xrocket.${stateKey[invoice.status] || "waiting"}`)}</div>
      {invoice.status === "payment_error" && <>
        <p className="text-[12px] leading-relaxed text-[#b4b7c7]">{invoice.error_message || t("xrocket.failed_help")}</p>
        <button onClick={() => pay(invoice)} disabled={busy || !info?.enabled} className="w-full h-12 rounded-xl bg-[#ffb000] text-black font-bold text-[13px] disabled:opacity-40" data-testid="xrocket-retry-invoice">{busy ? t("xrocket.creating") : t("xrocket.retry_invoice")}</button>
      </>}
      <div className="flex items-center justify-between text-[12px]"><span className="text-[#8e91a3]">{t("xrocket.credit")}</span><b className="inline-flex items-center gap-1.5 text-[#ffb000]">{formatMoney(invoice.credited ?? invoice.quoted_rap)} <RobuxIcon size={13} /></b></div>
      {invoice.price_amount && <p className="text-[12px] text-[#b4b7c7]">{t("xrocket.crypto_amount")} <b>{invoice.price_amount} {invoice.price_currency}</b></p>}
      {PENDING.includes(invoice.status) && <>
        {invoice.invoice_url && invoice.expires_at && <p className="text-[11px] text-[#8e91a3]">{t("xrocket.until")} {parseServerDate(invoice.expires_at).toLocaleString(lang === "en" ? "en-US" : "ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</p>}
        {invoice.status === "awaiting_payment" && invoice.invoice_url && <>
          <p className="text-[12px] leading-relaxed text-[#b4b7c7]">{t("xrocket.pay_help")}</p>
          <a href={invoice.invoice_url} className="h-12 flex items-center justify-center gap-2 rounded-xl bg-[#00a2ff] hover:bg-[#20afff] font-bold text-[14px] transition-colors" data-testid="xrocket-open">{t("xrocket.open")} ↗</a>
        </>}
        {!invoice.invoice_url && invoice.status !== "processing" && <button onClick={() => pay(invoice)} disabled={busy} className="w-full h-11 rounded-xl bg-[#ffb000] text-black text-[13px] font-bold disabled:opacity-40" data-testid="xrocket-retry-invoice">{busy ? t("xrocket.creating") : t("xrocket.retry_invoice")}</button>}
        <button onClick={check} disabled={busy} className="w-full h-10 rounded-lg bg-[#252630] text-[12px] font-bold hover:bg-[#30323d] disabled:opacity-40" data-testid="xrocket-check">{busy ? t("xrocket.checking") : t("xrocket.check")}</button>
        <p className="text-[11px] text-[#8e91a3] leading-relaxed">{t("xrocket.auto")}</p>
      </>}
      <button onClick={() => { setInvoice(null); setError(""); requestRef.current = null; autoOpenRef.current = null; loadHistory(); }} disabled={busy} className="text-[12px] text-[#00a2ff] hover:text-white disabled:opacity-40" data-testid="xrocket-new">{t("xrocket.new")}</button>
    </div> : <>
      <div className="flex flex-wrap items-center justify-between gap-2"><label htmlFor="xrocket-rub" className="text-[12px] font-bold">{t("xrocket.amount")}</label><div className="flex gap-1">{[35, 100, 250, 500, 1000].map((amount) => <button type="button" key={amount} onClick={() => setRub(String(amount))} disabled={busy} className={`px-2 h-6 rounded-md text-[10px] font-bold ${num === amount ? "bg-[#ffb000] text-black" : "bg-[#2a2b31] text-[#8e91a3] hover:text-white"}`}>{amount}</button>)}</div></div>
      <div className={`flex items-center gap-3 rounded-xl border px-4 py-3 bg-[#0f1015] ${num > 0 && !valid ? "border-[#ff5c5c]" : "border-[#ffb000]/50 focus-within:border-[#ffb000]"}`}>
        <input id="xrocket-rub" value={rub} disabled={busy} onChange={(e) => { const v = e.target.value.replace(",", "."); if (/^\d{0,7}(\.\d{0,2})?$/.test(v)) setRub(v); }} inputMode="decimal" className="w-full min-w-0 bg-transparent outline-none text-[26px] font-black" data-testid="xrocket-amount" />
        <span className="text-[#ffb000] text-xl font-black">₽</span>
      </div>
      <p className="!mt-1.5 text-[11px] text-[#8e91a3]">{t("xrocket.minimum")}</p>
      <fieldset disabled={busy}><legend className="mb-2 text-[12px] font-bold">{t("xrocket.currency")}</legend><div className="grid grid-cols-2 gap-1.5">
        {COINS.filter(([code]) => !info || info.currencies.includes(code)).map(([code, title, symbol, color]) => <button type="button" key={code} onClick={() => setCurrency(code)} aria-pressed={currency === code} aria-label={title} className={`relative flex items-center gap-2.5 p-3 rounded-xl border text-left transition-colors ${currency === code ? "border-[#00a2ff]/60 bg-[#00a2ff]/10" : "border-transparent bg-[#262830] hover:bg-[#30333e]"}`} data-testid={`xrocket-currency-${code}`}>
          <span aria-hidden="true" className="w-7 h-7 shrink-0 rounded-full flex items-center justify-center text-[19px] font-bold text-white" style={{ backgroundColor: color }}>{symbol}</span><span className="min-w-0"><b className="block text-[12px] truncate">{title}</b><span className="text-[10px] text-[#8e91a3]">{code}</span></span>{currency === code && <CheckIcon size={12} className="ml-auto shrink-0 text-[#00a2ff]" />}
        </button>)}
      </div></fieldset>
      <PromoInput compact />
      <div className="rounded-xl bg-[#0f1015] p-3 space-y-2 text-[12px]"><div className="flex justify-between gap-3"><span className="text-[#8e91a3]">{t("xrocket.credit")}</span><b className="text-[#ffb000] flex items-center gap-1.5" data-testid="xrocket-credit">{formatMoney(valid ? credit : 0)} <RobuxIcon size={12} /></b></div>{authUser?.promo_bonus > 0 && <p className="text-[10px] text-[#61d899]">{t("xrocket.promo")} {authUser.promo_code}</p>}<div className="text-[11px] text-[#61d899]">{t("xrocket.zero_fee")}</div></div>
      <p className="text-[11px] leading-relaxed text-[#8e91a3]" data-testid="xrocket-fee">{t("xrocket.provider_fee")}</p>
      <button onClick={() => pay()} disabled={busy || (authUser && (!valid || !info?.enabled))} className="w-full h-12 rounded-xl bg-[#ffb000] hover:bg-[#ffc233] text-black text-[14px] font-black disabled:opacity-40 transition-colors" data-testid="xrocket-pay">{busy ? t("xrocket.creating") : !authUser ? t("xrocket.login") : t("xrocket.pay")}</button>
    </>}
    {error && <p ref={alertRef} role="alert" className="rounded-lg bg-[#ff5c5c]/10 p-3 text-[12px] text-[#ff8a8a] leading-relaxed">{error}</p>}
    {historyError && <p role="alert" className="text-[12px] text-[#ff8a8a]">{t("xrocket.history_error")} <button onClick={loadHistory} className="underline">{t("xrocket.retry")}</button></p>}
    {!invoice && history.some((row) => row.status === "awaiting_payment" && row.invoice_url) && <div className="rounded-xl border border-[#00a2ff]/30 p-3 space-y-2"><h4 className="text-[12px] font-bold">{t("xrocket.unpaid")}</h4>{history.filter((row) => row.status === "awaiting_payment" && row.invoice_url).map((row) => <a key={row.id} href={row.invoice_url} className="flex justify-between gap-2 text-[12px] text-[#00a2ff] py-2"><b>{formatMoney(row.amount_rub)} ₽ · {row.currency}</b><span>{t("xrocket.continue")} ↗</span></a>)}</div>}
    {!invoice && history.length > 0 && <details className="space-y-1.5"><summary className="text-[12px] font-bold cursor-pointer text-[#8e91a3]">{t("xrocket.history")}</summary>{history.slice(0, 10).map((row) => <button key={row.id} disabled={busy} onClick={() => { setInvoice(row); setError(""); }} className="w-full flex items-center justify-between gap-3 p-2.5 bg-[#15161c] hover:bg-[#252630] rounded-lg text-[11px] text-left" data-testid="xrocket-history-item"><b>{formatMoney(row.amount_rub)} ₽ · {row.currency}</b><span className={row.status === "confirmed" ? "text-[#61d899]" : "text-[#8e91a3]"}>{t(`xrocket.${stateKey[row.status] || "waiting"}`)}</span></button>)}</details>}
    <a href="/tos" target="_blank" rel="noopener noreferrer" className="block text-[10px] text-[#7d8194] hover:text-[#8e91a3] text-center">{t("xrocket.terms")}</a>
  </div>;
}
