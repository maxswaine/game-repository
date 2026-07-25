# AI + Photo Storage Cost Analysis

**Date:** 2026-07-16
**Scope:** Per-game cost of existing OpenAI features (optimiser, embeddings), the planned
"brain dump" field-splitting feature, and the planned R2 photo storage system
(see [`docs/superpowers/specs/2026-07-16-photo-upload-system-design.md`](superpowers/specs/2026-07-16-photo-upload-system-design.md)),
plus platform running costs (hosting, analytics, email, domain).

## Context for the finance report

**What the app is:** *What's That Game* is a platform for storing and discovering games
— users create game entries (name, rules, setup, photos), browse and search a public
catalogue, upvote, favourite, and optimise their submissions with AI. Backend is a
FastAPI REST API; there is a companion frontend (web + mobile). Two catalogue types
exist: user-contributed games and verified games.

**Stage — pre-launch.** The app **has not launched yet**. There is no live user base and
no production traffic history. Therefore:

- **All user counts, event volumes, and game-creation rates in this document are
  assumptions/projections, not measured data.** They exist to model cost *at hypothetical
  scale*, not to report actual spend.
- Current real spend is effectively **only the fixed platform baseline** (Railway
  hosting + domain), with everything else at $0 free tier. See "Combined monthly
  run-rate → Early stage" for the closest thing to a today figure.
- Costs should be read as **step functions**, not linear: most services (Amplitude,
  Resend, R2, OpenAI) sit at $0 on free tiers and only begin charging once specific
  thresholds are crossed (e.g. Amplitude at ~2M events/month). The report should focus
  on **where those thresholds are** and **what MAU/traffic triggers each step**.

**How to use this doc (guidance for the finance agent):**

- Separate **fixed platform costs** (scale with traffic/load) from **per-unit costs**
  (scale with games created). Do not multiply fixed costs by game count.
- Treat the events-per-user (~160/month) and Railway compute figures as the two softest
  assumptions — flag any projection that hinges on them.
- For a launch budget, the **Early-stage row (~$9/month)** is the realistic starting
  burn; the higher rows are contingency planning for adoption that has not happened yet.
- No revenue model is included here — this is a **cost/burn-rate** analysis only.

## Pricing used (as of July 2026)

| Service | Rate | Source |
|---|---|--[ai-photo-cost-analysis.md](ai-photo-cost-analysis.md)-|
| GPT-4.1-nano input | $0.10 / 1M tokens | [OpenAI Pricing](https://developers.openai.com/api/docs/pricing) |
| GPT-4.1-nano output | $0.40 / 1M tokens | [OpenAI Pricing](https://developers.openai.com/api/docs/pricing) |
| text-embedding-3-small | $0.02 / 1M tokens (input only) | [Embedding pricing 2026](https://embeddingcost.com/openai) |
| R2 storage | $0.015 / GB-month | [Cloudflare R2 Pricing](https://developers.cloudflare.com/r2/pricing) |
| R2 Class A ops (writes/uploads) | $4.50 / 1M ops | [Cloudflare R2 Pricing](https://developers.cloudflare.com/r2/pricing) |
| R2 Class B ops (reads/retrievals) | $0.36 / 1M ops | [Cloudflare R2 Pricing](https://developers.cloudflare.com/r2/pricing) |
| R2 egress | $0 (no egress fees) | [Cloudflare R2 Pricing](https://developers.cloudflare.com/r2/pricing) |
| R2 free tier | 10GB storage, 1M Class A ops, 10M Class B ops / month | [Cloudflare R2 Pricing](https://developers.cloudflare.com/r2/pricing) |

**Note on transcription:** brain-dump speech input uses the phone's native
speech-to-text (client-side, free). No server-side transcription (Whisper /
GPT-4o-transcribe) cost applies — the backend only ever receives text.

## Assumptions

- Optimiser system prompts averaged from the four templates in `src/utils/prompts.py`
  (description/objective/setup/rules): ~220 tokens/call average.
- Average user-submitted field text: ~200 tokens in, ~150 tokens out per optimiser call.
- 3 optimiser calls per game (per user's stated usage pattern).
- Embedding: combined field text (~800 tokens), 2 embed calls per game lifecycle
  (1 create + 1 edit, average).
- Photos: 5 photos uploaded per game (of a 10-photo cap), ~800KB average per photo
  after client-side compression (5MB is the hard cap, not the typical size).
- Photo views: 100 views/month/game assumed for retrieval cost, modeled both with and
  without Cloudflare CDN caching in front of the public R2 bucket.
- Brain-dump call: one nano call, ~860 tokens in (combined dump text + extraction
  system prompt), ~400 tokens out (three split fields).

## Per-game cost breakdown

| Item | Calc | Cost |
|---|---|---|
| Optimiser (3 GPT-4.1-nano calls) | 3 × (430 tok in × $0.10/1M + 150 tok out × $0.40/1M) | **~$0.0003** |
| Embedding (2 calls, create + edit) | 2 × (800 tok × $0.02/1M) | **~$0.00003** |
| Brain-dump split (1 GPT-4.1-nano call) | 860 tok in × $0.10/1M + 400 tok out × $0.40/1M | **~$0.00025** |
| Photo upload (5× Class A) | 5 × $4.50/1M | **~$0.00002 (one-time)** |
| Photo storage (5 × 800KB = 4MB) | 0.0039GB × $0.015/GB-mo | **~$0.00006 / month** |
| Photo retrieval, no CDN cache (worst case) | 500 ops/mo × $0.36/1M | **~$0.00018 / month** |
| Photo retrieval, with CDN cache (~95% hit) | 25 ops/mo × $0.36/1M | **~$0.00001 / month** |

### Totals per game

| Scenario | One-time | Recurring (monthly) |
|---|---|---|
| Optimiser + embedding + photos (no brain dump) | **~$0.00035** | **~$0.00007–$0.00024** |
| + text-based brain dump | **~$0.00060** | same as above |

Brain dump (text-only, client-side speech recognition) adds roughly the cost of one
extra optimiser call — not materially different from the baseline. There is no
Whisper/audio cost since transcription happens on-device.

## At scale

10,000 games created in a month:

| Scenario | Total one-time AI + upload cost |
|---|---|
| Optimiser + embedding + photo uploads only | **~$3.50** |
| + text-based brain dump | **~$6.00** |

Recurring storage/retrieval cost stays inside R2's free tier (10GB storage / 1M Class A
/ 10M Class B per month) for a very long time at this scale — realistically $0/month
until well past 10,000+ accumulated games with photos.

---

# Platform running costs

The costs above are **per-game unit economics** — they scale with games created. The
costs below are **fixed platform / traffic-driven** costs that exist regardless of
per-game AI usage. Both are needed for a full run-rate.

## Additional pricing used (as of July 2026)

| Service | Rate | Source |
|---|---|---|
| Railway Hobby plan | $5 / month (includes $5 usage credit) | [Railway Pricing](https://railway.com/pricing) |
| Railway Pro plan | $20 / month per seat (includes $20 usage credit) | [Railway Pricing](https://railway.com/pricing) |
| Railway CPU | $20 / vCPU-month ($0.000463/vCPU/min) | [Railway Pricing](https://railway.com/pricing) |
| Railway RAM | $10 / GB-month ($0.000231/GB/min) | [Railway Pricing](https://railway.com/pricing) |
| Railway volume storage | $0.15 / GB-month | [Railway Pricing](https://railway.com/pricing) |
| Railway network egress | $0.05 / GB | [Railway Pricing](https://railway.com/pricing) |
| Amplitude Free (Starter) | $0 — 2M events / month | [Amplitude Pricing](https://amplitude.com/pricing) |
| Amplitude Plus | $49 / month — up to 300k MTU or 25M events | [Amplitude Pricing](https://amplitude.com/pricing) |
| Amplitude Growth | Custom (~$500–2,000+/mo at scale) | [Amplitude Pricing](https://amplitude.com/pricing) |
| Resend (email) Free | $0 — 3,000 emails / month, 100 / day | [Resend Pricing](https://resend.com/pricing) |
| Resend Pro | $20 / month — 50,000 emails | [Resend Pricing](https://resend.com/pricing) |
| `.co.uk` domain | ~$10–13 / year (~$1 / month) | registrar |

## 1. Railway (backend hosting) — fixed monthly cost

> **Estimate, not measured.** Railway CLI login was expired at time of writing, so the
> compute figure below is modeled from the resource-usage rate card, not pulled from
> actual billing. For the final finance report, run `! railway login` and the real
> current spend can be read from Railway metrics — actual usage beats a model.

The backend is a single FastAPI service plus a Railway-managed Postgres instance. Both
are billed on the same usage model (CPU + RAM + volume + egress), and both draw down the
plan's included usage credit before any overage is charged.

Modeled steady-state for a low-traffic app:

| Component | Assumed usage | Monthly |
|---|---|---|
| FastAPI service (CPU) | ~0.1 vCPU avg | ~$2.00 |
| FastAPI service (RAM) | ~0.25 GB avg | ~$2.50 |
| Postgres (CPU) | ~0.05 vCPU avg | ~$1.00 |
| Postgres (RAM) | ~0.25 GB avg | ~$2.50 |
| Postgres volume | ~1 GB | ~$0.15 |
| Egress | ~2 GB (photos served from R2, not Railway) | ~$0.10 |
| **Modeled resource usage** | | **~$8.25** |

Effective cost by plan (usage credit applied):

| Plan | Subscription | Included credit | Effective monthly |
|---|---|---|---|
| Hobby | $5 | $5 | ~$8.25 usage − $5 credit + $5 sub = **~$8.25** |
| Pro (1 seat) | $20 | $20 | usage ($8.25) inside $20 credit = **~$20** |

**Takeaway:** at this traffic level Railway is effectively **~$8–$20 / month** and does
not scale with game count. It scales with concurrent traffic (CPU/RAM), so it steps up
only as active-user load grows. Serving photos from R2 (zero egress) rather than Railway
keeps egress negligible here.

## 2. Amplitude (frontend analytics) — traffic-driven, over time

The org is currently on the **free Starter plan** (verified via API: plan `starter_v3`),
which allows **2M events / month** at $0. Amplitude cost is driven by **event volume**
(a function of active users × actions each), **not** by games created — so it grows with
adoption, not catalogue size.

Assumption: an active user generates **~40 events/session × ~4 sessions/month ≈ 160
events/user/month** (page views, game views, searches, upvotes, uploads, optimiser use).

| Monthly active users (MAU) | Est. monthly events (@160/user) | Amplitude plan | Monthly cost |
|---|---|---|---|
| 1,000 | 160k | Free | **$0** |
| 5,000 | 800k | Free | **$0** |
| ~12,500 | ~2.0M | Free tier ceiling | **$0** (at the limit) |
| 20,000 | 3.2M | Plus | **$49** |
| 100,000 | 16M | Plus (under 25M) | **$49** |
| 150,000+ | 24M+ | Plus → Growth | **$49 → custom** |

**Free → paid crossover: ~12,500 MAU.** Below that, analytics are free. The first paid
step is a flat **$49/month** (Plus), which then covers all the way to ~25M events
(~150k MAU) before a custom Growth contract is needed.

> **Sensitivity:** the crossover depends entirely on the ~160 events/user/month
> assumption. If instrumentation is heavier (e.g. ~320 events/user), the free-tier
> ceiling halves to **~6,250 MAU**. Tune the events-per-user figure once real Amplitude
> event data exists.

## 3. Other running costs

| Cost | Provider | Rate | Notes |
|---|---|---|---|
| Transactional email | Resend | $0 free (3k/mo) → $20/mo (50k) | Password-reset emails (`src/services/email.py`). Free tier fits until ~3,000 resets/month. |
| Domain | `whatsthatgame.co.uk` registrar | ~$1 / month (~$10–13/yr) | Fixed. |
| TLS / SSL | Railway | $0 | Included. |
| Google OAuth | Google | $0 | No cost at this scale. |
| Cloudflare R2 | Cloudflare | ~$0/mo (free tier) | See per-game section above. |
| OpenAI (optimiser + embeddings) | OpenAI | sub-cent/game | See per-game section above. |

# Combined monthly run-rate

Bringing fixed + traffic-driven + per-game×volume together. Per-game AI/upload cost is
~$0.00035–$0.0006 (see above), so even 10,000 new games/month adds only ~$3.50–$6.00 —
negligible against fixed costs.

| Stage | MAU | Fixed (Railway + domain) | Amplitude | Email | Per-game AI (@ games/mo) | **Total / month** |
|---|---|---|---|---|---|---|
| Early | ~1,000 | ~$9 | $0 | $0 | ~$0.35 (1k games) | **~$9** |
| Growing | ~10,000 | ~$20 | $0 | $0 | ~$3.50 (10k games) | **~$24** |
| Scaling | ~25,000 | ~$35 (heavier compute) | $49 | $20 | ~$6 (15k games) | **~$110** |
| Large | ~100,000 | ~$80 (multi-instance) | $49 | $20 | ~$6 | **~$155** |

Railway compute at the higher stages is a rough scale-up and is the least certain line —
confirm with real metrics once login is restored.

## Bottom line

- **Per-game AI + storage** (OpenAI, R2) is sub-cent and stays inside free tiers for a
  long time — not the cost driver.
- **Railway** is the dominant *early* cost: a near-fixed **~$8–$20/month** regardless of
  game count, scaling only with traffic. (Currently modeled — verify with `railway login`.)
- **Amplitude** is **$0 until ~12,500 MAU**, then a flat **$49/month** to ~150k MAU. It
  is the main *analytics* line but only kicks in at real scale.
- **Email (Resend)** and the **domain** are trivial (~$0–$21/month combined).
- Realistic total run-rate: **~$9/month early**, **~$24/month at 10k MAU**, stepping to
  **~$110–$155/month** only once analytics and heavier compute engage past ~25k MAU.

The brain-dump feature, using client-side speech recognition rather than server-side
transcription, does not change this materially — it's roughly one extra cheap LLM call
per game, not a new cost category.