import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, getToken, setToken } from "../lib/api";
import AuthModal from "../components/AuthModal";
import { useLocation } from "react-router-dom";

const AuthContext = createContext(null);

const ERRORS = {
  denied: "Вход через Discord отменён",
  state: "Сессия авторизации устарела, попробуйте ещё раз",
  token: "Discord не подтвердил вход. Попробуйте ещё раз",
  profile: "Не удалось получить профиль Discord",
  unavailable: "Вход через Discord пока недоступен: администратору нужно настроить приложение Discord.",
};

export function AuthProvider({ children }) {
  const location = useLocation();
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
        toast.error("Не удалось проверить сессию. Данные входа сохранены; попробуйте позже.");
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);
  useEffect(() => {
    const err = new URLSearchParams(location.search).get("auth_error");
    if (err) {
      toast.error(ERRORS[err] || "Ошибка авторизации");
      setAuthOpen(true);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [location.search]);

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
      toast.error("Не удалось завершить выход. Проверьте соединение и повторите.");
      return;
    }
    setToken(null);
    setAuthUser(null);
  }, []);

  const openAuth = useCallback(() => setAuthOpen(true), []);

  return (
    <AuthContext.Provider value={{ authUser, setAuthUser, loading, login, logout, refresh, openAuth }}>
      {children}
      <AuthModal open={authOpen} onOpenChange={setAuthOpen} />
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
