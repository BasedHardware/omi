# Testing on a real iPhone (and with an Omi wearable)

The simulator has no Bluetooth and no working Apple speech recognition, so capture with a device
and on-device transcription are verified on hardware. Everything else is verified headless (see README).

## 1. One-time setup

1. `cp Config/Secrets.xcconfig.example Config/Secrets.xcconfig` and set:
   - `DEVELOPMENT_TEAM` = your team (e.g. `ABCDE12345`)
   - `OMI_BUNDLE_ID` = a bundle id your team can sign (e.g. `com.yourname.omi.native`)
   - `OMI_API_HOST` = `<mac-lan-ip>:8000`, `OMI_AUTH_EMULATOR_HOST` = `<mac-lan-ip>:9099`
2. Start the harness reachable from the phone (upstream checkout):
   `OMI_DEV_HOST=<mac-lan-ip> PROVIDER_MODE=offline OMI_HARNESS_REDIS_PORT=6390 make dev-up`
3. Seed demo data: `python3 Tools/dev/seed_demo_conversations.py && python3 Tools/dev/seed_demo_tasks_memories.py`
4. `make generate && open Omi.xcodeproj`, pick your iPhone, Run.

Sign in with the local-dev button as `alice`. Allow Local Network, Microphone and Speech Recognition when asked.

## 2. What to check

| Area | Steps | Expected |
|---|---|---|
| Phone capture | Today → Record, talk for 20 s, Stop | Live level bars move, live transcript appears (on-device Apple speech), "Saving conversation…" |
| Omi pairing | Header device button → nearby list → tap your Omi | Connected, battery %, firmware and codec shown; header pill shows battery |
| Omi capture | Keep the Omi on and talk | Capture starts by itself ("Listening with Omi"), red dot in the header; transcript needs server STT (see 3) |
| Reconnect | Kill the app, reopen | The Omi reconnects without pairing again |
| Update path | Install the Flutter dev build, pair your Omi, install this build over it | Still signed in, the Omi reconnects (same `flutter.btDevice` and restore id) |
| Agent | Tasks → swipe right → Omi takes over | Steps stream, workstream recorded (answers need an LLM, see 3) |

## 3. Real AI locally (agent answers, summaries)

`Tools/dev/dev-up-real.sh <mac-lan-ip>` starts the harness in real mode. The backend's OpenAI calls
go to `Tools/dev/llm_proxy.py`, which serves them through OpenRouter (chat and agent
`xiaomi/mimo-v2.6-flash`; background extraction `google/gemini-2.5-flash-lite`, because the backend
cuts it off after 35 s; embeddings `openai/text-embedding-3-large`) using `~/.openrouter-key.env`; every request carries
`provider.max_price` ($0.20/M in, $0.50/M out) and reasoning off. `LLM_PROVIDER=gemini` uses Gemini
(`gemini-2.5-flash-lite`, `~/.gemini-key.env`) instead. To switch a running harness, restart only
the proxy: `OPENROUTER_API_KEY=... Tools/dev/llm_proxy.py --provider openrouter`.
Speech-to-text: with `~/.deepgram-key.env` (`DEEPGRAM_API_KEY=...`) the backend transcribes with
Deepgram nova-3 (`STT_SERVICE_MODELS=dg-nova-3,parakeet`), as in production, so capture keeps
working with the app in the background. Without it, turn on Settings › Capture › Transcribe on this
iPhone: Apple's recognizer only runs while the app is in front.

The harness has no Firestore -> Typesense sync and no Pinecone, so `dev-up-real.sh` also runs
`Tools/dev/index_conversations_typesense.py --all --watch 15`, which keeps every local user's
conversations searchable for the agent.

Web search: production uses Perplexity Sonar through the LLM gateway (above the price ceiling), and
the local gateway has no route for it. The proxy also fronts the gateway on port 9912
(`OMI_DEV_LLM_GATEWAY_URL`, read by the harness patch): it answers the `omi:auto:web-search` lane
with `gemini-2.5-flash-lite` plus OpenRouter's web plugin (3 results, about $0.0075 per search,
sources returned as Perplexity-style `citations`) and passes every other gateway request through.

The patch also sets `MEMORY_ENABLED=on`: the backend now fails closed without it, which pauses
memory writes and fails every recorded conversation's processing (503).

One-time: apply `Tools/dev/harness-real-mode.patch` to the upstream checkout (lets the harness pass
`OPENAI_BASE_URL` and `STT_SERVICE_MODELS` through to the backend).

Needs a key with credit; without it every answer is the backend's canned error.

## 4. Limits of the offline harness

`PROVIDER_MODE=offline` has no LLM and no server speech-to-text:
- Phone capture works end to end with on-device transcription; the backend's summary step then
  fails (HTTP 500 in `_get_structured`) and the conversation stays in progress.
- Omi capture streams opus to the backend, but no transcript comes back without server STT.
- Agent and chat answers are the backend's canned error text.

With real provider keys in upstream `backend/.env.local-dev` (`PROVIDER_MODE=real`) all three work
end to end. Against production (`api.omi.me`) only BasedHardware's own signed build can sign in.
