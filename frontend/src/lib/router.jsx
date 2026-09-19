import React from "react";
import { Link as RouterLink, Navigate as RouterNavigate } from "react-router-dom";
import { useLang } from "./i18n";
import { withLang } from "./locale";

// Drop-in replacements that prefix absolute paths with the active /ru or /en segment.
export const Link = React.forwardRef(function Link({ to, ...rest }, ref) {
  const { lang } = useLang();
  return <RouterLink ref={ref} to={withLang(lang, to)} {...rest} />;
});

export const Navigate = ({ to, ...rest }) => {
  const { lang } = useLang();
  return <RouterNavigate to={withLang(lang, to)} {...rest} />;
};

export const useLangHref = () => {
  const { lang } = useLang();
  return (to) => withLang(lang, to);
};
