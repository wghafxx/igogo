import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { adminStaffApi, errText } from "../../lib/staff-api";
import ReviewQueue from "./staff/ReviewQueue";
import StaffList from "./staff/StaffList";
import StaffDetail from "./staff/StaffDetail";
import StaffTelegramCard from "./staff/StaffTelegramCard";

export default function StaffTab({ refreshKey }) {
  const [view, setView] = useState("review");
  const [reviews, setReviews] = useState(null);
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(null);
  const load = useCallback(() => Promise.all([
    adminStaffApi.reviews().then(setReviews),
    adminStaffApi.list().then(setRows),
  ]).catch((e) => toast.error(errText(e, "Не удалось загрузить"))), []);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load, refreshKey]);
  const staff = rows.find((s) => s.id === selected);
  const pending = reviews ? reviews.reports.length + reviews.moves.length : 0;
  return (
    <div className="space-y-4" data-testid="admin-staff-tab">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 rounded-lg bg-[#0f1015] p-1">
          {[["review", `Проверка${pending ? ` · ${pending}` : ""}`], ["people", "Сотрудники и учёт"]].map(([k, l]) => (
            <button key={k} onClick={() => setView(k)} className={`h-8 px-3 rounded-md text-[12px] font-bold ${view === k ? "bg-white/[0.12] text-white" : "text-[#8e91a3] hover:text-white"}`} data-testid={`admin-staff-view-${k}`}>{l}</button>
          ))}
        </div>
        <StaffTelegramCard />
      </div>
      {view === "review" && <ReviewQueue data={reviews} onChanged={load} />}
      {view === "people" && (
        <div className="grid xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] gap-4">
          <StaffList rows={rows} selected={selected} onSelect={setSelected} onChanged={load} />
          {staff ? <StaffDetail key={staff.id} staff={staff} onChanged={load} /> : <div className="blox-panel h-40 flex items-center justify-center text-[13px] text-[#6b6f84]">Выберите сотрудника для статистики</div>}
        </div>
      )}
    </div>
  );
}
