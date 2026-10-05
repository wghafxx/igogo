import { capturedReferral, clearReferral } from "./referral";
import { discordLoginUrl } from "./api";

beforeEach(() => { localStorage.clear(); window.history.replaceState({}, "", "/"); });

test("keeps the first referral while navigating and includes it in Discord login", () => {
  window.history.replaceState({}, "", "/?ref=0123456789abcdef");
  expect(capturedReferral()).toBe("0123456789abcdef");
  window.history.replaceState({}, "", "/profile");
  expect(discordLoginUrl()).toContain("/auth/discord/login?ref=0123456789abcdef");
  window.history.replaceState({}, "", "/?ref=abcdef0123456789");
  expect(capturedReferral()).toBe("0123456789abcdef");
  window.history.replaceState({}, "", "/auth/callback");
  clearReferral();
  expect(discordLoginUrl()).toMatch(/\/auth\/discord\/login$/);
});

test.each(["invalid", "https://evil.test", "<script>", "a".repeat(1000)])("rejects malformed referral code: %s", (ref) => {
  window.history.replaceState({}, "", `/?ref=${encodeURIComponent(ref)}`);
  expect(capturedReferral()).toBeNull();
  expect(discordLoginUrl()).toMatch(/\/auth\/discord\/login$/);
});
