export const SUPPORTED_LANGS = ["ru", "en"];
export const LANG_KEY = "bloxgrade_lang";

// Languages whose speakers get the Russian UI (CIS + neighbours).
const RU_LANGS = ["ru", "uk", "be", "kk", "ky", "uz", "tg", "hy", "az", "tk", "mo", "ab", "os"];
// Free, offline, no-limit "geo" hint: browser timezone → CIS region.
const RU_TZ = /^(Europe\/(Moscow|Kaliningrad|Samara|Volgograd|Kirov|Astrakhan|Saratov|Ulyanovsk|Minsk|Kiev|Kyiv|Simferopol|Chisinau|Tiraspol)|Asia\/(Yekaterinburg|Omsk|Novosibirsk|Barnaul|Tomsk|Novokuznetsk|Krasnoyarsk|Irkutsk|Chita|Yakutsk|Khandyga|Vladivostok|Ust-Nera|Magadan|Sakhalin|Srednekolymsk|Kamchatka|Anadyr|Almaty|Qyzylorda|Qostanay|Aqtobe|Aqtau|Atyrau|Oral|Bishkek|Tashkent|Samarkand|Dushanbe|Ashgabat|Yerevan|Baku|Tbilisi))$/;

export const langFromPath = (pathname) => {
  const seg = (pathname || "").split("/")[1];
  return SUPPORTED_LANGS.includes(seg) ? seg : null;
};

export const stripLang = (pathname) => {
  const lang = langFromPath(pathname);
  return lang ? pathname.slice(lang.length + 1) || "/" : pathname;
};

export const withLang = (lang, to) => {
  if (typeof to !== "string" || !to.startsWith("/") || langFromPath(to)) return to;
  const tail = to === "/" ? "" : to.startsWith("/?") ? to.slice(1) : to;
  return `/${lang}${tail}`;
};

export const detectLang = () => {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (SUPPORTED_LANGS.includes(saved)) return saved;
  } catch { /* ignore */ }
  try {
    const langs = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language]).map((l) => (l || "").toLowerCase().split("-")[0]);
    for (const l of langs) {
      if (RU_LANGS.includes(l)) return "ru";
      if (l === "en") return "en";
    }
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    if (RU_TZ.test(tz)) return "ru";
  } catch { /* ignore */ }
  return "en";
};
