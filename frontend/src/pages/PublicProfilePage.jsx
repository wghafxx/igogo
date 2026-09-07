import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Logo, RobuxIcon } from "../components/Logo";
import Nick from "../components/Nick";
import { SkinCard } from "../components/SkinsSection";
import { SparklesIcon } from "../components/icons/sparkles";
import { SendIcon } from "../components/icons/send";
import { BoxesIcon } from "../components/icons/boxes";
import { LinkIcon } from "../components/icons/link";
import { api, formatMoney } from "../lib/api";
import { rarityColor } from "../lib/rarity";

const Stat = ({ title, icon: Icon, children, testId }) => (
  <div className="blox-panel p-4 flex flex-col gap-2" data-testid={testId}>
    <div className="flex items-center justify-between text-[13px] text-[#8e91a3]">
      {title}
      <span className="w-7 h-7 rounded-md bg-[#0f1015] flex items-center justify-center text-[#ffb000]">
        <Icon size={14} />
      </span>
    </div>
    {children}
  </div>
);

export default function PublicProfilePage() {
  const { discordId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    api.publicProfile(discordId).then((value) => { if (alive) setData(value); }).catch((e) => { if (alive) setError(e?.response?.data?.detail || "Не удалось загрузить профиль"); });
    return () => { alive = false; };
  }, [discordId]);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success("Ссылка скопирована");
    } catch { toast.error("Не удалось скопировать ссылку. Скопируйте адрес из строки браузера."); }
  };

  if (error)
    return (
      <div className="max-w-[1000px] mx-auto blox-panel p-10 text-center" data-testid="public-profile-error">
        <div className="font-bold text-[18px]">{error}</div>
        <Link to="/" className="inline-block mt-4 text-[#00a2ff] text-[13px] font-bold" data-testid="public-profile-home-link">На главную</Link>
      </div>
    );
  if (!data) return <div className="max-w-[1000px] mx-auto blox-panel h-[220px] animate-pulse" data-testid="public-profile-loading" />;

  const s = data.stats;
  return (
    <div className="max-w-[1000px] mx-auto space-y-4" data-testid="public-profile-page">
      <div className="blox-panel p-3 grid grid-cols-1 md:grid-cols-[320px_1fr] gap-3 fade-up">
        <div className="rounded-xl bg-[#0f1015] p-4 flex flex-col gap-3">
          <div className="flex items-center gap-4">
            <img src={data.avatar || "https://cdn.discordapp.com/embed/avatars/0.png"} alt="" className={`w-16 h-16 rounded-lg object-cover ${data.gold_nick ? "ring-2 ring-[#ffb000]" : ""}`} data-testid="public-profile-avatar" />
            <div className="min-w-0">
              <Nick gold={data.gold_nick} className="font-bold text-[17px] truncate block" testId="public-profile-nickname">{data.nickname}</Nick>
              <div className="mt-1 inline-flex items-center text-[11px] text-[#8e91a3] bg-[#1c1d25] rounded px-2 py-0.5" data-testid="public-profile-id">ID {data.discord_id}</div>
            </div>
          </div>
          <button onClick={copyLink} className="h-9 rounded-lg bg-[#1c1d25] hover:bg-[#22242e] text-[12px] font-bold text-[#c9ccd8] flex items-center justify-center gap-2 transition-colors" data-testid="public-profile-copy-link">
            <LinkIcon size={13} /> Скопировать ссылку на профиль
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat title="Апгрейдов" icon={Logo} testId="public-profile-upgrades">
            <div className="text-[22px] font-black leading-none">{s.upgrades}</div>
            <div className="text-[11px] text-[#8e91a3]">побед: {s.wins}</div>
          </Stat>
          <Stat title="Инвентарь" icon={BoxesIcon} testId="public-profile-inventory">
            <div className="text-[12px] text-[#8e91a3]">{s.inventory_count} предметов</div>
            <div className="font-bold flex items-center gap-1">{formatMoney(s.inventory_value)} <RobuxIcon size={11} /></div>
          </Stat>
          <Stat title="Выведено" icon={SendIcon} testId="public-profile-withdrawn">
            <div className="text-[12px] text-[#8e91a3]">{s.withdrawn_count} предметов</div>
            <div className="font-bold flex items-center gap-1">{formatMoney(s.withdrawn_sum)} <RobuxIcon size={11} /></div>
          </Stat>
          <Stat title="Лучший дроп" icon={SparklesIcon} testId="public-profile-best-drop">
            {data.best_drop ? (
              <div className="flex items-center gap-2" style={{ "--rarity": rarityColor(data.best_drop.item_rarity) }}>
                <img src={data.best_drop.item_image} alt="" className="w-10 h-10 object-contain" />
                <div className="min-w-0">
                  <div className="font-bold text-[12px] truncate">{data.best_drop.item_name}</div>
                  <div className="text-[11px] font-bold text-[#ffb000] flex items-center gap-1">{formatMoney(data.best_drop.item_price)} <RobuxIcon size={9} /></div>
                </div>
              </div>
            ) : (
              <div className="text-[12px] text-[#5f6377]">Пока нет</div>
            )}
          </Stat>
        </div>
      </div>

      <div className="blox-panel fade-up" style={{ animationDelay: "80ms" }}>
        <div className="px-3 py-2.5 border-b border-[#15161b] font-bold text-[13px] flex items-center gap-2">
          <SparklesIcon size={14} className="text-[#ffb000]" /> Последние выигрыши
        </div>
        <div className="p-3 min-h-[160px]">
          {data.drops.length ? (
            <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-8 gap-2" data-testid="public-profile-drops">
              {data.drops.map((d) => (
                <SkinCard key={d.id} item={{ id: d.id, name: d.item_name, type: d.item_type, price: d.item_price, image: d.item_image, rarity: d.item_rarity }} />
              ))}
            </div>
          ) : (
            <div className="h-[140px] flex items-center justify-center text-[13px] text-[#5f6377]" data-testid="public-profile-drops-empty">Выигрышей пока нет</div>
          )}
        </div>
      </div>
    </div>
  );
}
