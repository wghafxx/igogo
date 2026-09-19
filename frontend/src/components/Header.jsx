import React from "react";
import { Link } from "../lib/router";
import { ChevronDownIcon } from "./icons/chevron-down";
import { LogoutIcon } from "./icons/logout";
import { FileTextIcon } from "./icons/file-text";
import { UserIcon } from "./icons/user";
import { LinkIcon } from "./icons/link";
import { Logo, BrandWordmark, BrandAvatar, RobuxIcon, VkIcon } from "./Logo";
import AnimButton from "./AnimButton";
import DiscordButton from "./DiscordButton";
import Notifications from "./Notifications";
import { WalletIcon } from "./icons/wallet";
import TelegramIcon from "./TelegramIcon";
import { formatNumber, formatMoney } from "../lib/api";
import { useLang } from "../lib/i18n";
import LangSwitcher from "./LangSwitcher";
import { useAuth } from "../hooks/useAuth";
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

const CHANNEL_URL = "https://t.me/bloxgrade";

const StatBlock = ({ label, value, icon, mobile = false }) => (
  <div className={`${mobile ? "hidden min-[380px]:flex" : "hidden md:flex"} items-center gap-2 ${mobile ? "md:min-w-[86px]" : "min-w-[110px]"}`}>
    <span className="text-[#ffb000]">{icon}</span>
    <div className="leading-tight">
      <div className={`${mobile ? "hidden md:block" : ""} text-[12px] text-[#8e91a3] font-medium`}>{label}</div>
      <div className="text-[15px] font-bold text-white tabular-nums">{value}</div>
    </div>
  </div>
);

const ProfileMenu = ({ t, authUser, onLogout }) => (
  <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <button className="blox-chip h-10 sm:h-11 pl-1 pr-3 flex items-center gap-2 text-white font-bold text-sm sm:text-[15px]" data-testid="profile-button">
        <img src={authUser.avatar} alt={authUser.nickname} className="w-8 h-8 sm:w-9 sm:h-9 rounded-md object-cover" data-testid="profile-avatar" />
        <Nick gold={authUser.gold_nick} className="hidden sm:block max-w-[110px] truncate" testId="profile-nickname">
          {authUser.nickname}
        </Nick>
        <ChevronDownIcon size={14} className="text-[#8e91a3]" />
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="w-56 bg-[#16171d] border-0 text-white" data-testid="profile-menu">
      <DropdownMenuLabel className="text-xs text-[#8e91a3]">{t("header.discord_account")}</DropdownMenuLabel>
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
          <UserIcon size={14} className="mr-2" /> {t("header.profile")}
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild className="focus:bg-[#22242e] focus:text-white cursor-pointer">
        <Link to={`/users/${authUser.discord_id}`} data-testid="menu-public-profile-link">
          <LinkIcon size={14} className="mr-2" /> {t("header.public_page")}
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild className="focus:bg-[#22242e] focus:text-white cursor-pointer">
        <Link to="/profile?tab=referrals" reloadDocument data-testid="menu-referrals-link">
          <LinkIcon size={14} className="mr-2" /> {t("referrals.title")}
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild className="focus:bg-[#22242e] focus:text-white cursor-pointer">
        <Link to="/tos" data-testid="menu-tos-link">
          <FileTextIcon size={14} className="mr-2" /> {t("header.tos")}
        </Link>
      </DropdownMenuItem>
      <DropdownMenuSeparator className="bg-[#262833]" />
      <DropdownMenuItem onClick={onLogout} className="focus:bg-[#22242e] focus:text-white cursor-pointer text-[#ff6b6b]" data-testid="logout-button">
        <LogoutIcon size={14} className="mr-2" /> {t("header.logout")}
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
);

export default function Header({ stats, user, topUpOpen, setTopUpOpen }) {
  const { authUser, logout, openAuth } = useAuth();
  const { t } = useLang();
  const openTopUp = () => setTopUpOpen(true);

  return (
    <header
      className="h-[64px] sm:h-[72px] flex items-center justify-between gap-2 px-3 sm:px-5 border-b border-[#15161b]/80 bg-[#0f1015]/85 backdrop-blur-md sticky top-0 z-40"
      data-testid="header"
    >
      <div className="flex items-center gap-3 sm:gap-6 min-w-0">
        <Link to="/" className="flex items-center gap-2 group shrink-0" data-testid="logo-link">
          <BrandAvatar size={40} testId="header-brand-icon" className="transition-transform duration-200 group-hover:scale-110" />
          <BrandWordmark className="hidden sm:block text-[28px] leading-none" testId="header-brand-wordmark" />
        </Link>

        <StatBlock
          mobile
          label={t("header.online")}
          value={<span data-testid="online-count">{formatNumber(stats.online)}</span>}
          icon={<span className="inline-block w-2.5 h-2.5 rounded-full bg-[#2ecc71] pulse-dot" />}
        />
        <StatBlock
          label={t("header.upgrades")}
          value={<span data-testid="upgrades-count">{formatNumber(stats.upgrades)}</span>}
          icon={<Logo size={16} />}
        />
      </div>

      <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
        <div className="hidden md:block">
          <LangSwitcher />
        </div>
        <button
          className="blox-chip w-11 h-11 hidden sm:flex items-center justify-center text-[#9a9db0] hover:text-white"
          title={t("header.telegram")}
          onClick={() => window.open(CHANNEL_URL, "_blank", "noopener")}
          data-testid="telegram-link"
        ><TelegramIcon size={18} /></button>
        {process.env.REACT_APP_VK_URL && <a
          href={process.env.REACT_APP_VK_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="blox-chip w-11 h-11 hidden sm:flex items-center justify-center text-[#9a9db0] hover:text-white"
          title="VK"
          data-testid="vk-link"
        >
          <VkIcon />
        </a>}

        {authUser ? (
          <>
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <button className="blox-chip h-10 sm:h-11 px-2.5 sm:px-4 flex items-center gap-1.5 sm:gap-2 text-white font-bold text-sm sm:text-[15px] max-w-[140px] sm:max-w-none" data-testid="balance-button">
                  <RobuxIcon size={18} />
                  <span className="tabular-nums truncate" data-testid="header-balance">{formatMoney(user.balance)}</span>
                  <ChevronDownIcon size={14} className="text-[#8e91a3]" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 bg-[#16171d] border-0 text-white">
                <DropdownMenuLabel className="text-[#8e91a3] text-xs">{t("header.balance")}</DropdownMenuLabel>
                <div className="px-2 pb-2 flex items-center gap-2 text-lg font-bold">
                  <RobuxIcon size={18} /> {formatMoney(user.balance)}
                </div>
                <DropdownMenuSeparator className="bg-[#262833]" />
                <DropdownMenuItem onSelect={openTopUp} data-testid="balance-menu-topup" className="focus:bg-[#22242e] focus:text-white cursor-pointer">
                  <WalletIcon size={14} className="mr-2" /> {t("header.topup")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <AnimButton icon={WalletIcon} size={18} className="blox-btn-primary h-11 px-6 min-w-[150px] hidden sm:flex items-center gap-2 text-[15px]" onClick={openTopUp} data-testid="topup-button">
              <span>{t("header.topup")}</span>
            </AnimButton>
            <AnimButton
              icon={WalletIcon}
              size={16}
              className="blox-btn-primary w-10 h-10 flex sm:hidden items-center justify-center"
              onClick={openTopUp}
              title={t("header.topup")}
              data-testid="topup-button-mobile"
            />

            <Notifications key={authUser.session_id} />

            <ProfileMenu t={t} authUser={authUser} onLogout={logout} />
          </>
        ) : (
          <DiscordButton size="md" className="whitespace-nowrap shrink-0 !h-10 sm:!h-12 !px-4 sm:!px-7 sm:!text-[15px] sm:min-w-[248px]" onClick={openAuth} data-testid="header-login-button">
            <span className="sm:hidden">{t("header.login")}</span>
            <span className="hidden sm:inline">{t("header.login_discord")}</span>
          </DiscordButton>
        )}
      </div>

      <TopUpModal open={topUpOpen} onOpenChange={setTopUpOpen} />
    </header>
  );
}
