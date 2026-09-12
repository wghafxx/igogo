import React from "react";
import { useLang } from "../lib/i18n";

export const SKINS_PER_PAGE = 15;

export default function SkinPagination({ page, pages, onChange, disabled, label, testId }) {
  const { t } = useLang();
  if (pages <= 1) return null;

  let numbers;
  if (pages <= 7) numbers = Array.from({ length: pages }, (_, i) => i + 1);
  else if (page <= 4) numbers = [1, 2, 3, 4, 5, "…", pages];
  else if (page >= pages - 3) numbers = [1, "…", pages - 4, pages - 3, pages - 2, pages - 1, pages];
  else numbers = [1, "…", page - 1, page, page + 1, "…", pages];

  const buttonClass = "h-8 min-w-7 px-1.5 rounded-md text-[12px] font-bold transition-colors disabled:opacity-40 disabled:cursor-default";
  return (
    <nav aria-label={label} className="flex items-center justify-center gap-1 px-2 py-3 border-t border-[#262833]" data-testid={testId}>
      <button type="button" disabled={disabled || page === 1} onClick={() => onChange(page - 1)} aria-label={t("skins.previous_page")} className={`${buttonClass} text-[#8e91a3] hover:bg-[#262833]`} data-testid={`${testId}-previous`}>‹</button>
      {numbers.map((number, i) => typeof number === "number" ? (
        <button
          key={number}
          type="button"
          disabled={disabled}
          aria-label={`${t("skins.page")} ${number}`}
          aria-current={page === number ? "page" : undefined}
          onClick={() => onChange(number)}
          className={`${buttonClass} ${page === number ? "bg-[#00a2ff] text-white" : "bg-[#0f1015] text-[#8e91a3] hover:bg-[#262833] hover:text-white"}`}
          data-testid={`${testId}-page-${number}`}
        >{number}</button>
      ) : <span key={`ellipsis-${i}`} aria-hidden="true" className="text-[#5f6377] text-[12px]">{number}</span>)}
      <button type="button" disabled={disabled || page === pages} onClick={() => onChange(page + 1)} aria-label={t("skins.next_page")} className={`${buttonClass} text-[#8e91a3] hover:bg-[#262833]`} data-testid={`${testId}-next`}>›</button>
    </nav>
  );
}
