import type {OmiBackend} from './omiNativeTypes';

class MentorNotificationError extends Error {
  constructor() {
    super('Omi mentor notification settings are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new MentorNotificationError();
  }
  return value as Record<string, unknown>;
}

function requiredFrequency(value: unknown): number {
  const frequency =
    typeof value === 'string' && /^[+-]?[0-9]+$/.test(value)
      ? Number(value)
      : typeof value === 'number' && Number.isSafeInteger(value)
      ? value
      : null;
  if (frequency === null) {
    throw new MentorNotificationError();
  }
  return frequency;
}

export type OmiMentorNotificationSettings = {
  frequency: number;
};

export function parseOmiMentorNotificationSettings(
  body: string,
): OmiMentorNotificationSettings {
  const record = object(JSON.parse(body));
  return {frequency: requiredFrequency(record.frequency)};
}

export async function loadOmiMentorNotificationSettings(
  backend: OmiBackend,
): Promise<OmiMentorNotificationSettings | null> {
  const response = await backend.request({
    id: 'omi-mentor-notification-settings',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/mentor-notification-settings',
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return null;
  }
  try {
    return parseOmiMentorNotificationSettings(response.body);
  } catch {
    return null;
  }
}
