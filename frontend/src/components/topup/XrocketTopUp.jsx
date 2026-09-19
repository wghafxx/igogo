import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, formatMoney, parseServerDate } from "../../lib/api";
import { useAuth } from "../../hooks/useAuth";
import { useLang } from "../../lib/i18n";
import { RobuxIcon } from "../Logo";
import { PromoInput } from "../TopUpModal";
import { openXrocketPayment } from "../../lib/payment-navigation";

const COINS = [
  ["GRAM", "GRAM"], ["USDT", "Tether"], ["USDC", "USD Coin"], ["BTC", "Bitcoin"],
  ["ETH", "Ethereum"], ["TRX", "TRON"], ["SOL", "Solana"], ["BNB", "Binance Coin"],
];
const CB_COINS = [
  ["USDT", "Tether"], ["TON", "Toncoin"], ["BTC", "Bitcoin"], ["ETH", "Ethereum"],
  ["LTC", "Litecoin"], ["BNB", "Binance Coin"], ["TRX", "TRON"], ["USDC", "USD Coin"],
];
export const coinIcon = (code) => `/payments/coins/${code.toLowerCase()}.png`;
export const PROVIDERS = {
  xrocket: {
    key: "xrocket", i18n: "xrocket", coins: COINS, defaultCoin: "USDT",
    info: api.xrocketInfo, invoices: api.xrocketInvoices, create: api.createXrocketInvoice, get: api.xrocketInvoice, refresh: api.refreshXrocketInvoice,
    Logo: ({ className }) => <img src="/payments/xrocket.jpg" alt="" className={className} />,
  },
  cryptobot: {
    key: "cryptobot", i18n: "cryptobot", coins: CB_COINS, defaultCoin: "USDT",
    info: api.cryptobotInfo, invoices: api.cryptobotInvoices, create: api.createCryptobotInvoice, get: api.cryptobotInvoice, refresh: api.refreshCryptobotInvoice,
    Logo: ({ className }) => <img src="/payments/cryptobot.png" alt="" className={className} />,
  },
};
const PENDING = ["creating", "awaiting_payment", "processing"];
const stateKey = { creating: "preparing", awaiting_payment: "waiting", processing: "processing", confirmed: "confirmed", expired: "expired", cancelled: "cancelled", payment_error: "failed" };
const errorText = (error, fallback) => typeof error?.response?.data?.detail === "string" ? error.response.data.detail : fallback;

export default function XrocketTopUp({ onChanged, provider = "xrocket" }) {
  const P = PROVIDERS[provider];
  const tid = P.key;
  const { authUser, openAuth, refresh } = useAuth();
  const { t, lang } = useLang();
  const tp = (key) => t(`${P.i18n}.${key}`);
  const [info, setInfo] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [rub, setRub] = useState("35");
  const [currency, setCurrency] = useState(P.defaultCoin);
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
    P.info().then(setInfo).catch(() => setLoadError(true));
  }, [P]);
  useEffect(loadInfo, [loadInfo]);

  const loadHistory = useCallback(async () => {
    if (!authUser) return;
    const account = authUser.session_id;
    try {
      const rows = await P.invoices();
      if (accountRef.current !== account) return;
      setHistory(rows);
      setHistoryError(false);
      return rows;
    } catch {
      if (accountRef.current === account) setHistoryError(true);
    }
  }, [authUser, P]);

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
        const latest = await P.get(invoiceId);
        if (!cancelled) setInvoice(latest);
      } catch { /* A transient read error must not change an invoice's status. */ }
    }, 5000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [invoiceId, invoiceStatus, authUser?.session_id, P]);

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
      identity, id: retryInvoice ? retryInvoice.id.replace(/^(xrocket|cryptobot):/, "") : crypto.randomUUID(),
    };
    setBusy(true);
    setError("");
    try {
      const payload = { request_id: requestRef.current.id, amount_rub: amount };
      if (P.coins) payload.currency = coin;
      const result = await P.create(payload);
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
      const result = await P.refresh(invoice.id);
      if (accountRef.current !== account) return;
      setInvoice(result);
      if (result.status === "awaiting_payment") toast.info(t("xrocket.not_paid"));
    } catch (e) {
      if (accountRef.current === account) setError(errorText(e, t("xrocket.check_error")));
    } finally {
      setBusy(false);
    }
  };

  const tail = <>
    {error && <p ref={alertRef} role="alert" className="rounded-[10px] m-note-err p-3 text-[12px] leading-relaxed">{error}</p>}
    {historyError && <p role="alert" className="text-[12px] text-[#ff8a8a]">{t("xrocket.history_error")} <button onClick={loadHistory} className="underline">{t("xrocket.retry")}</button></p>}
    {!invoice && history.some((row) => row.status === "awaiting_payment" && row.invoice_url) && <div className="m-box-dark p-3 space-y-2"><h4 className="text-[12px] font-bold">{t("xrocket.unpaid")}</h4>{history.filter((row) => row.status === "awaiting_payment" && row.invoice_url).map((row) => <a key={row.id} href={row.invoice_url} className="flex justify-between gap-2 text-[12px] text-[#00a2ff] py-2"><b>{formatMoney(row.amount_rub)} ₽ · {row.currency}</b><span>{t("xrocket.continue")} ↗</span></a>)}</div>}
    {!invoice && history.length > 0 && <details className="space-y-1.5"><summary className="text-[12px] font-bold cursor-pointer text-[#8e91a3]">{t("xrocket.history")}</summary>{history.slice(0, 10).map((row) => <button key={row.id} disabled={busy} onClick={() => { setInvoice(row); setError(""); }} className="w-full flex items-center justify-between gap-3 p-2.5 bg-white/5 hover:bg-white/10 rounded-lg text-[11px] text-left" data-testid={`${tid}-history-item`}><b>{formatMoney(row.amount_rub)} ₽ · {row.currency}</b><span className={row.status === "confirmed" ? "text-[#61d899]" : "text-[#8e91a3]"}>{t(`xrocket.${stateKey[row.status] || "waiting"}`)}</span></button>)}</details>}
    <a href={`/${lang}/tos`} target="_blank" rel="noopener noreferrer" className="block m-hint hover:text-white/60">{t("xrocket.terms")}</a>
  </>;
  return <div ref={panelRef} className="mt-3 space-y-3" data-testid={`${tid}-topup`}>
    <div className="flex items-start gap-3">
      <div className="min-w-0 flex-1"><h3 className="font-semibold text-[15px]">{tp("title")}</h3><p className="text-[11px] leading-relaxed text-white/50 mt-1">{tp("subtitle")}</p></div>
      <span className="shrink-0 rounded-md bg-[#2ecc71]/10 px-2 py-1 text-[10px] font-bold text-[#61d899]">0%</span>
    </div>
    {loadError && <div role="alert" className="text-[12px] text-[#ff8a8a]">{t("xrocket.load_error")} <button onClick={loadInfo} className="underline">{t("xrocket.retry")}</button></div>}
    {info && !info.enabled && <p role="status" className="rounded-[10px] m-note-warn p-3 text-[12px]">{t("xrocket.unavailable")}</p>}

    {invoice ? <><div className="m-box p-4 space-y-4" data-testid={`${tid}-invoice`}>
      <div className="flex items-center gap-3"><P.Logo className="w-12 h-12 rounded-xl" /><div><span className="text-[11px] text-[#8e91a3]">{tp("invoice")}</span><div className="text-xl font-black">{formatMoney(invoice.amount_rub)} ₽ <span className="text-[12px] text-[#8e91a3]">· {invoice.currency}</span></div></div></div>
      <div className={`text-[13px] font-bold ${invoice.status === "confirmed" ? "text-[#61d899]" : "text-[#ffcf66]"}`} role="status" data-testid={`${tid}-status`}>{t(`xrocket.${stateKey[invoice.status] || "waiting"}`)}</div>
      {invoice.status === "payment_error" && <>
        <p className="text-[12px] leading-relaxed text-[#b4b7c7]">{invoice.error_message || t("xrocket.failed_help")}</p>
        <button onClick={() => pay(invoice)} disabled={busy || !info?.enabled} className="m-cta !h-12 text-[14px]" data-testid={`${tid}-retry-invoice`}>{busy ? t("xrocket.creating") : t("xrocket.retry_invoice")}</button>
      </>}
      <div className="flex items-center justify-between text-[12px]"><span className="text-[#8e91a3]">{t("xrocket.credit")}</span><b className="inline-flex items-center gap-1.5 text-[#fdd911]">{formatMoney(invoice.credited ?? invoice.quoted_rap)} <RobuxIcon size={13} /></b></div>
      {invoice.price_amount && P.key === "xrocket" && <p className="text-[12px] text-[#b4b7c7]">{t("xrocket.crypto_amount")} <b>{invoice.price_amount} {invoice.price_currency}</b></p>}
      {PENDING.includes(invoice.status) && <>
        {invoice.invoice_url && invoice.expires_at && <p className="text-[11px] text-[#8e91a3]">{t("xrocket.until")} {parseServerDate(invoice.expires_at).toLocaleString(lang === "en" ? "en-US" : "ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</p>}
        {invoice.status === "awaiting_payment" && invoice.invoice_url && <>
          <p className="text-[12px] leading-relaxed text-[#b4b7c7]">{tp("pay_help")}</p>
          <a href={invoice.invoice_url} className="m-cta m-cta-blue !h-12 text-[15px]" data-testid={`${tid}-open`}>{tp("open")} ↗</a>
        </>}
        {!invoice.invoice_url && invoice.status !== "processing" && <button onClick={() => pay(invoice)} disabled={busy} className="m-cta !h-11 text-[14px]" data-testid={`${tid}-retry-invoice`}>{busy ? t("xrocket.creating") : t("xrocket.retry_invoice")}</button>}
        <button onClick={check} disabled={busy} className="m-cta m-cta-ghost !h-10 text-[13px]" data-testid={`${tid}-check`}>{busy ? t("xrocket.checking") : t("xrocket.check")}</button>
        <p className="text-[11px] text-[#8e91a3] leading-relaxed">{t("xrocket.auto")}</p>
      </>}
      <button onClick={() => { setInvoice(null); setError(""); requestRef.current = null; autoOpenRef.current = null; loadHistory(); }} disabled={busy} className="text-[12px] text-[#00a2ff] hover:text-white disabled:opacity-40" data-testid={`${tid}-new`}>{t("xrocket.new")}</button>
    </div>{invoice && tail}</> : <>
      {P.coins && <fieldset disabled={busy}><legend className="mb-2 m-label">{t("xrocket.currency")}</legend><div className="grid grid-cols-4 gap-1.5">
        {P.coins.filter(([code]) => !info || info.currencies.includes(code)).map(([code, title]) => <button type="button" key={code} onClick={() => setCurrency(code)} aria-pressed={currency === code} aria-label={title} className="coin-tile m-tile flex flex-col items-center gap-2 px-2 pt-3 pb-2.5 text-center" data-testid={`${tid}-currency-${code}`}>
          <img src={coinIcon(code)} alt="" width={40} height={40} className="w-10 h-10 rounded-full object-contain" />
          <span className="min-w-0 w-full"><b className="block text-[13px] leading-tight">{code}</b><span className="block text-[10px] text-white/50 truncate">{title}</span></span>
        </button>)}
      </div></fieldset>}
      {!P.coins && info?.currencies && <div className="flex flex-wrap gap-2" data-testid={`${tid}-assets`}>{info.currencies.map((code) => <span key={code} className="pl-1.5 pr-3 h-9 rounded-full bg-white/5 text-[12px] font-bold text-[#d5d7e2] inline-flex items-center gap-2"><img src={coinIcon(code)} alt="" className="w-6 h-6 rounded-full object-contain" />{code}</span>)}</div>}
      <div className="m-foot space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><label htmlFor={`${tid}-rub`} className="m-label">{t("xrocket.amount")}</label><div className="flex gap-1">{[100, 250, 500, 1000, 2000].map((amount) => <button type="button" key={amount} onClick={() => setRub(String(amount))} disabled={busy} className="m-chip" data-active={num === amount ? "true" : "false"}>{amount} ₽</button>)}</div></div>
      <div className="m-input" data-invalid={num > 0 && !valid ? "true" : "false"}>
        <input id={`${tid}-rub`} value={rub} disabled={busy} onChange={(e) => { const v = e.target.value.replace(",", "."); if (/^\d{0,7}(\.\d{0,2})?$/.test(v)) setRub(v); }} inputMode="decimal" placeholder="0" data-testid={`${tid}-amount`} />
        <span className="text-2xl text-white/50">₽</span>
        <span className="text-[13px] text-white lowercase">{t("xrocket.minimum")}</span>
      </div>
      <PromoInput compact />
      <div className="m-box-dark p-3 space-y-1.5 text-[12px]"><div className="flex justify-between gap-3"><span className="text-white/50">{t("xrocket.credit")}</span><b className="text-[#fdd911] flex items-center gap-1.5" data-testid={`${tid}-credit`}>{formatMoney(valid ? credit : 0)} <RobuxIcon size={12} /></b></div>{authUser?.promo_bonus > 0 && <p className="text-[10px] text-[#61d899]">{t("xrocket.promo")} {authUser.promo_code}</p>}<div className="text-[11px] text-[#61d899]">{t("xrocket.zero_fee")}</div></div>
      <button onClick={() => pay()} disabled={busy || (authUser && (!valid || !info?.enabled))} className="m-cta" data-testid={`${tid}-pay`}>{busy ? t("xrocket.creating") : !authUser ? t("xrocket.login") : <>{t("xrocket.pay")}{valid && <span className="flex items-center gap-1">{formatMoney(credit)} <RobuxIcon size={16} /></span>}</>}</button>
      <p className="m-hint" data-testid={`${tid}-fee`}>{tp("provider_fee")}</p>
      {tail}
      </div>
    </>}
  </div>;
}
