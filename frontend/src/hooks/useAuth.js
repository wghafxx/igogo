import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, getToken, setToken } from "../lib/api";
import { useLang } from "../lib/i18n";
import AuthModal from "../components/AuthModal";
import { useLocation } from "react-router-dom";

const AuthContext = createContext(null);

const ERRORS = {
  denied: "auth.err_denied",
  state: "auth.err_state",
  token: "auth.err_token",
  profile: "auth.err_profile",
  unavailable: "auth.err_unavailable",
};

export function AuthProvider({ children }) {
  const location = useLocation();
  const { t } = useLang();
  const [authUser, setAuthUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [authOpen, setAuthOpen] = useState(false);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setAuthUser(null);
      setLoading(false);
      return null;
    }
    try {
      const u = await api.me();
      if (getToken() !== token) return null;
      setAuthUser(u);
      return u;
    } catch (error) {
      if (getToken() !== token) return null;
      if ([401, 403].includes(error?.response?.status)) {
        setToken(null);
        setAuthUser(null);
      } else {
        toast.error(t("auth.err_session"));
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    refresh();
  }, [refresh]);
  useEffect(() => {
    const err = new URLSearchParams(location.search).get("auth_error");
    if (err) {
      toast.error(t(ERRORS[err] || "auth.err_token"));
      setAuthOpen(true);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [location.search, t]);

  const login = useCallback(
    async (token) => {
      setToken(token);
      return refresh();
    },
    [refresh]
  );

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      toast.error(t("auth.err_logout"));
      return;
    }
    setToken(null);
    setAuthUser(null);
  }, [t]);

  const openAuth = useCallback(() => setAuthOpen(true), []);

  return (
    <AuthContext.Provider value={{ authUser, setAuthUser, loading, login, logout, refresh, openAuth }}>
      {children}
      <AuthModal open={authOpen} onOpenChange={setAuthOpen} />
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
