import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { LangProvider } from "../lib/i18n";
import Seo from "./Seo";

let root;
let container;
let navigate;
const content = (name) => document.head.querySelector(`meta[name="${name}"]`)?.content;
const canonical = () => document.head.querySelector('link[rel="canonical"]')?.href;

function Navigation() {
  navigate = useNavigate();
  return <Seo />;
}

beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  document.head.innerHTML = '<meta name="description" content="Default" />';
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter initialEntries={["/ru?ref=example"]}><LangProvider><Navigation /></LangProvider></MemoryRouter>);
  });
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("language navigation updates title, canonical and reciprocal alternate links without duplicates", async () => {
  expect(document.title).toBe("BloxGrade — апгрейд скинов BloxStrike");
  expect(canonical()).toBe("https://bloxgrade.com/ru");
  await act(async () => navigate("/en/privacy/?utm_source=test"));
  expect(document.title).toBe("Privacy Policy — BloxGrade");
  expect(document.documentElement.lang).toBe("en");
  expect(canonical()).toBe("https://bloxgrade.com/en/privacy");
  expect(document.head.querySelectorAll('link[rel="canonical"]')).toHaveLength(1);
  expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1);
  expect(document.head.querySelector('link[hreflang="ru"]').href).toBe("https://bloxgrade.com/ru/privacy");
  expect(document.head.querySelector('link[hreflang="en"]').href).toBe("https://bloxgrade.com/en/privacy");
});

test.each(["/admin", "/staff", "/auth/callback", "/ru/profile", "/en/users/123", "/ru/missing"])(
  "%s is noindex and returning home restores indexable metadata",
  async (path) => {
    await act(async () => navigate(path));
    expect(content("robots")).toBe("noindex, follow");
    expect(canonical()).toBeUndefined();
    expect(document.head.querySelectorAll('link[hreflang]')).toHaveLength(0);
    await act(async () => navigate("/en"));
    expect(content("robots")).toBe("index, follow");
    expect(canonical()).toBe("https://bloxgrade.com/en");
    expect(document.title).toBe("BloxGrade — BloxStrike skin upgrades");
  }
);
