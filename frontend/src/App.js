import React, { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";
import "./App.css";
import { BrowserRouter, Routes, Route, Outlet, Navigate, useLocation, useParams } from "react-router-dom";
import { Link } from "./lib/router";
import { SUPPORTED_LANGS, detectLang } from "./lib/locale";
import { Toaster } from "./components/ui/sonner";
import Header from "./components/Header";
import LiveDrop, { LiveDropStrip } from "./components/LiveDrop";
import UpgradePanel from "./components/UpgradePanel";
import SkinsSection from "./components/SkinsSection";
import SettingsModal from "./components/SettingsModal";
import { BrandAvatar, BrandWordmark } from "./components/Logo";
import { useSession, loadSettings, saveSettings, normalizeSettings } from "./hooks/useSession";
import { LangProvider, useLang } from "./lib/i18n";

// /ru or /en prefix guard: legacy paths (no prefix) get redirected to the detected language.
const LangGate = () => {
  const { lang } = useParams();
  const location = useLocation();
  if (!SUPPORTED_LANGS.includes(lang)) {
    return <Navigate to={`/${detectLang()}${location.pathname}${location.search}${location.hash}`} replace />;
  }
  return <Outlet />;
};

const RootRedirect = () => {
  const location = useLocation();
  return <Navigate to={`/${detectLang()}${location.search}${location.hash}`} replace />;
};

const NotFound = () => {
  const { t } = useLang();
  return (
    <div className="blox-panel max-w-[860px] mx-auto p-8 text-center" data-testid="not-found-page">
      <h1 className="text-3xl font-bold" data-testid="not-found-title">{t("footer.not_found")}</h1>
      <Link to="/" className="inline-block mt-5 text-[#00a2ff]" data-testid="not-found-home">{t("common.back_home")}</Link>
    </div>
  );
};
import { AuthProvider } from "./hooks/useAuth";
import { SessionProvider, useSessionCtx } from "./hooks/useSessionCtx";
import { SUPPORT_HANDLE } from "./components/SupportDialog";
import { api } from "./lib/api";
import { toast } from "sonner";
import LiveChatWidget from "./components/chat/LiveChatWidget";
import PointerEventsGuard from "./components/PointerEventsGuard";
import { preventGameDrag } from "./lib/game-interactions";
import { openLiveChat, openRubTopUp } from "./lib/events";

// Secondary pages are split into their own chunks so the home screen loads with the minimum JS.
const TosPage = lazy(() => import("./pages/TosPage"));
const PrivacyPage = lazy(() => import("./pages/PrivacyPage"));
const AuthCallbackPage = lazy(() => import("./pages/AuthCallbackPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const PublicProfilePage = lazy(() => import("./pages/PublicProfilePage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const StaffPage = lazy(() => import("./pages/StaffPage"));

const PageFallback = () => (
  <div className="blox-panel max-w-[860px] mx-auto p-8 text-center text-sm text-[#8e91a3]" data-testid="page-loading">…</div>
);

// Header + live-drop feed shared by every page
const Shell = () => {
  const session = useSession();
  const { t } = useLang();
  const [topUpOpen, setTopUpOpen] = useState(false);
  const openWithdrawalSupport = useCallback(async () => {
    try {
      const created = await api.createChat({ kind: "withdrawal" });
      openLiveChat(created.id);
    } catch (e) {
      const m = e?.response?.data?.detail;
      toast.error(typeof m === "string" ? m : t("chat.create_error"));
    }
  }, [t]);
  const { sessionId, stats, setStats, user, setUser, refreshUser, drops, bestDrop, refreshDrops, pauseUserRefresh } = session;
  // Stable context value: consumers re-render only when a field they read actually changes.
  const ctx = useMemo(() => ({ sessionId, stats, setStats, user, setUser, refreshUser, drops, bestDrop, refreshDrops, pauseUserRefresh, topUpOpen, setTopUpOpen, openWithdrawalSupport }),
    [sessionId, stats, setStats, user, setUser, refreshUser, drops, bestDrop, refreshDrops, pauseUserRefresh, topUpOpen, openWithdrawalSupport]);
  return (
    <SessionProvider value={ctx}>
      <div className="min-h-screen blox-bg text-white">
        <Header stats={session.stats} user={session.user} topUpOpen={topUpOpen} setTopUpOpen={setTopUpOpen} />
        <div className="flex">
          <LiveDrop drops={session.drops} bestDrop={session.bestDrop} />
          <main className="flex-1 min-w-0">
            <LiveDropStrip drops={session.drops} bestDrop={session.bestDrop} />
            <div className="px-3 py-4 sm:px-4 sm:py-6">
              <Suspense fallback={<PageFallback />}>
                <Outlet />
              </Suspense>
              <footer className="pt-7 pb-2 text-center space-y-2">
                <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs">
                  <Link to="/tos" className="text-[#999999] font-semibold hover:text-white transition-colors" data-testid="footer-tos-link">{t("footer.tos")}</Link>
                  <Link to="/privacy" className="text-[#999999] font-semibold hover:text-white transition-colors" data-testid="footer-privacy-link">{t("footer.privacy")}</Link>
                  <button type="button" onClick={openRubTopUp} className="text-[#999999] font-semibold hover:text-white transition-colors" data-testid="footer-tariffs-link">{t("footer.tariffs")}</button>
                  <button type="button" onClick={() => openLiveChat()} className="text-[#999999] font-semibold hover:text-white transition-colors" data-testid="footer-support-button">{t("footer.support")}</button>
                  <a href={`https://t.me/${SUPPORT_HANDLE.replace("@", "")}`} target="_blank" rel="noopener noreferrer" className="text-[#999999] font-semibold hover:text-white transition-colors" data-testid="footer-telegram-link">{SUPPORT_HANDLE}</a>
                </div>
                <div className="text-[11px] text-[#999999] font-medium" data-testid="footer-registration-location">{t("footer.registration_location")}</div>
              </footer>
            </div>
          </main>
        </div>
      </div>
      <LiveChatWidget />
    </SessionProvider>
  );
};

const Home = () => {
  const { sessionId, setStats, user, setUser, refreshUser, refreshDrops, setTopUpOpen, pauseUserRefresh } = useSessionCtx();
  const [settings, setSettings] = useState(loadSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [target, setTarget] = useState(null);
  const [betSkins, setBetSkins] = useState([]);
  const [spinning, setSpinning] = useState(false);
  useEffect(() => {
    pauseUserRefresh(false);
    return () => pauseUserRefresh(false);
  }, [sessionId, pauseUserRefresh]);
  useEffect(() => { setTarget(null); setBetSkins([]); setSpinning(false); }, [sessionId]);
  useEffect(() => { refreshUser(); }, [refreshUser]);
  const toggleBetSkin = useCallback((sk) => setBetSkins((prev) => (prev[0]?.uid === sk.uid ? [] : [sk])), []);

  const updateSettings = (s) => {
    setSettings(normalizeSettings(s));
    saveSettings(s);
  };

  const handleUpgraded = (res) => {
    setUser((u) => ({ ...u, balance: res.balance }));
    setStats((s) => ({ ...s, upgrades: res.upgrades_total }));
    refreshDrops();
    refreshUser();
    setBetSkins([]);
    if (res.win) setTarget(null);
  };

  return (
    <div className="max-w-[980px] mx-auto">
      <div className="flex h-[5.2rem] w-full items-center justify-center gap-3 px-8 mb-3 sm:mb-5 fade-up" style={{ background: "linear-gradient(90deg, rgba(0,0,0,0) 0%, rgba(0,0,0,.55) 35%, rgba(0,0,0,.55) 65%, rgba(0,0,0,0) 100%)" }} data-testid="page-title">
        <BrandAvatar size={40} testId="page-brand-icon" className="shrink-0 sm:w-[46px] sm:h-[46px]" />
        <h1 className="min-w-0" data-testid="page-brand-title">
          <BrandWordmark className="block text-[28px] sm:text-[34px] leading-none" testId="page-brand-wordmark" />
        </h1>
      </div>
      <UpgradePanel
        key={sessionId}
        sessionId={sessionId}
        user={user}
        settings={settings}
        onSettingsChange={updateSettings}
        onOpenSettings={() => setSettingsOpen(true)}
        onUpgraded={handleUpgraded}
        onSpinningChange={(value) => { setSpinning(value); pauseUserRefresh(value); }}
        target={target}
        onClearTarget={() => setTarget(null)}
        betSkins={betSkins}
        onRemoveBetSkin={(uid) => setBetSkins((prev) => prev.filter((b) => b.uid !== uid))}
      />
      <SkinsSection
        disabled={spinning}
        onTopUp={() => setTopUpOpen(true)}
        user={user}
        target={target}
        onPurchased={(updated) => { setUser(updated); refreshUser(); }}
        onSelectTarget={setTarget}
        betSkins={betSkins}
        onToggleBetSkin={toggleBetSkin}
        sound={settings.sound}
      />
      <SettingsModal open={settingsOpen} onOpenChange={setSettingsOpen} settings={settings} onSave={updateSettings} />
    </div>
  );
};

function App() {
  useEffect(() => {
    const block = (event) => {
      const el = event.target?.nodeType === 1 ? event.target : event.target?.parentElement;
      if (el?.closest('input, textarea, [contenteditable]:not([contenteditable="false"])')) return;
      event.preventDefault();
    };
    document.addEventListener("dragstart", preventGameDrag, true);
    document.addEventListener("selectstart", block, true);
    return () => {
      document.removeEventListener("dragstart", preventGameDrag, true);
      document.removeEventListener("selectstart", block, true);
    };
  }, []);
  return (
    <div className="App">
      <BrowserRouter>
        <LangProvider>
          <AuthProvider>
            <Routes>
              <Route path="/" element={<RootRedirect />} />
              <Route path="/auth/callback" element={<Suspense fallback={<PageFallback />}><AuthCallbackPage /></Suspense>} />
              <Route path="/admin" element={<Suspense fallback={<PageFallback />}><AdminPage /></Suspense>} />
              <Route path="/staff" element={<Suspense fallback={<PageFallback />}><StaffPage /></Suspense>} />
              <Route path="/:lang" element={<LangGate />}>
                <Route element={<Shell />}>
                  <Route index element={<Home />} />
                  <Route path="tos" element={<TosPage />} />
                  <Route path="privacy" element={<PrivacyPage />} />
                  <Route path="profile" element={<ProfilePage />} />
                  <Route path="users/:discordId" element={<PublicProfilePage />} />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Route>
            </Routes>
          </AuthProvider>
        </LangProvider>
      </BrowserRouter>
      <Toaster position="top-center" richColors={false} duration={3800} gap={10} offset={18} />
      <PointerEventsGuard />
    </div>
  );
}

export default App;
