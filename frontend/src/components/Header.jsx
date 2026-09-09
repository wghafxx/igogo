import React from "react";
import { Link } from "react-router-dom";
import { ChevronDownIcon } from "./icons/chevron-down";
import { LogoutIcon } from "./icons/logout";
import { FileTextIcon } from "./icons/file-text";
import { UserIcon } from "./icons/user";
import { LinkIcon } from "./icons/link";
import { Logo, RobuxIcon, VkIcon } from "./Logo";
import AnimButton from "./AnimButton";
import DiscordButton from "./DiscordButton";
import { BellIcon } from "./icons/bell";
import { WalletIcon } from "./icons/wallet";
import { SendIcon } from "./icons/send";
import { formatNumber, formatMoney } from "../lib/api";
import { useAuth } from "../hooks/useAuth";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import TopUpModal from "./TopUpModal";
import Nick from "./Nick";

const SUPPORT_URL = process.env.REACT_APP_TELEGRAM_SUPPORT_URL;

const StatBlock = ({ label, value, icon, mobile = false }) => (
  <div className={`${mobile ? "flex" : "hidden md:flex"} items-center gap-2`}>
    <span className="text-[#ffb000]">{icon}</span>
    <div className="leading-tight">
      <div className={`${mobile ? "hidden md:block" : ""} text-[11px] text-[#8e91a3] font-medium`}>{label}</div>
      <div className="text-[13px] font-bold text-white tabular-nums">{value}</div>
    </div>
  </div>
);

const ProfileMenu = ({ authUser, onLogout }) => (
  <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <button className="blox-chip h-9 pl-1 pr-2.5 flex items-center gap-2 text-white font-bold text-sm" data-testid="profile-button">
        <img src={authUser.avatar} alt={authUser.nickname} className="w-7 h-7 rounded-md object-cover" data-testid="profile-avatar" />
        <Nick gold={authUser.gold_nick} className="hidden sm:block max-w-[110px] truncate" testId="profile-nickname">
          {authUser.nickname}
        </Nick>
        <ChevronDownIcon size={14} className="text-[#8e91a3]" />
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="w-56 bg-[#16171d] border-0 text-white" data-testid="profile-menu">
      <DropdownMenuLabel className="text-xs text-[#8e91a3]">Аккаунт Discord</DropdownMenuLabel>
      <div className="px-2 pb-2 flex items-center gap-2">
        <img src={authUser.avatar} alt="" className="w-8 h-8 rounded-md" />
        <div className="min-w-0">
          <Nick gold={authUser.gold_nick} className="font-bold text-sm truncate block">{authUser.nickname}</Nick>
          <div className="text-[10px] text-[#8e91a3]">ID: {authUser.discord_id}</div>
        </div>
      </div>
      <DropdownMenuSeparator className="bg-[#262833]" />
      <DropdownMenuItem asChild className="focus:bg-[#22242e] focus:text-white cursor-pointer">
        <Link to="/profile" data-testid="menu-profile-link">
          <UserIcon size={14} className="mr-2" /> Профиль
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild className="focus:bg-[#22242e] focus:text-white cursor-pointer">
        <Link to={`/users/${authUser.discord_id}`} data-testid="menu-public-profile-link">
          <LinkIcon size={14} className="mr-2" /> Моя публичная страница
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild className="focus:bg-[#22242e] focus:text-white cursor-pointer">
        <Link to="/tos" data-testid="menu-tos-link">
          <FileTextIcon size={14} className="mr-2" /> Пользовательское соглашение
        </Link>
      </DropdownMenuItem>
      <DropdownMenuSeparator className="bg-[#262833]" />
      <DropdownMenuItem onClick={onLogout} className="focus:bg-[#22242e] focus:text-white cursor-pointer text-[#ff6b6b]" data-testid="logout-button">
        <LogoutIcon size={14} className="mr-2" /> Выйти
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
);

export default function Header({ stats, user, topUpOpen, setTopUpOpen }) {
  const { authUser, logout, openAuth } = useAuth();
  const openTopUp = () => setTopUpOpen(true);

  return (
    <header
      className="h-[54px] flex items-center justify-between gap-2 px-3 sm:px-4 border-b border-[#15161b] bg-[#0f1015] sticky top-0 z-40"
      data-testid="header"
    >
      <div className="flex items-center gap-3 sm:gap-6 min-w-0">
        <Link to="/" className="flex items-center gap-2 group shrink-0" data-testid="logo-link">
          <Logo size={34} className="transition-transform duration-200 group-hover:scale-110" />
          <span className="hidden sm:inline text-white font-black tracking-wide text-[24px] uppercase">BLOXGRADE</span>
        </Link>

        <StatBlock
          mobile
          label="Онлайн"
          value={<span data-testid="online-count">{formatNumber(stats.online)}</span>}
          icon={<span className="inline-block w-2.5 h-2.5 rounded-full bg-[#2ecc71] pulse-dot" />}
        />
        <StatBlock
          label="Апгрейдов"
          value={<span data-testid="upgrades-count">{formatNumber(stats.upgrades)}</span>}
          icon={<Logo size={16} />}
        />
      </div>

      <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
        {SUPPORT_URL && (
          <AnimButton
            icon={SendIcon}
            size={15}
            className="blox-chip w-9 h-9 hidden sm:flex items-center justify-center text-[#9a9db0] hover:text-white"
            title="Поддержка в Telegram"
            onClick={() => window.open(SUPPORT_URL, "_blank", "noopener")}
            data-testid="telegram-link"
          />
        )}
        {process.env.REACT_APP_VK_URL && <a
          href={process.env.REACT_APP_VK_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="blox-chip w-9 h-9 hidden sm:flex items-center justify-center text-[#9a9db0] hover:text-white"
          title="VK"
          data-testid="vk-link"
        >
          <VkIcon />
        </a>}

        {authUser ? (
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="blox-chip h-9 px-2 sm:px-3 flex items-center gap-1 sm:gap-2 text-white font-bold text-xs sm:text-sm max-w-[130px] sm:max-w-none" data-testid="balance-button">
                  <RobuxIcon size={16} />
                  <span className="tabular-nums truncate" data-testid="header-balance">{formatMoney(user.balance)}</span>
                  <ChevronDownIcon size={14} className="text-[#8e91a3]" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 bg-[#16171d] border-0 text-white">
                <DropdownMenuLabel className="text-[#8e91a3] text-xs">Баланс</DropdownMenuLabel>
                <div className="px-2 pb-2 flex items-center gap-2 text-lg font-bold">
                  <RobuxIcon size={18} /> {formatMoney(user.balance)}
                </div>
                <DropdownMenuSeparator className="bg-[#262833]" />
                <DropdownMenuItem onClick={openTopUp} className="focus:bg-[#22242e] focus:text-white cursor-pointer">
                  <WalletIcon size={14} className="mr-2" /> Пополнить
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <AnimButton icon={WalletIcon} size={16} className="blox-btn-primary h-9 px-4 hidden sm:flex items-center gap-2 text-sm" onClick={openTopUp} data-testid="topup-button">
              <span>Пополнить</span>
            </AnimButton>
            <AnimButton
              icon={WalletIcon}
              size={16}
              className="blox-btn-primary w-9 h-9 flex sm:hidden items-center justify-center"
              onClick={openTopUp}
              title="Пополнить"
              data-testid="topup-button-mobile"
            />

            <Popover>
              <PopoverTrigger asChild>
                <AnimButton icon={BellIcon} size={18} className="w-9 h-9 hidden sm:flex items-center justify-center text-[#9a9db0] hover:text-white transition-colors" data-testid="notifications-button" />
              </PopoverTrigger>
              <PopoverContent align="end" className="w-72 bg-[#16171d] border-0 text-white p-0 shadow-xl">
                <div className="px-4 py-3 border-b border-[#262833] font-bold text-sm">Уведомления</div>
                <div className="px-4 py-8 text-center text-sm text-[#8e91a3]">Нет новых уведомлений</div>
              </PopoverContent>
            </Popover>

            <ProfileMenu authUser={authUser} onLogout={logout} />
          </>
        ) : (
          <DiscordButton size="sm" className="whitespace-nowrap shrink-0" onClick={openAuth} data-testid="header-login-button">
            <span className="sm:hidden">Войти</span>
            <span className="hidden sm:inline">Войти через Discord</span>
          </DiscordButton>
        )}
      </div>

      <TopUpModal open={topUpOpen} onOpenChange={setTopUpOpen} />
    </header>
  );
}
