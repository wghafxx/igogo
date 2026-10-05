// Single contract for cross-component window events: name + payload live here only.
export const EVENTS = {
  openLiveChat: "open-live-chat",
  openRubTopUp: "open-rub-topup",
  openCryptoTopUp: "open-crypto-topup",
  notificationsChanged: "bloxgrade:notifications-changed",
};

export const openLiveChat = (chatId) => window.dispatchEvent(new CustomEvent(EVENTS.openLiveChat, { detail: { chatId: chatId || null } }));
export const openRubTopUp = () => window.dispatchEvent(new CustomEvent(EVENTS.openRubTopUp));
export const openCryptoTopUp = () => window.dispatchEvent(new CustomEvent(EVENTS.openCryptoTopUp));
export const notifyNotificationsChanged = () => window.dispatchEvent(new Event(EVENTS.notificationsChanged));

export const onEvent = (name, handler) => {
  window.addEventListener(name, handler);
  return () => window.removeEventListener(name, handler);
};
