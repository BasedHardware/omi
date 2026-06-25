# Auto-router v1 — Demo scenarios

Three concrete demonstrations of the auto-router's behavior under different per-task weights. Run them locally to see how the picker responds to weight changes.

## How to run

```bash
cd /Users/choguun/Documents/workspaces/cool-projects/omi-worktrees/auto-router-v1/backend
PYENV_VERSION=3.12.8 python -m utils.auto_router.demo.run
```

Or to call the actual HTTP endpoint (with default weights from `benchmarks.example.json`):

```bash
# Start the backend
cd backend && uvicorn main:app --reload --port 8000

# Hit the endpoint
curl http://localhost:8000/v1/auto-router/pick?task=ptt_response
curl http://localhost:8000/v1/auto-router/pick?task=general_assistant
curl http://localhost:8000/v1/auto-router/pick?task=screenshot_understanding
```

The demo script (`scripts/auto_router_demo.py`) uses the framework's scoring function directly with overridden weights — it does NOT call the HTTP endpoint. That's intentional: it shows the picker would behave correctly IF you adjusted the task weights (e.g., in `benchmarks.json` or a per-user preference layer).

---

## Demo 1: Low-cost mode for general_assistant

**Setup:** Override weights from the balanced defaults (q=0.5/l=0.3/c=0.2) to cost-dominant (q=0.1/l=0.1/c=0.8).

**Expected:** The cheap model (`haiku-4-5` with cost_score 0.85) wins.

**Result:**
```
Original weights (balanced):       haiku-4-5 wins (score 0.8000)
Cost-heavy override (q=0.1/l=0.1/c=0.8): haiku-4-5 still wins (score 0.8400)

Ranking shifts significantly:
  Original: haiku 0.800 → gemini-pro 0.775 → gpt-4o 0.735
  Override: haiku 0.840 → gemini-pro 0.603 → gpt-4o 0.477
```

**Interpretation:** When the user biases heavily toward cost, the scoring function amplifies the cost dimension. `haiku-4-5` is already cost-competitive (0.85) so it dominates even more strongly. `gemini-pro` and `gpt-4o` drop because their cost scores (0.55, 0.40) become 8× more important than before.

The winner is the same in this case because `haiku` was already the cost leader — the override amplifies its lead, but doesn't change the top spot. That's a feature, not a bug: the picker doesn't change winners unless it should.

---

## Demo 2: High-quality mode for screenshot_understanding

**Setup:** Override weights from quality-leaning (q=0.6/l=0.2/c=0.2) to extreme quality (q=0.95/l=0.025/c=0.025).

**Expected:** The strongest quality model (`claude-sonnet-4-6` with quality_score 0.95) wins.

**Result:**
```
Original weights (balanced):      gemini-1-5-pro wins (score 0.7880)
Quality-heavy (q=0.95/l=0.025/c=0.025): claude-sonnet-4-6 wins (score 0.9275)

Winner CHANGED:
  Before: gemini-1-5-pro (score 0.7880)
  After:  claude-sonnet-4-6 (score 0.9275)
```

**Interpretation:** With balanced weights, `gemini-1-5-pro` wins because its combined quality/latency/cost profile (0.88/0.75/0.55) edges out `claude-sonnet-4-6` (0.95/0.65/0.35). When the user makes quality overwhelmingly important, `claude-sonnet-4-6`'s 0.95 quality score dominates — it becomes the clear winner despite being slightly slower and more expensive.

This is exactly the kind of tradeoff the user can express through the router. The same models are candidates; the user just changes the relative importance.

---

## Demo 3: Low-latency mode for ptt_response

**Setup:** Override weights from latency-leaning (q=0.4/l=0.5/c=0.1) to extreme latency (q=0.05/l=0.9/c=0.05).

**Expected:** The fastest model (`gemini-1-5-flash-8b-exp` with latency_score 0.95) wins.

**Result:**
```
Original weights (latency-leaning): gemini-1-5-flash-8b-exp wins (score 0.8650)
Latency-heavy (q=0.05/l=0.9/c=0.05): gemini-1-5-flash-8b-exp wins (score 0.9375)

Same winner, but ranking shifts:
  Original: gemini 0.865 → gpt-realtime 0.800 → haiku 0.790
  Override: gemini 0.938 → haiku 0.843 → gpt-realtime 0.793
```

**Interpretation:** `gemini-1-5-flash-8b-exp` has the highest latency_score (0.95) so it's the clear winner in both cases. But the override surfaces an interesting secondary effect: `haiku-4-5` rises from 3rd to 2nd place. Reason: `haiku` has higher latency_score (0.85) than `gpt-realtime-2` (0.80), but the original weights also gave some credit to quality, where `gpt-realtime-2` slightly edged `haiku`. When latency dominates, `haiku` wins the tiebreaker.

This shows the router can re-rank candidates based on subtle differences in the dimension weights — not just change the top spot.

---

## What the demos show (summary)

| Demo | Setup | Winner changed? | Why it matters |
|---|---|---|---|
| 1. Low-cost general_assistant | q=0.1/l=0.1/c=0.8 | No (haiku stayed) | Override amplifies the cost dimension; pre-existing cost leader's lead widens |
| 2. High-quality screenshot | q=0.95/l=0.025/c=0.025 | **Yes** (gemini → claude) | The user expressed strong quality preference; the picker correctly switched to the quality king |
| 3. Low-latency PTT | q=0.05/l=0.9/c=0.05 | No (gemini stayed) | Override changes the secondary ranking, surfacing haiku over gpt-realtime |

**The mechanism works.** Per-task weights drive the picker; the same candidate set can produce different winners depending on the user's relative priorities.

---

## What's NOT in these demos

- **Real AA benchmarks** — these use the committed `benchmarks.example.json` (educated estimates). Production deployment would replace this with real measurements.
- **Cost dimension interaction with latency** — the formula treats them independently. A future improvement could penalize candidates where high speed implies high cost (positive correlation in real benchmarks).
- **User feedback loops** — picks are pure functions of weights + benchmark data. There's no per-user preference learning yet.

See [`docs/doc/developer/auto-router.mdx`](./doc/developer/auto-router.mdx) "Future work" for the roadmap.
