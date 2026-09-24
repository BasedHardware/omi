# Omi local "brain" router (Laya sidecar)

A tiny, **opt-in Python sidecar** that runs a fast non-LLM intent/difficulty
classifier ([laya](https://github.com/NandhaKishorM/laya)) and answers one
question per request: *"where should this turn be handled?"* — the cheap,
local-capable vs. cloud-hard decision.

> **Status: inert building block — NOT wired into the app.** `desktop/windows`
> `src/renderer/src/lib/localBrain.ts` holds the pure `planFromDecision()` mapper
> and a `/route` client, but **nothing on `main` imports or runs it**, and there
> is **no app Settings toggle** for it on `main`. The decision to grow a local
> intent-routing tier over "Ask Omi Anything" is an open maintainer
> product/security call — tracked in **RFC #17295**. Do **not** wire this to the
> agent control plane or `llm_gateway` routing without that decision (see
> `INV-AGENT-*` and the BYOK/provider contract).
>
> This classifier is **text only**. It does **not** do speaker identification /
> diarization (that is out of scope here and lives elsewhere in Omi). Laya's base
> checkpoints are near-chance zero-shot on a custom taxonomy, so this behaves as a
> conservative router (unknown → cloud) until fine-tuned on labelled Omi requests.

## Relationship to the existing macOS router
`desktop/macos/agent/src/runtime/desktop-intent-router.ts` already implements a
deterministic intent router (`answer_inline / spawn_agent / continue_run / clarify
/ reject`) for the macOS agent runtime. This sidecar is a *different* thing: a
statistical local-vs-cloud classifier. Whether "intent routing" converges on one
shared concept or stays per-platform is an open question for #17295, and is
cheaper to settle before any wiring lands.

## Run (manual / local testing only — nothing installs or runs it in CI)
```bash
cd router
python3 -m pip install -r requirements.txt           # or: uv venv && uv pip install -r requirements.txt
python3 laya_server.py --device cpu --model ./models/laya   # -> http://127.0.0.1:8765
# no torch/weights needed to exercise the contract:
python3 laya_server.py --mock                          # stdlib-only stub, same routes
```
`--device` accepts `cpu` / `cuda` / `mps`. `--model` may be a local dir or the HF
model id.

## Contract
`POST /route { "request": "…free text…" }` → `{ "route", "intent", "needs_tools", "difficulty" }`
where `route ∈` `confirm_or_refuse | omi_local_memory | omi_local_screen_history |
omi_task_tools | small_local_llm | large_local_llm_or_cloud`. `GET /health` for
liveness. `localBrain.ts` `VALID_ROUTES` mirrors these 1:1; unknown/empty/garbage
classifier output fails safe to cloud.

## Testable with no heavy deps
`torch`/`laya`/`fastapi` are imported **lazily**, so the pure `decide_route()` map
imports and tests with nothing installed:
```bash
python3 -c "from laya_server import decide_route; print(decide_route({'answers':{'intent':{'choice':'memory_search'},'needs_tools':{'choice':'yes'}}}))"
```
`planFromDecision()` has vitest coverage in `src/renderer/src/lib/localBrain.test.ts`.

## See also
- RFC #17295 — consent-gated local-brain / ambient assistant (the product decision this feeds).
- #15948 — the desktop local-model download manager (the model this router would route *to*).
