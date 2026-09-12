import React, { useRef, useState } from "react";
import { Minus, Plus, ShoppingCart, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, formatMoney } from "../../lib/api";
import { useAuth } from "../../hooks/useAuth";
import { useLang } from "../../lib/i18n";
import { RobuxIcon } from "../Logo";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../ui/dialog";
import { SkinCard } from "./SkinGrid";
import SkinCatalog from "./SkinCatalog";

const newRequestId = () => {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

export default function SkinShop({ active, tabs, pageSize, user, disabled, onTopUp, onPurchased }) {
  const { authUser, setAuthUser, openAuth } = useAuth();
  const { t } = useLang();
  const [cart, setCart] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const attempt = useRef(null);
  const submitting = useRef(false);
  const count = cart.reduce((sum, row) => sum + row.quantity, 0);
  const totalCents = cart.reduce((sum, row) => sum + Math.round(row.item.price * 100) * row.quantity, 0);
  const total = totalCents / 100;
  const shortage = Math.max(0, totalCents - Math.round((user?.balance || 0) * 100)) / 100;
  const locked = busy || disabled || uncertain;

  const change = (item, delta) => {
    if (locked) return;
    if (!authUser) { openAuth(); return; }
    if (delta > 0 && count >= 100) { toast.error(t("store.limit")); return; }
    attempt.current = null;
    setCart((rows) => {
      const found = rows.find((row) => row.item.id === item.id);
      if (!found) return delta > 0 ? [...rows, { item, quantity: 1 }] : rows;
      return rows.map((row) => row.item.id === item.id ? { ...row, quantity: row.quantity + delta } : row).filter((row) => row.quantity > 0);
    });
  };
  const clear = () => { if (!locked) { setCart([]); attempt.current = null; } };

  const buy = async () => {
    if (submitting.current || disabled || !cart.length || (!uncertain && shortage > 0)) return;
    if (!authUser) { openAuth(); return; }
    submitting.current = true;
    setBusy(true);
    try {
      if (!attempt.current) attempt.current = {
        request_id: newRequestId(), items: cart.map((row) => ({ id: row.item.id, quantity: row.quantity })), expected_total: total,
      };
      const result = await api.buySkins(attempt.current);
      setAuthUser(result.user);
      setCart([]);
      attempt.current = null;
      setUncertain(false);
      setOpen(false);
      toast.success(`${t("store.success")}: ${result.count}`);
      onPurchased?.(result.user);
    } catch (error) {
      const knownFailure = [400, 401, 403, 409, 422].includes(error?.response?.status);
      setUncertain(!knownFailure);
      if (knownFailure) attempt.current = null;
      toast.error(knownFailure ? error.response.data?.detail || t("store.failed") : t("store.retry_purchase"));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };

  return (
    <>
      <div className={active ? "flex flex-1 flex-col" : "hidden"} data-testid="balance-store">
        <div className="h-[52px] shrink-0 px-3 flex items-center gap-2">
          {tabs}
          <button type="button" onClick={() => setOpen(true)} className="ml-auto relative h-8 shrink-0 px-2.5 rounded-lg bg-[#ffb000] hover:bg-[#ffc233] text-black flex items-center gap-1.5 font-bold text-[12px]" aria-label={t("store.cart")} title={t("store.cart")} data-testid="store-cart-button">
            <ShoppingCart size={17} /> {count > 0 && <span data-testid="store-cart-count">{count}</span>}
          </button>
        </div>
        {active && <SkinCatalog pageSize={pageSize} compact testPrefix="store-" renderItem={(item) => {
          const quantity = cart.find((row) => row.item.id === item.id)?.quantity || 0;
          return <div key={item.id} className={`relative rounded-lg ${quantity ? "ring-1 ring-[#ffb000]" : ""}`}>
            <SkinCard item={item} selected={quantity > 0} disabled={locked} onClick={() => change(item, 1)} testId={`store-skin-${item.id}`} />
            {quantity > 0 && <div className="absolute bottom-1 left-1 right-1 h-6 rounded-md bg-[#ffb000] text-black flex items-center justify-between text-[11px] font-black" data-testid={`store-quantity-${item.id}`}>
              <button type="button" disabled={locked} onClick={() => change(item, -1)} className="h-6 w-6 flex items-center justify-center disabled:opacity-40" aria-label={`${t("store.remove_one")} ${item.name}`}><Minus size={13} /></button>
              {quantity}
              <button type="button" disabled={locked || count >= 100} onClick={() => change(item, 1)} className="h-6 w-6 flex items-center justify-center disabled:opacity-40" aria-label={`${t("store.add_one")} ${item.name}`}><Plus size={13} /></button>
            </div>}
          </div>;
        }} />}
      </div>
      <Dialog open={open} onOpenChange={(value) => { if (!busy) setOpen(value); }}>
        <DialogContent className="bg-[#17181e] border border-[#2a2b34] text-white w-[calc(100%-2rem)] sm:max-w-[580px] max-h-[90vh] flex flex-col p-5 sm:p-6 rounded-2xl" data-testid="store-cart-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-[17px]"><ShoppingCart size={18} className="text-[#ffb000]" />{t("store.cart")}</DialogTitle>
            <DialogDescription className="text-[#8e91a3] text-[12px]">{t("store.buy_description")}</DialogDescription>
          </DialogHeader>
          <div className="flex items-center justify-between text-[12px] text-[#8e91a3]">
            <span>{count} {t("common.items_unit")}</span>
            <button type="button" disabled={locked || !cart.length} onClick={clear} className="flex items-center gap-1 hover:text-white disabled:opacity-40" data-testid="store-cart-clear"><Trash2 size={13} />{t("store.clear")}</button>
          </div>
          <div className="min-h-[160px] overflow-y-auto space-y-2 pr-1" data-testid="store-cart-items">
            {cart.length === 0 ? <div className="py-12 text-center text-[13px] text-[#8e91a3]">{t("store.empty_cart")}</div> : cart.map(({ item, quantity }) => (
              <div key={item.id} className="rounded-xl bg-[#22232b] p-3 flex flex-wrap sm:flex-nowrap items-center gap-3" data-testid={`cart-item-${item.id}`}>
                <img src={item.image} alt={item.name} className="w-14 h-14 object-contain shrink-0" />
                <div className="flex-1 min-w-[100px]">
                  <div className="text-[10px] text-[#8e91a3]">{item.type}</div>
                  <div className="text-[13px] font-bold">{item.name}</div>
                  <div className="mt-1 text-[11px] text-[#8e91a3]">{formatMoney(item.price)} RAP × {quantity}</div>
                </div>
                <div className="flex items-center gap-1 rounded-lg bg-[#0f1015]">
                  <button type="button" disabled={locked} onClick={() => change(item, -1)} aria-label={`${t("store.remove_one")} ${item.name}`} className="p-2 disabled:opacity-40"><Minus size={12} /></button>
                  <span className="text-[12px] font-bold">{quantity}</span>
                  <button type="button" disabled={locked || count >= 100} onClick={() => change(item, 1)} aria-label={`${t("store.add_one")} ${item.name}`} className="p-2 disabled:opacity-40"><Plus size={12} /></button>
                </div>
                <span className="font-bold text-[#ffb000] text-[13px] whitespace-nowrap">{formatMoney(Math.round(item.price * 100) * quantity / 100)}</span>
                <button type="button" disabled={locked} onClick={() => change(item, -quantity)} aria-label={`${t("store.remove")} ${item.name}`} className="p-2 rounded-lg text-[#8e91a3] hover:text-[#ff8a8a] disabled:opacity-40"><Trash2 size={14} /></button>
              </div>
            ))}
          </div>
          <div className="border-t border-[#2a2b34] pt-4 space-y-3">
            <div className="flex justify-between text-[13px] text-[#8e91a3]"><span>{t("store.balance")}</span><span>{formatMoney(user?.balance)} RAP</span></div>
            <div className="flex justify-between font-black text-[17px]"><span>{t("store.total")}</span><span className="flex items-center gap-1 text-[#ffb000]" data-testid="store-cart-total">{formatMoney(total)} <RobuxIcon size={14} /></span></div>
            {uncertain && <div className="text-[12px] text-[#ffd166]" role="status">{t("store.retry_purchase")}</div>}
            {shortage > 0 && !uncertain && <div className="rounded-lg border border-[#ffb000]/30 bg-[#ffb000]/10 px-3 py-2 flex items-center justify-between gap-2" data-testid="store-shortage">
              <span className="text-[12px] text-[#ffd166]">{t("store.shortage")} <b>{formatMoney(shortage)} RAP</b></span>
              <button type="button" onClick={() => { setOpen(false); onTopUp(); }} className="h-8 shrink-0 px-3 rounded-lg bg-[#ffb000] text-black text-[12px] font-bold" data-testid="store-topup">{t("skins.topup")}</button>
            </div>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setOpen(false)} disabled={busy} className="h-10 shrink-0 px-3 sm:px-4 rounded-lg border border-[#3b3d47] text-[13px] font-bold disabled:opacity-40">{t("store.cancel")}</button>
              <button type="button" onClick={buy} disabled={busy || disabled || !cart.length || (!uncertain && shortage > 0)} className="min-h-10 min-w-0 flex-1 sm:flex-none sm:min-w-[160px] px-3 py-2 sm:px-5 rounded-lg bg-[#ffb000] hover:bg-[#ffc233] text-black text-[13px] font-black disabled:opacity-40 disabled:cursor-default" data-testid="store-buy">{busy ? t("store.buying") : uncertain ? t("store.check_purchase") : t("store.buy")}</button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
