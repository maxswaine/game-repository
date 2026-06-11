# Privacy Policy — What's That Game

**Last updated:** 11 June 2026
**Applies to:** the "What's That Game" mobile app (iOS and Android) and its backend API.

## 1. Who we are

What's That Game ("we", "us", "our") is an independent project run by its founding team. We are **not yet incorporated as a legal entity** — the project is currently operated privately by its founders. If and when we incorporate, this policy will be updated with the company details.

For any privacy question or request, contact us at **whatsthatgameteam@gmail.com**.

The project founders act as joint data controllers for the purposes of the UK GDPR / EU GDPR.

---

## 2. Summary

What's That Game lets you create, store, search and discover party/board games. To do that we store an account for you, the games you contribute, and the games you favourite. We use a small number of third-party providers (Google, OpenAI, Amplitude, Railway) to sign you in, power semantic search and AI text suggestions, measure how the app is used, and host the service. We do **not** sell your personal data.

---

## 3. Data we collect

### 3.1 Account data (you give us this when you register)

| Data | Required? | Why |
|------|-----------|-----|
| First name | Yes | Display, personalisation |
| Last name | Yes | Display, personalisation |
| Username | Yes | Public identity on the platform |
| Email address | Yes | Login, account recovery, service notices |
| Password | Only for email/password sign-up | Authentication — stored only as a **bcrypt hash**, never in plain text |
| Date of birth | Yes | Age-appropriate content (age ratings, adult-content gating) |
| Country of origin | Yes | Personalisation / regional context (stored as a 2-letter ISO code) |
| Avatar image URL | Optional | Profile picture |

We also automatically record an account `role`, an active/inactive flag, and account `created`/`last updated` timestamps.

### 3.2 Google sign-in data (if you choose "Sign in with Google")

If you sign in with Google, we receive from Google — under the `openid email profile` scopes — your:

- Email address (and whether it is verified)
- Google account ID (`sub`)
- First name and last name (`given_name`, `family_name`)
- Profile picture URL

We store these to create and identify your account. We do **not** receive your Google password.

### 3.3 Content you create

- Games you contribute: name, description, objective, setup, rules, type, player counts, duration, difficulty, age rating, equipment, setting, image URL, and public/private visibility.
- Games you favourite or upvote.
- Achievements you earn.
- Reports you submit about other games (the reason text and which game).

Anything you mark **public** is visible to other users. Anything you mark **private** is visible only to you.

### 3.4 Analytics data (Amplitude)

Our app uses **Amplitude** to understand how the app is used (for example: which screens are viewed and key in-app actions/moments). Amplitude may process a device identifier, app/usage events, and technical data such as device type, OS version and approximate location derived from IP. This helps us improve the product. See Amplitude's privacy policy: https://amplitude.com/privacy.

### 3.5 Technical data

When the app calls our backend, our hosting provider processes standard request metadata (IP address, timestamps, user-agent) for security and reliability. Authentication uses a JWT token stored in a secure, HTTP-only cookie and/or sent as a bearer token from the app.

---

## 4. How we use your data (purposes & legal bases)

| Purpose | Legal basis (GDPR) |
|---------|--------------------|
| Create and run your account, authenticate you | Performance of a contract |
| Store and display the games and favourites you create | Performance of a contract |
| Semantic search and AI text suggestions (see §5) | Performance of a contract / legitimate interest |
| Age-appropriate content gating | Legitimate interest / legal obligation |
| Product analytics and improvement (Amplitude) | Consent, where required, otherwise legitimate interest |
| Security, fraud/abuse prevention, debugging | Legitimate interest |
| Service and security communications | Performance of a contract / legitimate interest |

We do not use your data for automated decisions that produce legal effects on you.

---

## 5. AI features and how your content is processed

When you create or edit a game, the game's text is sent to **OpenAI** to:

1. Generate a semantic-search embedding (`text-embedding-3-small`), stored so your game can be found by meaning-based search.
2. Optionally improve a field's wording when you use the AI optimiser (`gpt-4.1-nano`).

Only the game text you submit is sent — not your account credentials. OpenAI processes this as our service provider. See OpenAI's privacy policy: https://openai.com/policies/privacy-policy. We recommend not putting personal or sensitive information into game text fields.

---

## 6. Third parties we share data with

We share data only with providers that help us run the service:

| Provider | Role | What they receive |
|----------|------|-------------------|
| **Google** | Sign-in (OAuth) | Authentication exchange; we receive your basic profile (§3.2) |
| **OpenAI** | Embeddings + AI text suggestions | Game text you submit (§5) |
| **Amplitude** | Product analytics | Usage events and device/technical data (§3.4) |
| **Railway** | Hosting + managed PostgreSQL database | All data needed to run the service, stored at rest |

We do **not** sell your personal data or share it with advertisers.

---

## 7. International transfers

Our backend and database are hosted on **Railway**, and our processors (Google, OpenAI, Amplitude) may process data in **Europe**. Where data leaves the UK/EEA, transfers are protected by appropriate safeguards such as Standard Contractual Clauses.

---

## 8. How long we keep data

- **Active accounts:** account data and content are kept while your account is active.
- **Account deletion — Stage 1 (Day 0):** when you request deletion, your account is deactivated immediately and login is blocked. Your data is not yet deleted.
- **Recovery window (Days 1–30):** you can reactivate your account and restore full access within 30 days of requesting deletion.
- **Account deletion — Stage 2 (Day 30):** after the 30-day window expires, we permanently erase your personal data (name, email, date of birth, country, avatar, authentication credentials). Private games and their associated content are deleted. Public games you contributed are retained anonymously (attributed to "Deleted user") so the platform catalogue remains useful. Comments you posted are retained anonymously. User reports, favourites, and achievements are deleted.
- **Analytics data** is retained according to Amplitude's retention settings.
- **Backups and logs** are kept for a limited period for security and recovery, then deleted.

---

## 9. Your rights and choices

Depending on your location, you have the right to access, correct, delete, restrict, or object to processing of your personal data, and to data portability.

- **Delete your account:** you can request deletion from within the app. Your account is deactivated immediately and permanently erased after 30 days (see §8). You can cancel deletion and reactivate within those 30 days. You can also email us at **whatsthatgameteam@gmail.com** for manual erasure requests.
- **Access / correction:** update your profile in the app, or contact us.
- **Withdraw analytics consent:** where we rely on consent, you can withdraw it at any time via in-app settings / OS-level controls.

To exercise any right, email **whatsthatgameteam@gmail.com**. You also have the right to complain to your data protection authority (in the UK, the ICO: https://ico.org.uk).

---

## 10. Children

What's That Game is not directed at children under **13**. You must be at least 13 to create an account. We do not knowingly collect data from children under that age. If you believe a child has given us data, contact us and we will delete it. Some games are gated as adult content and require an appropriate age.

---

## 11. Security

Passwords are stored only as bcrypt hashes. Authentication uses signed JWT tokens over HTTPS in HTTP-only cookies. Access to production data is restricted. No system is perfectly secure, but we take reasonable technical and organisational measures to protect your data.

---

## 12. Changes to this policy

We may update this policy. We will post the new version with an updated "Last updated" date and, for material changes, notify you in the app.

---

## 13. Contact

**What's That Game** (founding team)
Email: **whatsthatgameteam@gmail.com**
