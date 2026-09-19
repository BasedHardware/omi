import Constants from 'expo-constants';

/**
 * Runtime configuration for the Omi RN (Expo) app.
 * Values come from app.json `expo.extra` (overridable via EAS secrets).
 * Mirrors the env contract used by the Flutter app and the desktop/linux port.
 *
 * SECURITY: never place a reusable provider key (e.g. a raw Deepgram API key)
 * here. Anything in `expo.extra` is compiled into the distributed client bundle
 * and is trivially extractable. Live speech recognition must go through the Omi
 * backend STT proxy (`listenWsUrl`), which authenticates with the short-lived,
 * user-scoped Firebase ID token and holds provider credentials server-side. A
 * raw `deepgramWsUrl + access_token` is only acceptable for a local dev run with
 * an ephemeral key the developer supplies out-of-band (never committed).
 */
const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, string>;

export const ENV = {
  apiBaseUrl: extra.apiBaseUrl ?? 'https://api.omi.me',
  // Backend websocket that proxies STT/agent traffic; auth is the Bearer ID token.
  listenWsUrl: extra.listenWsUrl ?? 'wss://api.omi.me/v4/listen',
  agentProxyWsUrl: extra.agentProxyWsUrl ?? 'wss://api.omi.me/v1/agent/chat',
  webClientId: extra.webClientId ?? '',
} as const;

export type Env = typeof ENV;
