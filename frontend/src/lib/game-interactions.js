// A drag of selected text suppresses normal mouse input in the browser.
// Cancel it only on game surfaces; text fields keep native editing/dragging.
export const preventGameDrag = (event) => {
  const element = event.target?.nodeType === 1 ? event.target : event.target?.parentElement;
  if (element?.closest('input, textarea, [contenteditable]:not([contenteditable="false"])')) return;
  event.preventDefault();
};