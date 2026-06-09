# Model Cost Analysis — AI Optimiser

**Date:** 2026-06-03
**Scope:** OpenAI model selection for the AI optimiser (`src/services/optimiser.py`), plus a cost
projection at scale. The embedder model is treated as fixed and not analysed here.

---

## 1. Current Setup

| Task      | File                          | Model                    | Call site                          |
|-----------|-------------------------------|--------------------------|------------------------------------|
| Optimiser | `src/services/optimiser.py`   | `gpt-4.1-nano`           | `responses.create()` (line 46)     |
| Embedder  | `src/services/embedder.py`    | `text-embedding-3-small` | `embeddings.create()` (line 43)    |

- **Optimiser** rewrites a single game field (`description`, `objective`, `setup`, `rules`) on demand,
  using a per-field system prompt from `src/utils/prompts.py`. **This is the model under analysis.**
- **Embedder** runs once per game submission (and on edit). Fixed at `text-embedding-3-small` — not
  changing, so it is folded in as a flat **$0.000003/game** line and not compared further.

---

## 2. Per-Call Token & Cost Profile

### Optimiser (per field optimised)

Approximate token budget per call:

- System prompt (per-field template): ~230 tokens
- User text (`Input: <field text>`): ~250 tokens
- Output (rewritten field): ~150 tokens

| Model                  | Input $/1M | Output $/1M | Cost / call | Verdict for this task        |
|------------------------|-----------:|------------:|------------:|------------------------------|
| `gpt-4.1-nano` *(now)* |      $0.10 |       $0.40 |  $0.000108  | Correct choice. Cheapest viable. |
| `gpt-4o-mini`          |      $0.15 |       $0.60 |  $0.000162  | Marginal gain, not worth it. |
| `gpt-4.1-mini`         |      $0.40 |       $1.60 |  $0.000432  | The real ceiling. Use only if nano fails `rules`. |
| `gpt-4.1`              |      $2.00 |       $8.00 |  $0.00216   | Overkill. No measurable benefit. |
| `gpt-5` / `gpt-5-mini` / `gpt-5-nano` | high | high | — | **Overkill — see §4.** |

> Embedding is fixed at `text-embedding-3-small` ≈ **$0.000003/game** (~150 tokens × $0.02/1M). It is
> ~1.4% of a Medium game's cost — included as a flat line below, not analysed.

---

## 3. Cost Model — Bottom-Up

Build the unit cost from the smallest atom (one game) and scale up. This keeps the model independent
of any user-count guess — pick your own user number and multiply.

### 3a. The two atomic units

| Unit                          | `gpt-4.1-nano` | `gpt-4.1-mini` |
|-------------------------------|---------------:|---------------:|
| 1 embedding (per game, fixed) |     $0.000003  |     $0.000003  |
| 1 optimiser call (per field)  |     $0.000108  |     $0.000432  |

Embedding is fixed (`text-embedding-3-small`) — same in both columns. Only the optimiser model swaps.

### 3b. Cost per game

Every game = 1 embed (always) + N optimiser calls (0–4, user's choice). `Fields` = how many fields
the user optimises on that game.

| Fields optimised | `gpt-4.1-nano` / game | `gpt-4.1-mini` / game |
|------------------|----------------------:|----------------------:|
| 0 (embed only)   |          $0.000003    |          $0.000003    |
| 1 (Light)        |          $0.000111    |          $0.000435    |
| **2 (Medium)**   |        **$0.000219**  |        **$0.000867**  |
| 4 (Heavy)        |          $0.000435    |          $0.001731    |

> Read: even in the Heavy case on the pricier model, one game costs **~0.17 cents**. Embedding is
> ~1.4% of a Medium game's cost — negligible.

### 3c. Cost per user

**Assumption:** one user submits 1–2 games/day → midpoint **1.5 games/day** = **45 games/month**.
Hold the Medium (2-field) behaviour constant.

| Per user      | `gpt-4.1-nano` | `gpt-4.1-mini` |
|---------------|---------------:|---------------:|
| per day (1.5 games)   |    $0.00033 |    $0.00130 |
| **per month (45 games)** |  **$0.00986** |  **$0.03902** |
| per year (548 games)  |    $0.11999 |    $0.47470 |

> A user costs **~1 cent/month** on nano, **~4 cents/month** on mini. Per-user cost is the number to
> compare against ARPU / subscription price.

### 3d. Scale-up (Medium scenario, multiply §3c by user count)

| Users    | nano /month | mini /month | nano /year | mini /year |
|----------|------------:|------------:|-----------:|-----------:|
| 1        |     $0.0099 |     $0.0390 |     $0.12  |     $0.47  |
| 100      |     $0.99   |     $3.90   |    $11.83  |    $46.80  |
| 1,000    |     $9.86   |    $39.02   |   $118.26  |   $468.24  |
| 10,000   |    $98.55   |   $390.15   | $1,182.60  | $4,681.80  |
| 100,000  |   $985.50   | $3,901.50   |$11,826.00  |$46,818.00  |

Same totals as a top-down model, but now every row traces back to one auditable per-game atom in §3b.

---

## 4. Why GPT-5 Is Overkill

The optimiser task is **creative rewriting under rigid formatting rules** — not reasoning, not
knowledge retrieval, not long-context synthesis. GPT-5's strengths (multi-step reasoning, large
context, agentic planning) are irrelevant here. The job is:

1. Read 1–3 sentences of user text.
2. Rewrite it cleaner, preserving identity / profanity / structure.
3. Obey ~7–10 formatting rules (no em dashes, no markdown fences, keep card-value identifiers).

A small model does this fine. GPT-5 would cost multiples more per call for output a human could not
distinguish from `gpt-4.1-nano` on this task. **Every GPT-5 variant is overkill.** The hard ceiling
for any plausible quality need is `gpt-4.1-mini`.

---

## 5. Recommendations

1. **Optimiser: stay on `gpt-4.1-nano`** for `description` and `objective` (simple fields).
2. **Benchmark `gpt-4.1-nano` on the `rules` field specifically** — it is the most rule-heavy prompt
   (card-value detection, profanity preservation, blank-line formatting). If nano slips, upgrade
   **only that field** to `gpt-4.1-mini`. Per-field routing keeps cost down while protecting quality.
3. **Do not use any GPT-5 model** for the optimiser.
4. **Embedder** is out of scope — fixed at `text-embedding-3-small`, counted as a flat $0.000003/game.

### Cost-saving lever worth noting

The system prompt (~230 tokens) is sent on **every** optimiser call. At 900k calls/month that is
~207M repeated input tokens. OpenAI prompt caching (or batching repeat-structure calls) could cut the
input half of the optimiser bill significantly if volume grows. Not urgent at current scale.
