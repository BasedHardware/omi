# Omi — React Native App (`app/react-native`)

A React Native port of the Omi mobile app, **Android-first**, with **Firebase Auth**.
It talks to the same Omi backend as the Flutter app (`app/`) and the desktop ports
(`desktop/windows`, `desktop/linux`).

> This is an active port. See [`PLAN.md`](./PLAN.md) for the full scope and phasing.
> Phase 1 delivers the project skeleton + a vertical slice (auth → conversations →
> live capture → memories) on Android via the Expo workflow.

## Prerequisites
- Node 18+ and pnpm (or npm)
- Expo CLI: `pnpm add -g expo-cli`
- Android SDK (API 33+) and an emulator or device for `expo run:android`
- A Firebase config (`google-services.json` for Android, `GoogleService-Info.plist` for iOS)

## Setup
```bash
cd app/react-native
pnpm install
# place google-services.json in the generated android/app/ (after expo prebuild)
pnpm start          # expo start
pnpm run android    # expo run:android
```

## Architecture
- **State:** Zustand
- **Navigation:** React Navigation
- **Networking:** axios + native WebSocket (`/v4/listen`)
- **Auth:** `@react-native-firebase/auth` (Android)
- **STT:** mic → Deepgram `nova-2` + diarize (speaker ID via enrolled voiceprint)
- **TTS:** Web Speech / Deepgram Aura
- **BLE (Omi device):** `react-native-ble-plx`

## Backend
Reuses Omi REST/WebSocket contracts: `/v1/conversations`, `/v3/memories`, `/v1/goals`,
`/v1/action-items`, `/v1/knowledge-graph`, `/v4/listen`. See `PLAN.md` for the full list.
