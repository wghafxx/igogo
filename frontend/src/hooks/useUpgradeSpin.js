import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { playTick, prepareResultSounds, playResultSound, stopResultSound } from "../lib/sound";

export const useUpgradeSpin = ({ settings, onUpgraded, onSpinningChange, onResult, onChance }) => {
  const [spinning, setSpinning] = useState(false);
  const [rotation, setRotation] = useState(180);
  const [fast, setFast] = useState(settings.fastSpin);
  const [cashback, setCashback] = useState(0);
  const busyRef = useRef(false);
  const pending = useRef(null);
  const alive = useRef(true);
  const latest = useRef({ settings, onUpgraded, onSpinningChange, onResult, onChance });
  latest.current = { settings, onUpgraded, onSpinningChange, onResult, onChance };

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; pending.current = null; stopResultSound(); };
  }, []);
  useEffect(() => {
    if (!settings.sound) stopResultSound();
  }, [settings.sound]);

  const finishSpin = useCallback(() => {
    const res = pending.current;
    if (!alive.current || !res) return;
    pending.current = null; // transition events may bubble or repeat: settle once.
    busyRef.current = false;
    setSpinning(false);
    latest.current.onSpinningChange?.(false);
    latest.current.onResult(res.win ? "win" : "lose");
    setCashback(Number(res.cashback) || 0);
    playResultSound(res.win, latest.current.settings.sound);
    latest.current.onUpgraded?.(res);
  }, []);

  const runSpin = async (payload) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setSpinning(true);
    setFast(settings.fastSpin); // changing settings cannot alter an active transition.
    setCashback(0);
    onSpinningChange?.(true);
    onResult(null);
    prepareResultSounds();
    playTick(settings.sound);
    try {
      const res = await api.upgrade(payload);
      if (!alive.current) return;
      pending.current = res;
      latest.current.onChance(res.display_chance ?? res.chance);
      setRotation((r) => r + 4 * 360 + (((180 + res.angle - r) % 360) + 360) % 360);
    } catch (error) {
      if (!alive.current) return;
      busyRef.current = false;
      setSpinning(false);
      latest.current.onSpinningChange?.(false);
      toast.error(error?.response?.data?.detail || "Ошибка апгрейда");
    }
  };
  return { spinning, rotation, fast, cashback, busyRef, runSpin, finishSpin };
};