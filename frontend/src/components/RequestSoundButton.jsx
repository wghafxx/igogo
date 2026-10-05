import React from "react";
import { Volume2, VolumeX } from "lucide-react";

export default function RequestSoundButton({ soundOn, blocked, toggleSound }) {
  const Icon = soundOn && !blocked ? Volume2 : VolumeX;
  const label = blocked ? "Включить звук заявок" : soundOn ? "Звук заявок включён" : "Звук заявок выключен";
  return <button onClick={toggleSound} aria-pressed={soundOn && !blocked}
    aria-label={label}
    className={`blox-chip h-9 px-3 text-[12px] font-bold inline-flex items-center gap-1.5 ${soundOn && !blocked ? "text-[#7ee2a8]" : "text-[#9a9db0]"}`}
    title={blocked ? "Браузер заблокировал звук. Нажмите, чтобы разрешить и проверить его." : "Звук только при новой заявке. Нажатие включает с проверкой или выключает звук."}
    data-testid="request-sound-toggle">
    <Icon size={15} /><span className="hidden sm:inline">{label}</span>
  </button>;
}
