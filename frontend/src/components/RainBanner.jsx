import React, { useEffect, useState } from "react";
import { api, formatMoney } from "../lib/api";

// Полоска над апгрейдом: видна только пока раздача активна.
// Ошибки сети молча прячем — баннер никогда не должен ломать страницу.
export default function RainBanner() {
  const [st, setSt] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => api.rainStatus().then((v) => { if (alive) setSt(v); }).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  if (!st?.active) return null;
  const max = st.amounts?.length ? Math.max(...st.amounts.map(Number)) : 0;
  return (
    <div className="mb-2 rounded-lg border border-[#00a2ff]/40 bg-[#00a2ff]/10 px-3 py-2 text-[12px] leading-snug text-[#b4d9ff]" data-testid="rain-banner">
      🌧 Дождь активен: осталось кусков <b>{st.remaining}</b>
      {max > 0 && <> · макс <b>{formatMoney(max)}</b></>}
      {" "}· крути от <b>{formatMoney(st.min_bet ?? 20)}</b>, проигрыш может превратиться в добивку. Один акк — один кусок.
    </div>
  );
}
