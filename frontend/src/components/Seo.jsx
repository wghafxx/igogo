import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useLang } from "../lib/i18n";
import { langFromPath, stripLang } from "../lib/locale";

const SITE_URL = "https://bloxgrade.com";
const PAGES = {
  "/": {
    ru: ["BloxGrade — апгрейд скинов BloxStrike", "BloxGrade — сервис апгрейда скинов BloxStrike. Каталог предметов, выбор скина для улучшения, инвентарь и история апгрейдов."],
    en: ["BloxGrade — BloxStrike skin upgrades", "BloxGrade is a BloxStrike skin upgrade service. Browse the item catalog, choose a target skin, and view your inventory and upgrade history."],
  },
  "/tos": {
    ru: ["Пользовательское соглашение — BloxGrade", "Условия использования BloxGrade: правила сервиса, апгрейды, внутренняя валюта, права и обязанности пользователей."],
    en: ["Terms of Service — BloxGrade", "BloxGrade terms of service: platform rules, upgrades, virtual currency, and user rights and responsibilities."],
  },
  "/privacy": {
    ru: ["Политика конфиденциальности — BloxGrade", "Какие данные обрабатывает BloxGrade, как они используются и хранятся. Политика конфиденциальности сервиса."],
    en: ["Privacy Policy — BloxGrade", "Learn which data BloxGrade collects, how it is used and stored, and how the service handles user information."],
  },
};

function setMeta(attribute, name, content) {
  let element = document.head.querySelector(`meta[${attribute}="${name}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attribute, name);
    document.head.appendChild(element);
  }
  element.content = content;
}

// The HTML template intentionally has no canonical: each public route has its own URL.
export default function Seo() {
  const { pathname } = useLocation();
  const { lang } = useLang();

  useEffect(() => {
    const path = stripLang(pathname).replace(/\/+$/, "") || "/";
    const localized = Boolean(langFromPath(pathname));
    const page = localized ? PAGES[path] : null;
    const isRoot = pathname === "/";
    const [title, description] = page?.[lang] || (isRoot ? PAGES["/"][lang] : ["BloxGrade", "BloxGrade"]);
    document.title = title;
    setMeta("name", "description", description);
    setMeta("name", "robots", page || isRoot ? "index, follow" : "noindex, follow");
    setMeta("property", "og:title", title);
    setMeta("property", "og:description", description);
    setMeta("property", "og:locale", lang === "en" ? "en_US" : "ru_RU");
    setMeta("name", "twitter:title", title);
    setMeta("name", "twitter:description", description);

    document.head.querySelectorAll('link[data-bloxgrade-seo]').forEach((node) => node.remove());
    document.head.querySelector('meta[property="og:url"]')?.remove();
    if (page) {
      const suffix = path === "/" ? "" : path;
      const canonical = `${SITE_URL}/${lang}${suffix}`;
      const link = document.createElement("link");
      link.rel = "canonical";
      link.href = canonical;
      link.dataset.bloxgradeSeo = "true";
      document.head.appendChild(link);
      setMeta("property", "og:url", canonical);
      for (const language of ["ru", "en"]) {
        const alternate = document.createElement("link");
        alternate.rel = "alternate";
        alternate.hreflang = language;
        alternate.href = `${SITE_URL}/${language}${suffix}`;
        alternate.dataset.bloxgradeSeo = "true";
        document.head.appendChild(alternate);
      }
    }
  }, [pathname, lang]);

  return null;
}
