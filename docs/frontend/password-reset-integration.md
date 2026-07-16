# Password Reset — Frontend Integration

## Overview

Two-step flow: user requests a reset link → receives email → clicks link → enters new password.

The reset link points to `{FRONTEND_URL}/reset-password?token=<token>`. The frontend **must** implement this route.

---

## Step 1 — Forgot Password Form

**Trigger:** user clicks "Forgot password?" on the login screen.

**UI:** simple form with a single email field.

**API call:**

```
POST /auth/forgot-password
Content-Type: application/json

{ "email": "user@example.com" }
```

**Response (always 200):**
```json
{ "message": "If that email is registered, a reset link has been sent." }
```

The response is intentionally vague — don't reveal whether the email exists. Always show the same confirmation message regardless of outcome:

> "If that email is registered, you'll receive a reset link shortly."

**Rate limit:** 3 requests/minute per IP. Show a friendly error if the user hits it.

---

## Step 2 — Reset Password Page

**Route:** `/reset-password?token=<token>`

**UI:** form with two fields — new password + confirm password.

On page load, extract `token` from the query string. If no token present, redirect to `/login`.

**Validation (client-side before submitting):**
- Password minimum length (recommend 8 chars)
- Passwords match
- Basic email typo check on the forgot-password form (e.g. catch `gmial.com`, `hotmal.com`)

**API call:**

```
POST /auth/reset-password
Content-Type: application/json

{
  "token": "<token from query string>",
  "new_password": "newpassword123"
}
```

**Success (200):**
```json
{ "message": "Password reset successfully" }
```

→ Show success message, then redirect to `/login` after 2–3 seconds (or immediately with a toast).

**Note on resubmission:** this endpoint is idempotent for a duplicate submission of the same token/password (e.g. a double-click) — you'll get 200 both times, not an error. No client-side guard needed for that case.

**Note on stale sessions:** on success, the backend clears the `access_token` cookie (web only). Mobile/bearer-token clients must discard any locally stored token themselves and route the user back through login — the old token is revoked server-side and will 401 ("Could not validate credentials") if reused.

**Error (400):**
```json
{ "detail": "Invalid or expired reset token" }
```

→ Show: "This reset link has expired or is invalid. Please request a new one." with a link back to the forgot password form.

**Token expiry:** 15 minutes from when the email was sent.

---

## Flow Diagram

```
Login screen
  └─ "Forgot password?" →  /forgot-password
                              │
                              │  POST /auth/forgot-password
                              ▼
                           "Check your email"
                              │
                              │  User clicks link in email
                              ▼
                         /reset-password?token=...
                              │
                              │  POST /auth/reset-password
                              ▼
                         "Password reset!"  →  /login
```

---

## Mobile App Considerations

The reset link opens in the system browser — this is intentional. Do not attempt to deep-link into the native app for password reset:

- Deep links break when the app is not installed
- Browser-based reset works for all users regardless of platform

After the user resets in the browser, they return to the app and log in normally. If you want to improve the experience, the web reset page can show a "Return to app" button after success that opens a custom URL scheme (e.g. `whatsthatgame://login`), but this is optional.

---

## Environment Variable

The backend constructs the reset URL using `FRONTEND_URL`:

```
FRONTEND_URL=https://whatsthatgame.co.uk
```

Ensure this is set correctly in each environment (dev, staging, production).

---

## Error States Summary

| Scenario | UI response |
|---|---|
| Email not found | Same success message (don't reveal) |
| Rate limited (3/min) | "Too many attempts, please wait a minute" |
| Token expired (>15 min) | "Link expired — request a new one" |
| Token invalid/tampered | "Link invalid — request a new one" |
| Passwords don't match | Client-side validation error |
| Network error | Generic retry message |
