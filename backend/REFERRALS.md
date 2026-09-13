# Referral rewards

No new Railway variables are required. Links use `PUBLIC_APP_URL`.

- A signed-in player gets a permanent link in Profile → Referrals.
- The first referral link is saved in the browser and sent to Discord login. The
  server resolves the opaque code and stores its owner in the one-use OAuth state.
- Attribution is written only when the Discord account is created (`$setOnInsert`).
  Existing accounts cannot acquire or replace an inviter. Self-referrals are ignored.
- The inviter receives 25 RAP once the invited player's completed wagers reach
  100 RAP, counting balance plus server-valued skins, regardless of the game result.
- Each verified skin or xRocket deposit pays 3.5% of its gross RAP before site fees
  and promo bonuses. It starts with the first deposit and never expires. For
  xRocket, 35 RUB = 70 RAP, so the inviter earns 2.45 RAP.
- Credits are paid from the site's existing funds: user liabilities increase;
  no fictitious deposit is added to the bank. Amounts are rounded to 0.01 RAP.

`referral_rewards` stores an immutable reward per qualifying account or deposit.
The inviter's balance and `referral_receipts` deduplication marker are updated
atomically. An interrupted request cannot pay the same reward twice. Persistent
source-event flags and a 30-second reconciliation loop recover missed credits.
Referral failures do not block the invited player's deposit or game response.

Indexes are created at startup. Existing accounts, deposits and games are not
retroactively attributed. The profile lists the latest 100 invited accounts;
totals include all invited accounts and credited rewards.

Isolated checks: `python -m pytest tests/test_referrals.py tests/test_xrocket.py -q`
