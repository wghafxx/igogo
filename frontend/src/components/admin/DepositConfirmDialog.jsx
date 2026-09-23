import React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../ui/dialog";
import { Btn } from "./chat/ui";

export default function DepositConfirmDialog({ open, description, busy, onConfirm, onClose }) {
  if (!open) return null;
  return <Dialog open onOpenChange={(next) => { if (!next && !busy) onClose(); }}>
    <DialogContent className="modal-surface w-[92vw] max-w-[420px] border-0 text-white p-6" data-testid="deposit-confirm-dialog">
      <DialogHeader className="text-left">
        <DialogTitle className="modal-title">Вы уверены?</DialogTitle>
        <DialogDescription className="text-white/60 text-sm leading-relaxed whitespace-pre-line">{description}</DialogDescription>
      </DialogHeader>
      <div className="flex gap-2">
        <Btn className="flex-1" onClick={onClose} disabled={busy}>Отмена</Btn>
        <Btn tone="success" className="flex-1" onClick={onConfirm} disabled={busy} data-testid="deposit-confirm-submit">{busy ? "Пополнение…" : "Да, пополнить"}</Btn>
      </div>
    </DialogContent>
  </Dialog>;
}
