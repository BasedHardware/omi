# chat

Not a rail destination. Lives on `/home` and as an overlay from other pages.

- `api.ts` — sessions, streaming messages, file upload, Gemini live tokens
- `model.ts` — stream-line decode (`parseStreamLine`)
- `ui/` — `ChatComposer`/`ChatTranscript` (home) and `ChatPanel` (overlay); do not merge those composers in this folder move
- `useChat.ts` / `useGeminiLive.ts` — existing React orchestration
