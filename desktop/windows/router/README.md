# Omi local "brain" router (Laya sidecar)

A tiny **Python sidecar** that runs a fast non-LLM intent/difficulty classifier
([laya](https://github.com/NandhaKishorM/laya)) and answers one question per
request: *"where should Omi handle this?"* The desktop app's
`src/renderer/src/lib/localBrain.ts` calls it and routes the turn to local tools,
a small local LLM, or the metered cloud — so easy/known-local turns **don't burn
your cloud quota**.

> This is a *decision* router, not the answering model, and **not** speaker ID.
> Speaker identity already lives in the local voiceprint module (`voiceprint.ts`).
> Laya's base checkpoints are near-chance zero-shot on a custom taxonomy — treat
> this as a conservative router (unknown → cloud) until you **fine-tune** it on
> labelled Omi requests.

## Run
```bash
cd router
python3 -m pip install -r requirements.txt
python3 laya_server.py --device cpu --model ./models/laya   # -> http://127.0.0.1:8765
```
`--device` accepts `cpu` / `cuda` / `mps`. Put a laya checkpoint in `./models/laya`
(a local dir works, as does the HF model id).

## Contract
`POST /route { "request": "…free text…" }` → `{ "route", "intent", "needs_tools", "difficulty" }`
where `route ∈` `confirm_or_refuse | omi_local_memory | omi_local_screen_history |
omi_task_tools | small_local_llm | large_local_llm_or_cloud`. `GET /health` for liveness.

## Wire it up in the app
Settings → General → LLM: set a **Local** model (Base URL e.g. `http://localhost:8080/v1`
via `llama-server --jinja`), then enable **Local brain router** + point it at this
sidecar (`http://127.0.0.1:8765`). Off by default; any sidecar error/timeout falls
back to the normal cloud path.

## No heavy deps? Still testable
`torch`/`laya`/`fastapi` are imported **lazily**, so `decide_route()` (the pure
routing map) imports and unit-tests with nothing installed:
```bash
python3 -c "from laya_server import decide_route; print(decide_route({'answers':{'intent':{'choice':'memory_search'},'needs_tools':{'choice':'yes'}}}))"
```
