const fs = require('fs');
const path = require('path');

// Load the base Expo config (kept in app.json for tooling compatibility) and
// allow local-dev overrides via EXPO_PUBLIC_* env vars. Never put provider
// secrets here — EXPO_PUBLIC_* is bundled into the client.
const base = JSON.parse(fs.readFileSync(path.join(__dirname, 'app.json'), 'utf8'));
const expo = base.expo || base;
const extra = { ...(expo.extra || {}) };

if (process.env.EXPO_PUBLIC_API_BASE_URL) extra.apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;
if (process.env.EXPO_PUBLIC_LISTEN_WS_URL) extra.listenWsUrl = process.env.EXPO_PUBLIC_LISTEN_WS_URL;
if (process.env.EXPO_PUBLIC_AGENT_PROXY_WS_URL)
  extra.agentProxyWsUrl = process.env.EXPO_PUBLIC_AGENT_PROXY_WS_URL;
if (process.env.EXPO_PUBLIC_WEB_CLIENT_ID) extra.webClientId = process.env.EXPO_PUBLIC_WEB_CLIENT_ID;

module.exports = { ...base, expo: { ...expo, extra } };
