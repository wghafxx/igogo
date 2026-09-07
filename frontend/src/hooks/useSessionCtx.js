import { createContext, useContext } from "react";

const SessionCtx = createContext(null);
export const SessionProvider = SessionCtx.Provider;
export const useSessionCtx = () => useContext(SessionCtx);
