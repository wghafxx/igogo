import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { getLang } from "../lib/i18n";
import { playTick, prepareResultSounds, playResultSound, playRareSound, stopResultSound } from "../lib/sound";

const RARE_CHANCE = 0.01;
const pickPhrase = (win) => {
  if (Math.random() < RARE_CHANCE) return win ? "gauge.win_rare" : "gauge.lose_rare";
  const pool = win ? ["gauge.win_1", "gauge.win_2"] : ["gauge.lose_1", "gauge.lose_2", "gauge.lose_3"];
  return pool[Math.floor(Math.random() * pool.length)];
};

export const useUpgradeSpin = ({ settings, onUpgraded, onSpinningChange, onResult, onChance }) => {
  const [spinning, setSpinning] = useState(false);
  const [rotation, setRotation] = useState(180);
  const [fast, setFast] = useState(settings.fastSpin);
  const [cashback, setCashback] = useState(0);
  const [phrase, setPhrase] = useState(null);
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
    const key = pickPhrase(res.win);
    setPhrase(key);
    if (key.endsWith("_rare")) playRareSound(res.win ? "mellstroy" : "casino", latest.current.settings.sound);
    else playResultSound(res.win, latest.current.settings.sound);
    latest.current.onUpgraded?.(res);
  }, []);

  const runSpin = async (payload) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setSpinning(true);
    setFast(settings.fastSpin); // changing settings cannot alter an active transition.
    setCashback(0);
    setPhrase(null);
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
      toast.error(error?.response?.data?.detail || (getLang() === "en" ? "Upgrade failed" : "Ошибка апгрейда"));
    }
  };
  return { spinning, rotation, fast, cashback, phrase, busyRef, runSpin, finishSpin };
};