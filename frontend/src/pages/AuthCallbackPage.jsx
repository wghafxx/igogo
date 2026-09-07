import React, { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Logo } from "../components/Logo";
import { useAuth } from "../hooks/useAuth";

export default function AuthCallbackPage() {
  const { login } = useAuth();
  const location = useLocation();
  const [done, setDone] = useState(null);

  useEffect(() => {
    const hash = new URLSearchParams(location.hash.replace(/^#/, ""));
    const token = hash.get("token");
    if (!token) {
      setDone("fail");
      return;
    }
    login(token).then((u) => setDone(u ? "ok" : "fail"));
  }, [location.hash, login]);

  if (done === "ok") return <Navigate to="/" replace />;
  if (done === "fail") return <Navigate to="/?auth_error=token" replace />;

  return (
    <div className="min-h-screen bg-[#0d0e12] text-white flex flex-col items-center justify-center gap-4" data-testid="auth-callback-page">
      <Logo size={56} className="animate-pulse" />
      <div className="text-[14px] text-[#8e91a3]">Входим через Discord...</div>
    </div>
  );
}
