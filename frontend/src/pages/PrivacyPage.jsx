import React from "react";
import { Link } from "react-router-dom";
import { useLang } from "../lib/i18n";

const SECTIONS_RU = [
  ["1. Общие положения", ["1.1. Настоящая Политика конфиденциальности (далее — «Политика») регулирует порядок обработки и защиты информации, которую Пользователь передаёт при использовании сервиса BLOXGRADE (далее — «Сервис»).", "1.2. Используя Сервис, Пользователь подтверждает своё согласие с условиями Политики. Если Пользователь не согласен с условиями — он обязан прекратить использование Сервиса."]],
  ["2. Сбор информации", ["2.1. Сервис может собирать следующие типы данных: идентификаторы аккаунта (никнейм, ID Discord и т.п.); техническую информацию (IP-адрес, данные о браузере, устройстве и операционной системе); историю взаимодействий с Сервисом (апгрейды, пополнения, заявки).", "2.2. Сервис не требует от Пользователя предоставления паспортных данных, документов, фотографий или другой личной информации, кроме минимально необходимой для работы."]],
  ["3. Использование информации", ["3.1. Сервис может использовать полученную информацию исключительно для: обеспечения работы функционала; связи с Пользователем (в том числе для уведомлений и поддержки); анализа и улучшения работы Сервиса."]],
  ["4. Передача информации третьим лицам", ["4.1. Администрация не передаёт полученные данные третьим лицам, за исключением случаев: если это требуется по закону; если это необходимо для исполнения обязательств перед Пользователем (например, при работе с платёжными системами); если Пользователь сам дал на это согласие."]],
  ["5. Хранение и защита данных", ["5.1. Данные хранятся в течение срока, необходимого для достижения целей обработки.", "5.2. Администрация принимает разумные меры для защиты данных, но не гарантирует абсолютную безопасность информации при передаче через интернет."]],
  ["6. Отказ от ответственности", ["6.1. Пользователь понимает и соглашается, что передача информации через интернет всегда сопряжена с рисками.", "6.2. Администрация не несёт ответственности за утрату, кражу или раскрытие данных, если это произошло по вине третьих лиц или самого Пользователя."]],
  ["7. Изменения в Политике", ["7.1. Администрация вправе изменять условия Политики без предварительного уведомления.", "7.2. Продолжение использования Сервиса после внесения изменений означает согласие Пользователя с новой редакцией Политики."]],
];

const SECTIONS_EN = [
  ["1. General", ["1.1. This Privacy Policy (the “Policy”) governs how information users provide while using the BLOXGRADE service (the “Service”) is processed and protected.", "1.2. By using the Service the User accepts the Policy. If the User disagrees, they must stop using the Service."]],
  ["2. Information we collect", ["2.1. The Service may collect: account identifiers (nickname, Discord ID, etc.); technical data (IP address, browser, device and OS information); interaction history (upgrades, top-ups, requests).", "2.2. The Service does not require passport data, documents, photos or other personal information beyond what is minimally necessary."]],
  ["3. Use of information", ["3.1. The Service uses the collected information solely to: run the features; contact the User (including notifications and support); analyse and improve the Service."]],
  ["4. Sharing with third parties", ["4.1. The administration does not share collected data with third parties except: when required by law; when necessary to fulfil obligations to the User (e.g. payment systems); with the User's consent."]],
  ["5. Storage and protection", ["5.1. Data is stored for as long as needed for the processing purposes.", "5.2. The administration takes reasonable measures to protect data but cannot guarantee absolute security of information transmitted over the internet."]],
  ["6. Disclaimer", ["6.1. The User understands that transmitting information over the internet always involves risks.", "6.2. The administration is not liable for loss, theft or disclosure of data caused by third parties or the User themselves."]],
  ["7. Changes to the Policy", ["7.1. The administration may change the Policy without prior notice.", "7.2. Continued use of the Service after changes means acceptance of the new version."]],
];

export default function PrivacyPage() {
  const { t, lang } = useLang();
  const sections = lang === "en" ? SECTIONS_EN : SECTIONS_RU;
  return (
    <div className="max-w-[860px] mx-auto" data-testid="privacy-page">
      <div className="fade-up">
        <div className="text-[11px] uppercase tracking-[0.2em] text-[#00a2ff] font-bold">{t("docs.legal")}</div>
        <h1 className="text-[30px] sm:text-[36px] font-black leading-tight mt-2">{t("docs.privacy_title")}</h1>
        <p className="text-[13px] text-[#8e91a3] mt-2">{t("docs.privacy_date")}</p>
      </div>

      <div className="mt-8 space-y-4">
        {sections.map(([title, items], i) => (
          <section key={title} className="blox-panel p-5 fade-up" style={{ animationDelay: `${i * 50}ms` }} data-testid={`privacy-section-${i + 1}`}>
            <h2 className="text-[15px] md:text-[16px] font-bold mb-3">{title}</h2>
            <ul className="space-y-2">
              {items.map((it) => (
                <li key={it} className="text-[13px] text-[#b4b7c7] leading-relaxed">{it}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3 text-[12px] text-[#5f6377]">
        <span>
          BLOXGRADE © 2026 ·{" "}
          <Link to="/tos" className="text-[#00a2ff] hover:underline font-semibold" data-testid="privacy-tos-link">
            {t("docs.tos_title")}
          </Link>
        </span>
        <Link to="/" className="blox-btn-primary h-10 px-5 inline-flex items-center text-[13px]" data-testid="privacy-back-home">
          {t("docs.back")}
        </Link>
      </div>
    </div>
  );
}
