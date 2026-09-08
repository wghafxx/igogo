import React, { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import Gauge from "./Gauge";
import AnimButton from "./AnimButton";
import { Logo, RobuxIcon } from "./Logo";
import { SettingsIcon } from "./icons/settings";
import { VolumeIcon } from "./icons/volume";
import { ZapIcon } from "./icons/zap";
import { CircleHelpIcon } from "./icons/circle-help";
import { SlidersHorizontalIcon } from "./icons/sliders-horizontal";
import { Slider } from "./ui/slider";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { api, formatMoney } from "../lib/api";
import { REEL_FLY, rarityColor } from "../lib/rarity";
import { XIcon } from "./icons/x";

import { playTick, prepareResultSounds } from "../lib/sound";
import { useUpgradeSpin } from "../hooks/useUpgradeSpin";
import { useAuth } from "../hooks/useAuth";

const SlotItem = ({ item, onRemove, testId, disabled }) => (
  <div className="slot-item" style={{ "--rarity": rarityColor(item.rarity) }} data-testid={testId}>
    <AnimButton icon={XIcon} size={14} className="target-remove" disabled={disabled} onClick={onRemove} title="Убрать" data-testid={`${testId}-remove`} />
    <div className="text-center px-8 sm:px-10 pt-3 sm:pt-5">
      <div className="text-[10px] sm:text-[11px] text-[#9a9db0] uppercase tracking-wide truncate">{item.type}</div>
      <div className="text-[14px] sm:text-[17px] font-bold truncate" data-testid={`${testId}-name`}>{item.name}</div>
    </div>
    <img src={item.image} alt={item.name} className="slot-item-img" draggable={false} />
    <div className="text-[13px] sm:text-[14px] font-bold text-[#ffb000] flex items-center justify-center gap-1 pb-3 sm:pb-5">
      {formatMoney(Number(item.price) || 0)} <RobuxIcon size={13} />
    </div>
  </div>
);

const ToolIcon = ({ label, icon, onClick, active, testId, iconProps }) => (
  <TooltipProvider delayDuration={100}>
    <Tooltip>
      <TooltipTrigger asChild>
        <AnimButton
          icon={icon}
          size={14}
          iconProps={iconProps}
          onClick={onClick}
          aria-label={label}
          data-testid={testId}
          className={`w-6 h-6 flex items-center justify-center rounded transition-colors ${active ? "text-[#00a2ff]" : "text-[#5f6377] hover:text-white"}`}
        />
      </TooltipTrigger>
      <TooltipContent className="bg-[#1c1d25] border-0 text-white text-xs">{label}</TooltipContent>
    </Tooltip>
  </TooltipProvider>
);

export default function UpgradePanel({ sessionId, user, settings, onSettingsChange, onOpenSettings, onUpgraded, onSpinningChange, target, onClearTarget, betSkins = [], onRemoveBetSkin }) {
  const { authUser, openAuth } = useAuth();
  const [bet, setBet] = useState(0);
  const [chance, setChance] = useState(0.5);
  const [cfg, setCfg] = useState({ rtp: 0.85, min_chance: 0.01, max_chance: 0.75, max_bet_ratio: 0.75 / 0.85 });
  const [configReady, setConfigReady] = useState(false);
  useEffect(() => {
    api.gameConfig().then((value) => { setCfg(value); setConfigReady(true); }).catch(() => toast.error("Не удалось загрузить параметры игры. Обновите страницу."));
  }, []);
  const MAX_CHANCE = cfg.max_chance;
  const RTP = cfg.rtp;
  const MAX_RATIO = cfg.max_bet_ratio;
  const [activeQuick, setActiveQuick] = useState(null);
  const [result, setResult] = useState(null);
  const [lockedChance, setLockedChance] = useState(null);
  const settleUntil = useRef(0);
  const { rotation, spinning, fast, busyRef, runSpin, finishSpin } = useUpgradeSpin({
    settings, onUpgraded, onSpinningChange, onChance: setLockedChance,
    onResult: (value) => {
      if (value) settleUntil.current = Date.now() + 1500;
      setResult(value);
    },
  });

  const balance = Number(user.balance) || 0;
  const targetPriceNum = Number(target?.price) || 0;
  const skinsTotal = betSkins.reduce((sum, sk) => sum + (Number(sk.price) || 0), 0);
  const maxBet = target && targetPriceNum > 0 ? Math.max(0, Math.min(balance, Math.floor((targetPriceNum * MAX_RATIO - skinsTotal) * 100) / 100)) : 0;
  const totalBet = bet + skinsTotal;
  const overLimit = Boolean(target) && targetPriceNum > 0 && totalBet > targetPriceNum * MAX_RATIO + 1e-6;
  const underMin = Boolean(target) && targetPriceNum > 0 && totalBet > 0 && (totalBet / targetPriceNum) * RTP < cfg.min_chance - 1e-9;
  const canUpgrade = configReady && !spinning && Boolean(target) && totalBet > 0 && bet <= maxBet && !overLimit && !underMin;

  useEffect(() => {
    if (!spinning && bet > maxBet) setBet(maxBet);
  }, [maxBet, bet, spinning]);
  // new target or new bet skins = new game: unlock the zone (never while the wheel is spinning)
  const targetKey = `${target?.id || ""}|${betSkins.map((s) => s.uid).join(",")}`;
  const prevKey = useRef(targetKey);
  useEffect(() => {
    if (prevKey.current !== targetKey && !busyRef.current && Date.now() > settleUntil.current) {
      setLockedChance(null);
      setResult(null);
    }
    prevKey.current = targetKey;
  }, [targetKey, busyRef]);

  const clampChance = (c) => Math.max(cfg.min_chance, Math.min(MAX_CHANCE, c));
  // Показ: bet / price без house edge (20 на кейс 40 = 50%).
  // Реальный шанс победы (с RTP) считает только сервер и на дроп не влияет.
  const effectiveChance = target && totalBet > 0 && targetPriceNum > 0 ? clampChance(totalBet / targetPriceNum) : chance;

  const applyQuick = (c) => {
    playTick(settings.sound);
    setLockedChance(null);
    setResult(null);
    setChance(c);
    if (target && targetPriceNum > 0) setBet(Math.max(0, Math.min(maxBet, Math.round((targetPriceNum * c - skinsTotal) * 100) / 100)));
  };
  const pickMultiplier = (x) => {
    setActiveQuick(`x${x}`);
    applyQuick(clampChance(1 / x));
  };
  const pickPercent = (p) => {
    setActiveQuick(`p${p}`);
    applyQuick(clampChance(p / 100));
  };

  const runUpgrade = async () => {
    if (!authUser) {
      openAuth();
      return;
    }
    if (!canUpgrade || busyRef.current) return;
    await runSpin({
        session_id: sessionId,
        bet_amount: bet,
        bet_items: betSkins.map((sk) => ({ uid: sk.uid })),
        target_item: { id: target.id },
        chance: effectiveChance,
    });
  };

  const targetPrice = targetPriceNum;

  return (
    <section className="fade-up" data-testid="upgrade-panel">
      <div className="flex items-center gap-1 mb-2">
        <ToolIcon label="Как работает апгрейд" icon={CircleHelpIcon} onClick={() => toast.info("Выберите цель, добавьте скин или баланс и нажмите «Прокачать». Шанс зависит от стоимости ставки и цели.")} testId="info-icon" />
        <ToolIcon label="Настройки" icon={SettingsIcon} onClick={onOpenSettings} testId="settings-icon" />
        <ToolIcon
          label={settings.sound ? "Звук включен" : "Звук выключен"}
          icon={VolumeIcon}
          iconProps={{ on: settings.sound }}
          active={settings.sound}
          onClick={() => { prepareResultSounds(); onSettingsChange({ ...settings, sound: !settings.sound }); }}
          testId="sound-icon"
        />
        <ToolIcon
          label={settings.fastSpin ? "Ускоренная прокрутка" : "Обычная прокрутка"}
          icon={ZapIcon}
          active={settings.fastSpin}
          onClick={() => onSettingsChange({ ...settings, fastSpin: !settings.fastSpin })}
          testId="fast-icon"
        />
      </div>

      {/* Row 1: source panel | gauge | target panel */}
      <div className="grid grid-cols-2 lg:grid-cols-[1fr_300px_1fr] gap-2 sm:gap-3 lg:gap-x-6 lg:gap-y-3 items-stretch">
        <div className="blox-panel relative overflow-hidden h-[230px] sm:h-[300px] px-3 sm:px-4 pt-4 sm:pt-5 pb-3 sm:pb-4 flex flex-col order-2 lg:order-none" data-testid="source-panel">
          {betSkins.length > 0 && <SlotItem item={betSkins[0]} disabled={spinning} onRemove={() => onRemoveBetSkin(betSkins[0].uid)} testId="bet-skin" />}
          <div className="text-center">
            <div className="text-[12px] sm:text-[13px] font-bold">Выберите скины или скины и баланс для использования</div>
            <div className="text-[11px] text-[#7d8194] mt-1 flex items-center justify-center gap-1">
              Ставка: <RobuxIcon size={11} /> <span className="tabular-nums" data-testid="total-bet">{formatMoney(totalBet)}</span>
            </div>
          </div>
          <div className="upgrade-slot slot-bg flex-1 flex items-center justify-center" data-testid="source-slot">
            <img src={REEL_FLY[1].image} alt="" className="slot-ghost" draggable={false} />
            <Logo size={92} className="relative rotate-180 w-[64px] h-[64px] sm:w-[92px] sm:h-[92px] drop-shadow-[0_0_28px_rgba(0,162,255,0.45)]" />
          </div>
        </div>

        <div className="col-span-2 lg:col-span-1 flex items-center justify-center order-1 lg:order-none">
          <Gauge chance={lockedChance ?? effectiveChance} rotation={rotation} spinning={spinning} fast={fast} result={result} onSpinEnd={finishSpin} />
        </div>

        <div className="blox-panel relative overflow-hidden h-[230px] sm:h-[300px] px-3 sm:px-4 pt-4 sm:pt-5 pb-3 sm:pb-4 flex flex-col order-3 lg:order-none" data-testid="target-panel">
          {target && <SlotItem item={target} disabled={spinning} onRemove={onClearTarget} testId="target-item" />}
          <div className="text-center">
            <div className="text-[12px] sm:text-[13px] font-bold">Выберите скин для апгрейда</div>
            <div className="text-[11px] text-[#7d8194] mt-1 flex items-center justify-center gap-1">
              Цель: <RobuxIcon size={11} /> <span className="tabular-nums">{formatMoney(targetPrice)}</span>
            </div>
          </div>
          <div className="upgrade-slot slot-bg flex-1 flex items-center justify-center" data-testid="target-slot">
            <img src={REEL_FLY[1].image} alt="" className="slot-ghost" draggable={false} />
            <Logo size={92} className="relative w-[64px] h-[64px] sm:w-[92px] sm:h-[92px] drop-shadow-[0_0_28px_rgba(255,138,0,0.4)]" />
          </div>
        </div>

        {/* Row 2: balance | upgrade button | quick pick */}
        <div className="blox-panel min-h-11 px-4 py-1.5 flex flex-col justify-center gap-1.5 col-span-2 lg:col-span-1 order-5 lg:order-none" data-testid="balance-slider-block">
          <div className="flex items-center justify-between gap-2 text-[10px] leading-none">
            <span className="text-[#7d8194] whitespace-nowrap">Сумма баланса</span>
            <span className="flex items-center gap-1 font-bold whitespace-nowrap">
              <span className="tabular-nums" data-testid="bet-amount">{formatMoney(bet)}</span> <RobuxIcon size={10} />
              <span className="text-[#5f6377] font-normal">(макс {formatMoney(maxBet)})</span>
            </span>
          </div>
          <Slider
            data-testid="bet-slider"
            aria-label="Сумма ставки с баланса"
            value={[Math.min(bet, maxBet)]}
            min={0}
            max={Math.max(maxBet, 0.01)}
            step={0.01}
            disabled={maxBet <= 0 || spinning}
            onValueChange={(v) => { setLockedChance(null); setResult(null); setBet(Number(v[0])); }}
            className="w-full [&_[role=slider]]:h-3.5 [&_[role=slider]]:w-3.5 [&_[role=slider]]:bg-[#00a2ff] [&_[role=slider]]:border-[#00a2ff] [&_.bg-primary]:bg-[#00a2ff] [&_.bg-primary\/20]:bg-[#262833]"
          />
        </div>

        <button
          className="blox-btn-primary h-11 w-full flex items-center justify-center gap-2 text-[14px] col-span-2 lg:col-span-1 order-4 lg:order-none"
          disabled={authUser ? !canUpgrade : false}
          onClick={runUpgrade}
          data-testid="upgrade-button"
        >
          <Logo size={16} />
          {spinning ? "Крутим..." : !authUser ? "Войти через Discord" : !target ? "Выберите скин" : overLimit ? `Ставка выше ${Math.round(MAX_RATIO * 100)}% цели` : "Прокачать"}
        </button>

        <div className="blox-panel min-h-11 px-2 py-1.5 flex flex-wrap items-center justify-between gap-2 col-span-2 lg:col-span-1 order-6 lg:order-none" data-testid="quick-pick">
          <div className="flex gap-1">
            {settings.multipliers.map((x) => (
              <button key={x} className={`blox-toggle h-7 px-2.5 text-[12px] ${activeQuick === `x${x}` ? "active" : ""}`} onClick={() => pickMultiplier(x)} disabled={spinning} data-testid={`mult-x${x}`}>
                x{x}
              </button>
            ))}
          </div>
          <div className="flex gap-1">
            {settings.percents.map((p) => (
              <button key={p} className={`blox-toggle h-7 px-2 text-[12px] ${activeQuick === `p${p}` ? "active" : ""}`} onClick={() => pickPercent(p)} disabled={spinning} data-testid={`pct-${p}`}>
                {p}%
              </button>
            ))}
          </div>
          <AnimButton
            icon={SlidersHorizontalIcon}
            size={15}
            className="w-7 h-7 flex items-center justify-center text-[#7d8194] hover:text-white transition-colors"
            onClick={onOpenSettings}
            data-testid="quick-settings-button"
          />
        </div>
      </div>
    </section>
  );
}
