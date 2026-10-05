import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { SkinCard } from "./SkinGrid";

let container;
let root;

const ITEM = {
  id: "m4a4-ignition",
  uid: "m4a4-ignition-uid",
  type: "M4A4",
  name: "Ignition",
  price: 1400,
  rarity: "pink",
  image: "m4a4_ignition.png",
};

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => {
    root.unmount();
  });
  container.remove();
  document.body.innerHTML = "";
});

test("renders live-drop style card without legacy rarity dot", async () => {
  await act(async () => {
    root.render(<SkinCard item={ITEM} testId="shop-skin-m4a4" />);
  });

  const card = container.querySelector('[data-testid="shop-skin-m4a4"]');
  expect(card).not.toBeNull();
  expect(card.querySelector(".rarity-dot")).toBeNull();
  expect(card.querySelector(".skin-card-price")).not.toBeNull();
  expect(card.querySelector('[data-testid="skin-card-image-shop-skin-m4a4"]')).not.toBeNull();
  expect(card.querySelector(".skin-card-caption")).not.toBeNull();
});

test("prevents native drag on card and image", async () => {
  const onSelect = jest.fn();
  await act(async () => {
    root.render(<SkinCard item={ITEM} testId="shop-skin-m4a4" onSelect={onSelect} />);
  });

  const card = container.querySelector('[data-testid="shop-skin-m4a4"]');
  const image = container.querySelector('[data-testid="skin-card-image-shop-skin-m4a4"]');

  expect(card.getAttribute("draggable")).toBe("false");
  expect(image.getAttribute("draggable")).toBe("false");

  const dragEvent = new Event("dragstart", { bubbles: true, cancelable: true });
  card.dispatchEvent(dragEvent);
  expect(dragEvent.defaultPrevented).toBe(true);

  await act(async () => {
    card.click();
  });
  expect(onSelect).toHaveBeenCalledTimes(1);
});
