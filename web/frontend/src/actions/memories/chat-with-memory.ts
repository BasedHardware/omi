'use server';

import { createHmac } from 'node:crypto';
import { isIP } from 'node:net';
import { headers } from 'next/headers';
import envConfig from '@/src/constants/envConfig';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatWithMemoryRequest {
  conversationId: string;
  question: string;
  history: ChatMessage[];
  userIdToken?: string;
}

export type ChatLimitReason =
  | 'free_questions_exhausted'
  | 'conversation_daily'
  | 'global_minute'
  | 'global_daily'
  | 'subject_minute'
  | 'signed_user_daily'
  | 'signed_global_daily'
  | 'no_omi_account'
  | 'invalid_token';

export type ChatWithMemoryResponse =
  | { status: 'ok'; message: string; remainingFreeQuestions?: number }
  | {
      status: 'rate_limited';
      message: string;
      reason: ChatLimitReason;
      retryAfterSeconds?: number;
    }
  | { status: 'unavailable'; message: string };

const FRONTEND_CLOUD_RUN_SERVICE = 'frontend';
const HMAC_KEY_ENV_VAR = 'PUBLIC_SHARED_CONVERSATION_CHAT_IP_HMAC_KEY';
const AUDIENCE_ENV_VAR = 'PUBLIC_SHARED_CONVERSATION_CHAT_FRONTEND_AUDIENCE';
const METADATA_IDENTITY_URL =
  'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity';
const UNAVAILABLE: ChatWithMemoryResponse = {
  status: 'unavailable',
  message: 'Chat with this shared conversation is currently unavailable.',
};

function googleLoadBalancerClientIp(forwardedFor: string | null): string | null {
  if (process.env.K_SERVICE !== FRONTEND_CLOUD_RUN_SERVICE || !forwardedFor) {
    return null;
  }

  // Google External Application Load Balancing appends
  // <client-ip>,<load-balancer-ip>. Earlier values are caller-controlled.
  const addresses = forwardedFor.split(',').map((address) => address.trim());
  if (addresses.length < 2) return null;
  const clientIp = addresses.at(-2);
  const loadBalancerIp = addresses.at(-1);
  if (
    !clientIp ||
    !loadBalancerIp ||
    isIP(clientIp) === 0 ||
    isIP(loadBalancerIp) === 0
  ) {
    return null;
  }
  return clientIp;
}

async function mintIdentityToken(audience: string): Promise<string | null> {
  const url = new URL(METADATA_IDENTITY_URL);
  url.searchParams.set('audience', audience);
  url.searchParams.set('format', 'full');
  const response = await fetch(url, {
    headers: { 'Metadata-Flavor': 'Google' },
    cache: 'no-store',
    signal: AbortSignal.timeout(3_000),
  });
  if (!response.ok) return null;
  const token = (await response.text()).trim();
  return token || null;
}

function retryAfterSeconds(value: string | null): number | undefined {
  if (!value || !/^\d+$/.test(value)) return undefined;
  const seconds = Number.parseInt(value, 10);
  return seconds >= 1 && seconds <= 86400 ? seconds : undefined;
}

const LIMIT_REASONS = new Set<ChatLimitReason>([
  'free_questions_exhausted',
  'conversation_daily',
  'global_minute',
  'global_daily',
  'subject_minute',
  'signed_user_daily',
  'signed_global_daily',
  'no_omi_account',
  'invalid_token',
]);

function parsedReason(payload: unknown): ChatLimitReason | null {
  if (!payload || typeof payload !== 'object' || !('reason' in payload)) return null;
  const reason = payload.reason;
  return typeof reason === 'string' && LIMIT_REASONS.has(reason as ChatLimitReason)
    ? (reason as ChatLimitReason)
    : null;
}

export default async function chatWithMemory(
  data: ChatWithMemoryRequest,
): Promise<ChatWithMemoryResponse> {
  try {
    const backendUrl = envConfig.API_URL?.replace(/\/$/, '');
    const hmacKey = process.env[HMAC_KEY_ENV_VAR];
    const audience = process.env[AUDIENCE_ENV_VAR];
    const requestHeaders = await headers();
    const clientIp = googleLoadBalancerClientIp(requestHeaders.get('x-forwarded-for'));
    if (!backendUrl || !hmacKey || !audience || !clientIp) return UNAVAILABLE;

    const identityToken = await mintIdentityToken(audience);
    if (!identityToken) return UNAVAILABLE;
    const opaqueSubject = createHmac('sha256', hmacKey).update(clientIp).digest('hex');

    const response = await fetch(`${backendUrl}/v1/conversations/shared/chat`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${identityToken}`,
        'Content-Type': 'application/json',
        'X-Omi-Public-Chat-Subject': opaqueSubject,
        ...(data.userIdToken ? { 'X-Omi-User-Id-Token': data.userIdToken } : {}),
      },
      body: JSON.stringify({
        conversation_id: data.conversationId,
        question: data.question,
        history: data.history.slice(-8),
      }),
      cache: 'no-store',
      signal: AbortSignal.timeout(20_000),
    });

    if (response.status === 429 || response.status === 403 || response.status === 401) {
      const payload: unknown = await response.json().catch(() => null);
      const reason = parsedReason(payload);
      if (!reason) return UNAVAILABLE;
      const retryAfter = retryAfterSeconds(response.headers.get('Retry-After'));
      return {
        status: 'rate_limited',
        message: 'Keep asking with Omi.',
        reason,
        ...(retryAfter ? { retryAfterSeconds: retryAfter } : {}),
      };
    }
    if (response.status === 503 || !response.ok) return UNAVAILABLE;

    const payload: unknown = await response.json();
    if (
      typeof payload !== 'object' ||
      payload === null ||
      !('message' in payload) ||
      typeof payload.message !== 'string' ||
      !payload.message.trim()
    ) {
      return UNAVAILABLE;
    }
    const remaining =
      'remaining_free_questions' in payload ? payload.remaining_free_questions : null;
    return {
      status: 'ok',
      message: payload.message.trim(),
      ...(typeof remaining === 'number' &&
      Number.isInteger(remaining) &&
      remaining >= 0 &&
      remaining <= 3
        ? { remainingFreeQuestions: remaining }
        : {}),
    };
  } catch {
    return UNAVAILABLE;
  }
}
