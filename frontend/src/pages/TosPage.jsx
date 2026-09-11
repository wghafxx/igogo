import React from "react";
import { Link } from "react-router-dom";
import { SUPPORT_HANDLE } from "../components/SupportDialog";
import { useLang } from "../lib/i18n";

const SUPPORT_URL = process.env.REACT_APP_TELEGRAM_SUPPORT_URL || "https://t.me/bloxgradesupport";

const RU = [
  ["1. Общие положения", [
    "1.1. Настоящее Пользовательское соглашение (далее — «Соглашение») регулирует отношения между администрацией сайта BLOXGRADE (далее — «Сервис») и пользователем сети Интернет (далее — «Пользователь»).",
    "1.2. Используя Сервис, Пользователь подтверждает, что ознакомился с условиями Соглашения, принимает их в полном объёме и обязуется соблюдать.",
    "1.3. Если Пользователь не согласен с условиями Соглашения, он обязан прекратить использование Сервиса.",
    "1.4. Администрация вправе изменять Соглашение без предварительного уведомления. Новая редакция вступает в силу с момента публикации на сайте.",
  ]],
  ["2. Регистрация и аккаунт", [
    "2.1. Авторизация на Сервисе осуществляется через аккаунт Discord. Пользователь несёт полную ответственность за безопасность своего аккаунта Discord.",
    "2.2. Использовать Сервис могут только лица, достигшие 18 лет, либо возраста совершеннолетия согласно законодательству страны проживания Пользователя.",
    "2.3. Запрещается создавать несколько аккаунтов с целью получения преимуществ, обхода ограничений или злоупотребления бонусами.",
    "2.4. Администрация вправе заблокировать аккаунт Пользователя при нарушении условий Соглашения без возврата средств и предметов.",
  ]],
  ["3. Апгрейды и трейды", [
    "3.1. Сервис предоставляет возможность обмена (апгрейда) виртуальных предметов (скинов) на другие виртуальные предметы с заданной вероятностью успеха.",
    "3.2. Шанс успешного апгрейда отображается перед его совершением. Результат определяется случайным образом и не может быть изменён после запуска.",
    "3.3. При неуспешном апгрейде использованные предметы и/или баланс не возвращаются Пользователю, за исключением кешбэка 1 RAP на баланс при ставке от 10 RAP (если позволяет пул выплат). Это является неотъемлемой частью механики Сервиса.",
    "3.4. Пользователь осознаёт, что виртуальные предметы не имеют реальной денежной стоимости за пределами Сервиса, если иное не указано отдельно.",
    "3.5. Пополнение баланса — только скинами через трейд в Roblox. Сначала добавьте нас в друзья, потом отправьте скины трейдом и оставьте заявку на сайте.",
    "3.6. Простыми словами про цену: сколько стоит ваш скин — решает администратор сайта, когда проверяет трейд. Из этой цены вычитается 20%. Пример: скин оценили в 100 RAP → на баланс приходит 80 RAP. Это не «комиссия сверху», а именно минус 20% от цены.",
    "3.7. Принимаются скины от 35 RAP. Скины дешевле 35 RAP не зачисляются на баланс и не возвращаются — вы можете потерять такой скин. Будьте внимательны.",
    "3.8. Промокод даёт бонус к сумме зачисления (например +10%). Бонус считается от суммы после вычета 20%.",
    "3.9. После подтверждения депозита рассчитанная сумма распределяется на покупку до пяти разных предметов из каталога Сервиса. Подбор стремится к близким долям, но зависит от доступных цен. Неиспользованный остаток зачисляется на баланс. Если суммы недостаточно для одного предмета, она зачисляется на баланс целиком. Стоимость выданных предметов вместе с остатком не превышает сумму после комиссии и промокода.",
  ]],
  ["4. Редкость предметов", [
    "4.1. Каждому предмету на Сервисе присвоен уровень редкости: Stock, Blue, Purple, Pink, Red, Gold, Special, Forbidden.",
    "4.2. Редкость определяет визуальное оформление предмета и не гарантирует его стоимость или востребованность.",
    "4.3. Администрация вправе изменять уровень редкости и оценочную стоимость предметов в любое время.",
  ]],
  ["5. Ограничения и запреты", [
    "5.1. Запрещается использование ботов, скриптов, эксплойтов и любых средств автоматизации при работе с Сервисом.",
    "5.2. Запрещается вмешательство в работу Сервиса, попытки получения несанкционированного доступа к данным других Пользователей.",
    "5.3. Запрещается использовать Сервис для отмывания средств, мошенничества и иной противоправной деятельности.",
    "5.4. При обнаружении нарушений Администрация вправе аннулировать результаты апгрейдов, заблокировать аккаунт и удержать предметы.",
  ]],
  ["6. Ответственность", [
    "6.1. Сервис предоставляется «как есть». Администрация не гарантирует бесперебойную работу Сервиса и не несёт ответственности за возможные убытки Пользователя.",
    "6.2. Администрация не несёт ответственности за действия третьих лиц, включая платформу Discord и игровые платформы, на которых используются предметы.",
    "6.3. Пользователь самостоятельно несёт ответственность за соблюдение законодательства своей страны при использовании Сервиса.",
  ]],
  ["7. Персональные данные", [
    "7.1. При авторизации через Discord Сервис получает идентификатор, имя пользователя и аватар. Иные данные не запрашиваются.",
    "7.2. Порядок обработки данных описан в Политике конфиденциальности (/privacy).",
  ]],
  ["8. Оплата в рублях и возвраты", [
    "8.1. Пополнение баланса рублями производится через СБП по тарифу 1 RAP = 0,50 ₽. Актуальные пакеты и цены указаны в разделе пополнения на сайте.",
    "8.2. Минимальный рублёвый платёж — 35 ₽ (70 RAP). Оплата производится на условиях, указанных в Сервисе до момента оплаты.",
    "8.3. В связи с нематериальным характером цифровых товаров возврат денежных средств после зачисления не осуществляется, за исключением случаев, когда услуга не была оказана по технической вине Сервиса.",
    "8.4. Для рассмотрения вопроса о возврате Пользователь обязан обратиться в службу поддержки в течение 24 часов с момента оплаты. Решение принимается Администрацией индивидуально.",
    "8.5. Пользователь обязуется не инициировать возврат платежа (chargeback) через платёжные системы без предварительного обращения в службу поддержки Сервиса.",
  ]],
  ["9. Поддержка и контакты", [
    "9.1. По вопросам работы Сервиса Пользователь может обратиться в службу поддержки: личные сообщения в Telegram либо кнопка «Поддержка» внизу сайта (диалог тикетов).",
    "9.2. Споры разрешаются путём переговоров. Претензии рассматриваются в течение 14 рабочих дней с момента получения.",
  ]],
];

const EN = [
  ["1. General", [
    "1.1. These Terms of Service (the “Terms”) govern the relationship between the administration of the BLOXGRADE website (the “Service”) and an internet user (the “User”).",
    "1.2. By using the Service the User confirms they have read the Terms, accept them in full and agree to comply.",
    "1.3. If the User disagrees with the Terms, they must stop using the Service.",
    "1.4. The administration may change the Terms without prior notice. The new version takes effect once published on the website.",
  ]],
  ["2. Registration and account", [
    "2.1. Authorization on the Service is done via a Discord account. The User is fully responsible for the security of their Discord account.",
    "2.2. Only persons who are 18+ or of legal age under the law of their country of residence may use the Service.",
    "2.3. Creating multiple accounts to gain advantages, bypass restrictions or abuse bonuses is prohibited.",
    "2.4. The administration may block a User's account for violating the Terms without returning funds or items.",
  ]],
  ["3. Upgrades and trades", [
    "3.1. The Service provides exchanges (upgrades) of virtual items (skins) for other virtual items with a set success probability.",
    "3.2. The upgrade chance is shown before it starts. The outcome is random and cannot be changed after the spin.",
    "3.3. On a failed upgrade the used items and/or balance are not returned, except for a 1 RAP cashback to balance for bets of 10+ RAP (if the payout pool allows). This is an integral part of the Service mechanics.",
    "3.4. The User understands that virtual items have no real monetary value outside the Service unless stated otherwise.",
    "3.5. Balance top-ups are only via Roblox skin trades. Add us as a friend first, then send skins by trade and submit a request on the website.",
    "3.6. Pricing in plain words: the site administrator decides your skin's value when reviewing the trade. 20% is deducted from that price. Example: a skin valued at 100 RAP → 80 RAP goes to your balance. This is not a “fee on top”, it's minus 20% of the price.",
    "3.7. Skins of 35 RAP and up are accepted. Cheaper skins are not credited and not returned — you may lose such a skin. Be careful.",
    "3.8. A promo code gives a bonus to the credited amount (e.g. +10%). The bonus is calculated after the 20% deduction.",
    "3.9. After a deposit is confirmed the calculated amount is spent on up to five different items from the Service catalog. Matching aims for close shares but depends on available prices. The unused remainder goes to balance. If the amount is not enough for a single item, it goes to balance in full. The value of issued items plus the remainder never exceeds the amount after fee and promo.",
  ]],
  ["4. Item rarity", [
    "4.1. Every item on the Service has a rarity level: Stock, Blue, Purple, Pink, Red, Gold, Special, Forbidden.",
    "4.2. Rarity defines the item's visual styling and does not guarantee its value or demand.",
    "4.3. The administration may change rarity levels and item valuations at any time.",
  ]],
  ["5. Restrictions", [
    "5.1. Bots, scripts, exploits and any automation when using the Service are prohibited.",
    "5.2. Interfering with the Service or attempting to gain unauthorized access to other Users' data is prohibited.",
    "5.3. Using the Service for money laundering, fraud or other unlawful activity is prohibited.",
    "5.4. Upon detecting violations the administration may void upgrade results, block the account and withhold items.",
  ]],
  ["6. Liability", [
    "6.1. The Service is provided “as is”. The administration does not guarantee uninterrupted operation and is not liable for the User's possible losses.",
    "6.2. The administration is not liable for third-party actions, including the Discord platform and gaming platforms where items are used.",
    "6.3. The User is solely responsible for complying with the laws of their country when using the Service.",
  ]],
  ["7. Personal data", [
    "7.1. When logging in via Discord the Service receives an identifier, username and avatar. No other data is requested.",
    "7.2. Data processing is described in the Privacy Policy (/privacy).",
  ]],
  ["8. Ruble payments and refunds", [
    "8.1. Balance top-ups in rubles are processed via SBP at 1 RAP = ₽0.50. Current packages and prices are shown in the top-up section of the website.",
    "8.2. The minimum ruble payment is ₽35 (70 RAP). Payment is made under the terms shown in the Service before payment.",
    "8.3. Due to the intangible nature of digital goods, refunds are not issued after crediting, except when the service was not provided due to a technical fault of the Service.",
    "8.4. To request a refund the User must contact support within 24 hours of payment. The decision is made by the administration individually.",
    "8.5. The User agrees not to initiate a chargeback through payment systems without contacting the Service support first.",
  ]],
  ["9. Support and contacts", [
    "9.1. For questions about the Service, contact support: Telegram DMs or the “Support” button at the bottom of the website (ticket dialog).",
    "9.2. Disputes are resolved by negotiation. Claims are reviewed within 14 business days of receipt.",
  ]],
];

export default function TosPage() {
  const { t, lang } = useLang();
  const sections = lang === "en" ? EN : RU;
  return (
    <div className="max-w-[860px] mx-auto" data-testid="tos-page">
        <div className="fade-up">
          <div className="text-[11px] uppercase tracking-[0.2em] text-[#00a2ff] font-bold">{t("docs.legal")}</div>
          <h1 className="text-[30px] sm:text-[36px] font-black leading-tight mt-2">{t("docs.tos_title")}</h1>
          <p className="text-[13px] text-[#8e91a3] mt-2">{t("docs.tos_date")}</p>
        </div>

        <div className="mt-8 space-y-4">
          {sections.map(([title, items], i) => (
            <section key={title} className="blox-panel p-5 fade-up" style={{ animationDelay: `${i * 50}ms` }} data-testid={`tos-section-${i + 1}`}>
              <h2 className="text-[15px] md:text-[16px] font-bold mb-3">{title}</h2>
              <ul className="space-y-2">
                {items.map((it) => (
                  <li key={it} className="text-[13px] text-[#b4b7c7] leading-relaxed">
                    {it}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>

        <div className="mt-8 flex flex-wrap items-center justify-between gap-3 text-[12px] text-[#5f6377]">
          <span>
            BLOXGRADE © 2026 · {t("footer.support")}:{" "}
            <a href={SUPPORT_URL} target="_blank" rel="noopener noreferrer" className="text-[#00a2ff] hover:underline font-semibold" data-testid="tos-telegram-link">
              {SUPPORT_HANDLE || "Telegram"}
            </a>
            {" "}·{" "}
            <Link to="/privacy" className="text-[#00a2ff] hover:underline font-semibold" data-testid="tos-privacy-link">
              {t("docs.privacy_title")}
            </Link>
          </span>
          <Link to="/" className="blox-btn-primary h-10 px-5 inline-flex items-center text-[13px]" data-testid="tos-accept-go-login">
            {t("docs.back")}
          </Link>
        </div>
    </div>
  );
}
