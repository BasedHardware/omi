# chat

Not a rail destination. Lives on `/home` and as an overlay from other pages.

- `api.ts` — sessions, streaming messages, file upload, Gemini live tokens
- `model.ts` — stream-line decode (`parseStreamLine`)
- `ui/` — `ChatComposer` (home pill) and `ChatPanel` (overlay) share `useChatAttachments`; they are not one visual composer
- `useChat.ts` / `useGeminiLive.ts` — signal stores; live session ownership is still the client-ref guard
