import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../ui/dialog";

// Confirmation with PIN for sensitive bank actions. `request` = { title, description, confirmLabel, danger, onConfirm(pin) }.
export default function PinConfirmDialog({ request, onClose }) {
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (request) { setPin(""); setBusy(false); } }, [request]);
  if (!request) return null;
  const submit = async () => {
    if (pin.length < 4 || busy) return;
    setBusy(true);
    try {
      await request.onConfirm(pin);
      onClose();
    } catch {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
      <DialogContent className="modal-surface w-[92vw] max-w-[420px] border-0 text-white p-6" data-testid="pin-dialog">
        <DialogHeader className="text-left">
          <DialogTitle className={`modal-title ${request.danger ? "text-[#ff8a8a]" : ""}`} data-testid="pin-dialog-title">{request.title}</DialogTitle>
          <DialogDescription className="text-white/60 text-sm leading-relaxed whitespace-pre-line" data-testid="pin-dialog-description">{request.description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <div className="m-label">PIN-код подтверждения</div>
          <div className="m-input m-input-sm" data-testid="pin-dialog-input-box">
            <input
              type="password"
              inputMode="numeric"
              autoComplete="off"
              autoFocus
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 8))}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="••••"
              className="tracking-[0.4em] font-black"
              data-testid="pin-dialog-input"
            />
          </div>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={busy} className="m-cta m-cta-ghost !h-10 flex-1 text-[13px]" data-testid="pin-dialog-cancel">Отмена</button>
          <button type="button" onClick={submit} disabled={busy || pin.length < 4} className={`m-cta !h-10 flex-1 text-[13px] ${request.danger ? "!bg-[#ff5c5c] !text-white hover:!bg-[#ff7676]" : ""}`} data-testid="pin-dialog-confirm">
            {busy ? "…" : request.confirmLabel || "Подтвердить"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
