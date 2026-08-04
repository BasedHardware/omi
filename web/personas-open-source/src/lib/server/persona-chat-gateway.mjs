const UNAUTHENTICATED_LANE = 'omi:auto:persona-chat';
const AUTHENTICATED_LANE = 'omi:auto:persona-chat-premium';

export class PersonaAuthenticationError extends Error {
  constructor(message = 'Invalid authentication') {
    super(message);
    this.name = 'PersonaAuthenticationError';
  }
}

export class PersonaGatewayUnavailableError extends Error {
  constructor(message = 'The chat service is unavailable') {
    super(message);
    this.name = 'PersonaGatewayUnavailableError';
  }
}

export async function resolvePersonaIdentity(
  authorization,
  { fetchImpl = fetch, firebaseApiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY } = {},
) {
  if (authorization === null || authorization === undefined) return null;

  const token = authorization.match(/^Bearer\s+([^\s]+)$/i)?.[1];
  if (!token) throw new PersonaAuthenticationError();
  if (!firebaseApiKey) {
    throw new PersonaGatewayUnavailableError(
      'Authentication verification is unavailable',
    );
  }

  let response;
  try {
    response = await fetchImpl(
      `https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=${encodeURIComponent(
        firebaseApiKey,
      )}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idToken: token }),
      },
    );
  } catch {
    throw new PersonaGatewayUnavailableError(
      'Authentication verification is unavailable',
    );
  }

  if (!response.ok) throw new PersonaAuthenticationError();
  const payload = await response.json();
  const user = payload?.users?.[0];
  if (!user?.localId || user.disabled === true) throw new PersonaAuthenticationError();

  const providers = Array.isArray(user.providerUserInfo) ? user.providerUserInfo : [];
  const isAuthenticated =
    Boolean(user.email) || providers.some((provider) => provider?.providerId);
  return isAuthenticated ? { uid: user.localId } : null;
}

export function personaLaneForIdentity(identity) {
  return identity ? AUTHENTICATED_LANE : UNAUTHENTICATED_LANE;
}

export async function requestPersonaChatStream({
  identity,
  messages,
  fetchImpl = fetch,
  gatewayUrl = process.env.OMI_LLM_GATEWAY_URL,
  gatewayToken = process.env.OMI_LLM_GATEWAY_SERVICE_TOKEN,
}) {
  if (!gatewayUrl?.trim() || !gatewayToken?.trim()) {
    throw new PersonaGatewayUnavailableError('The LLM gateway is not configured');
  }

  const lane = personaLaneForIdentity(identity);
  const headers = {
    Authorization: `Bearer ${gatewayToken.trim()}`,
    'Content-Type': 'application/json',
    'X-Omi-Service-Caller': 'omi-web',
    'X-Omi-LLM-Feature': identity ? 'persona_chat_premium' : 'persona_chat',
  };
  if (identity) headers['X-Omi-User-Uid'] = identity.uid;

  let response;
  try {
    response = await fetchImpl(`${gatewayUrl.replace(/\/+$/, '')}/v1/chat/completions`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        model: lane,
        messages,
        stream: true,
        temperature: 0.8,
        max_tokens: 2044,
      }),
    });
  } catch {
    throw new PersonaGatewayUnavailableError();
  }

  if (!response.ok || !response.body) throw new PersonaGatewayUnavailableError();
  return response;
}

export const PERSONA_CHAT_LANES = Object.freeze({
  authenticated: AUTHENTICATED_LANE,
  unauthenticated: UNAUTHENTICATED_LANE,
});
