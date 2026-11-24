import { moonshineJson } from '@tschk/moonshine-next/server';
import {
  isHardwareReferralCode,
  parseHardwareAttribution,
} from '@/lib/hardwareReferralContract';

const backends = { prod: 'https://api.omi.me', dev: 'https://api.omiapi.com' } as const;
const failure = (detail: string, status: number) =>
  moonshineJson({ detail }, { status, headers: { 'Cache-Control': 'no-store' } });

export async function POST(request: Request) {
  const authorization = request.headers.get('Authorization');
  if (!authorization || !/^Bearer \S+$/i.test(authorization))
    return failure('unauthorized', 401);
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return failure('invalid_request', 400);
  }
  if (
    !body ||
    typeof body !== 'object' ||
    !('code' in body) ||
    !('environment' in body) ||
    !isHardwareReferralCode(body.code) ||
    (body.environment !== 'prod' && body.environment !== 'dev') ||
    Object.keys(body).some((key) => key !== 'code' && key !== 'environment')
  )
    return failure('invalid_request', 400);
  try {
    const response = await fetch(
      `${backends[body.environment]}/v2/users/me/referral/campaign/attribution`,
      {
        method: 'POST',
        headers: { Authorization: authorization, 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: body.code }),
        signal: AbortSignal.timeout(10_000),
        redirect: 'error',
      },
    );
    const result: unknown = await response.json();
    if (response.status !== 200) {
      const detail =
        typeof result === 'object' &&
        result !== null &&
        'detail' in result &&
        typeof result.detail === 'string'
          ? result.detail
          : 'checkout_unavailable';
      const errors: Record<string, number> = {
        campaign_disabled: 503,
        checkout_activation_required: 503,
        invalid_referral_code: 404,
        self_referral: 409,
        attribution_conflict: 409,
        account_unavailable: 409,
        checkout_unavailable: 503,
      };
      if (errors[detail] === response.status) return failure(detail, response.status);
      return failure('checkout_unavailable', 503);
    }
    const attribution = parseHardwareAttribution(result);
    return attribution
      ? moonshineJson(attribution, { headers: { 'Cache-Control': 'no-store' } })
      : failure('checkout_unavailable', 503);
  } catch {
    return failure('checkout_unavailable', 503);
  }
}
