# Omi React Native — Contributor Notes

Android-first RN port of the Omi mobile app (Flutter in `../`). Talks to the same Omi
backend as `desktop/linux` and `desktop/windows`.

## Layout
- `src/api/omiApi.ts` — axios client + endpoint helpers (`/v3/memories`, `/v1/conversations`, …).
- `src/auth/firebaseAuth.ts` — Firebase auth; ID token used as the Omi bearer token.
- `src/state/*` — Zustand stores (auth, conversations, memories, capture).
- `src/services/stt.ts` — Deepgram streaming STT (nova-2 + diarize), matches `deepgramListen.ts`.
- `src/services/voiceprint.ts` — speaker enrollment ("You" / "Other N"); mirrors `voiceprint.ts`.
- `src/services/tts.ts` — TTS (Web Speech, Deepgram Aura fallback pending).
- `src/screens/*` — Onboarding, Home, Conversations, ConversationDetail, Memories, Capture, Settings.

## Build (Expo, Android)
```bash
pnpm install
pnpm start            # expo start (metro dev server)
pnpm run android      # expo run:android (prebuilds + runs on emulator/device)
```
Firebase is wired via config plugins in app.json (`@react-native-firebase/app`, `/auth`);
place `google-services.json` in the prebuilt `android/app/`.

## Validation
```bash
pnpm run typecheck    # TypeScript strict mode check
pnpm run lint         # ESLint (TS, React, React Hooks)
```
See `TESTING.md` for full validation and device testing procedures.

## Status
Phase 1 vertical slice (Expo Router): auth → conversations → live capture (mic→Deepgram) →
memories. `pnpm install` / `expo start` are the dev entry points.
