# Authentication regression checks

Preserve the existing Discord + JWT and ten-word admin authentication; no email/password migration.
Check Mongo user session_id and admin jti unique indexes; OAuth created_at and admin expires_at TTL indexes.
Use /app/memory/test_credentials.md for admin login. Login through /api/admin/login, verify /api/admin/session with the same User-Agent, then logout and confirm rejection.
Admin phrase has been replaced by the owner's ten-word phrase (see ignored credentials file). Its length exceeds 72 bytes: bcrypt hashes a SHA256 hex digest with a `sha256$` version prefix. Changing the LAST word must fail authentication. Legacy test admin tokens/phrase must not work after rotation. Do not log the phrase or hardcode it in test files.
Create isolated test users via Mongo only; sign JWT using the env secret, never add a bypass API. Test /api/auth/me using Bearer and bg_token cookie; logout must delete bg_token using its original attributes. Invalid roles and expired tokens must be rejected.
Verify OAuth state is browser-bound, one-use and explicitly younger than ten minutes. Missing provider config must not break public routes. Owner has now provided and confirmed credentials in backend/.env. Verify redirect and provider configuration; actual Discord consent remains unverified without owner's interactive Discord session. Do not log credentials or exchange tokens into report artifacts.
Verify frontend does not discard a valid token on network/5xx errors. Normalize FastAPI array validation messages before rendering.