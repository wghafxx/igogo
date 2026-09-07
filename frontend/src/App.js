import React, { useEffect, useState } from "react";
import "./App.css";
import { BrowserRouter, Routes, Route, Outlet, Link } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import Header from "./components/Header";
import LiveDrop, { LiveDropStrip } from "./components/LiveDrop";
import UpgradePanel from "./components/UpgradePanel";
import SkinsSection from "./components/SkinsSection";
import SettingsModal from "./components/SettingsModal";
import { Logo } from "./components/Logo";
import { useSession, loadSettings, saveSettings, normalizeSettings } from "./hooks/useSession";
import { AuthProvider } from "./hooks/useAuth";
import { SessionProvider, useSessionCtx } from "./hooks/useSessionCtx";
import TosPage from "./pages/TosPage";
import AuthCallbackPage from "./pages/AuthCallbackPage";
import ProfilePage from "./pages/ProfilePage";
import PublicProfilePage from "./pages/PublicProfilePage";
import AdminPage from "./pages/AdminPage";

// Header + live-drop feed shared by every page
const Shell = () => {
  const session = useSession();
  const [topUpOpen, setTopUpOpen] = useState(false);
  return (
    <SessionProvider value={{ ...session, topUpOpen, setTopUpOpen }}>
      <div className="min-h-screen bg-[#0d0e12] text-white">
        <Header stats={session.stats} user={session.user} topUpOpen={topUpOpen} setTopUpOpen={setTopUpOpen} />
        <div className="flex">
          <LiveDrop drops={session.drops} />
          <main className="flex-1 min-w-0">
            <LiveDropStrip drops={session.drops} />
            <div className="px-3 py-4 sm:px-4 sm:py-6">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
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
  const toggleBetSkin = (sk) => setBetSkins((prev) => (prev[0]?.uid === sk.uid ? [] : [sk]));

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
      <div className="flex items-center justify-center gap-2 mb-4 sm:mb-6 fade-up" data-testid="page-title">
        <Logo size={34} className="sm:w-[38px] sm:h-[38px]" />
        <h1 className="text-[24px] sm:text-[30px] font-black uppercase tracking-wide">BLOXGRADE</h1>
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
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route element={<Shell />}>
              <Route path="/" element={<Home />} />
              <Route path="/tos" element={<TosPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/users/:discordId" element={<PublicProfilePage />} />
              <Route path="*" element={<div className="blox-panel max-w-[860px] mx-auto p-8 text-center" data-testid="not-found-page"><h1 className="text-3xl font-bold" data-testid="not-found-title">Страница не найдена</h1><Link to="/" className="inline-block mt-5 text-[#00a2ff]" data-testid="not-found-home">На главную</Link></div>} />
            </Route>
            <Route path="/auth/callback" element={<AuthCallbackPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
      <Toaster theme="dark" position="top-center" richColors />
    </div>
  );
}

export default App;
