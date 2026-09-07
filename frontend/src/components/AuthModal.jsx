import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { Checkbox } from "./ui/checkbox";
import DiscordButton from "./DiscordButton";
import { discordLoginUrl } from "../lib/api";

const Check = ({ checked, onChange, testId, children }) => (
  <label className="flex items-start gap-3 cursor-pointer select-none">
    <Checkbox
      checked={checked}
      onCheckedChange={(v) => onChange(Boolean(v))}
      className="mt-0.5 h-[18px] w-[18px] rounded-[5px] border-[#3a3d4d] bg-[#23242d] data-[state=checked]:bg-[#00a2ff] data-[state=checked]:border-[#00a2ff]"
      data-testid={testId}
    />
    <span className="text-[14px] text-[#d5d7e2] leading-snug">{children}</span>
  </label>
);

export default function AuthModal({ open, onOpenChange }) {
  const [adult, setAdult] = useState(false);
  const [tos, setTos] = useState(false);
  const ready = adult && tos;

  const startLogin = () => {
    if (!ready) return;
    localStorage.setItem("bloxgrade_tos", "1");
    window.location.href = discordLoginUrl;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1e1f23] border-0 text-white sm:max-w-[460px] p-0 overflow-hidden rounded-2xl" data-testid="auth-modal">
        <DialogHeader className="px-6 py-5 border-b border-[#2a2b31]">
          <DialogTitle className="text-[18px] font-bold text-left">Авторизация</DialogTitle>
        </DialogHeader>
        <div className="px-6 pt-5 pb-6 space-y-5">
          <p className="text-[15px] leading-snug" data-testid="auth-modal-text">
            Чтобы продолжить, примите условия пользования сервиса и войдите через Discord.
          </p>
          <div className="space-y-3">
            <Check checked={adult} onChange={setAdult} testId="auth-adult-checkbox">
              Я подтверждаю, что мне больше 18 лет
            </Check>
            <Check checked={tos} onChange={setTos} testId="auth-tos-checkbox">
              Я принимаю{" "}
              <Link to="/tos" className="text-[#00a2ff] font-semibold hover:underline" onClick={() => onOpenChange(false)} data-testid="auth-tos-link">
                правила и положения
              </Link>{" "}
              использования веб-сайта
            </Check>
          </div>
          <DiscordButton size="lg" className="w-full" onClick={startLogin} disabled={!ready} data-testid="discord-login-button" />
        </div>
      </DialogContent>
    </Dialog>
  );
}
