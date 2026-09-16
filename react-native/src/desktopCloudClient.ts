import type {OmiBackend} from './omiNative';
import {
  desktopAccountSettingUnavailableCopy,
  desktopAppsUnavailableCopy,
  desktopBackendConfigurationCopy,
  desktopBackendServiceCopy,
  desktopBackendUnauthorizedCopy,
  desktopBackendUnavailableCopy,
  desktopReadErrorCopy,
  usageLoadErrorCopy,
  subscriptionLoadErrorCopy,
  visibleDisplayText,
} from './desktopReadClient';

export type CloudApp = {
  id: string;
  name: string;
  description: string;
  category: string;
  author: string;
  enabled: boolean;
  uid: string | null;
  private: boolean;
  official: boolean;
  installs: number;
  ratingAvg?: number | null;
  ratingCount?: number | null;
  image?: string;
  hasExternalIntegration: boolean;
  connectedAccounts: string[];
};

export type ConnectorsSnapshot = {
  apps: CloudApp[];
  enabledIds: string[] | null;
  enabledError: string | null;
  ownerUid: string | null;
  ownerError: string | null;
};

export type CloudProfile = {
  uid: string;
  name: string | null;
  email: string | null;
  company: string | null;
  job: string | null;
  dataProtectionLevel: string | null;
};

export type CloudSubscription = {
  plan: string;
  status: string;
  transcriptionSecondsUsed: number | null;
  transcriptionSecondsLimit: number | null;
  wordsTranscribedUsed: number | null;
  wordsTranscribedLimit: number | null;
  insightsGainedUsed: number | null;
  insightsGainedLimit: number | null;
  chatQuotaUsed: number | null;
  chatQuotaUnit: string | null;
  chatQuestionsPerMonth: number | null;
  chatCostUsdPerMonth: number | null;
};

export type CloudUsageStats = {
  transcriptionSeconds: number;
  wordsTranscribed: number;
  insightsGained: number;
  memoriesCreated: number;
};

export type CloudLanguageOption = {
  code: string;
  name: string;
};

export type CloudWebhookStatus = {
  type: string;
  enabled: boolean | null;
  url: string | null;
};

export type AccountSettingsSnapshot = {
  profile: CloudProfile | null;
  profileError: string | null;
  subscription: CloudSubscription | null;
  subscriptionError: string | null;
  storeRecordingPermission: boolean | null;
  storeRecordingError: string | null;
  trainingOptedIn: boolean | null;
  trainingError: string | null;
  privateCloudSync: boolean | null;
  privateCloudSyncError: string | null;
  webhooks: CloudWebhookStatus[] | null;
  webhooksError: string | null;
  usage: CloudUsageStats | null;
  usageError: string | null;
  language: string | null;
  languageError: string | null;
  languageNames: CloudLanguageOption[] | null;
  languageNamesError: string | null;
};

function object(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} is malformed`);
  }
  return value as Record<string, unknown>;
}

function optionalString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function presentPaddedKnown(value: unknown, label: string): void {
  if (typeof value === 'string' && visibleDisplayText(value) !== value) {
    throw new Error(`${label} is malformed`);
  }
}

function optionalBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function optionalInteger(value: unknown): number | null {
  if (typeof value === 'string') {
    if (!/^[+-]?[0-9]+$/.test(value)) {
      return null;
    }
    return Number(value);
  }
  return typeof value === 'number' && Number.isSafeInteger(value)
    ? value
    : null;
}

function optionalFiniteNumber(value: unknown): number | null {
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      return null;
    }
    const parsed = Number(value);
    if (value === '' || !Number.isFinite(parsed)) {
      return null;
    }
    return parsed;
  }
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function parseJson(body: string | null, label: string): unknown {
  if (body === null) {
    throw new Error(`${label} returned an empty response`);
  }
  try {
    return JSON.parse(body) as unknown;
  } catch {
    throw new Error(`${label} returned invalid JSON`);
  }
}

function nestedErrorRetryable(body: string | null): boolean | null {
  if (body === null) {
    return null;
  }
  try {
    const parsed = JSON.parse(body) as {
      error?: {retryable?: unknown} | string;
    };
    if (parsed.error !== null && typeof parsed.error === 'object') {
      return typeof parsed.error.retryable === 'boolean'
        ? parsed.error.retryable
        : null;
    }
  } catch {}
  return null;
}

export function cloudErrorCanRetry(error: unknown): boolean {
  return !(
    error instanceof Error &&
    'retryable' in error &&
    (error as {retryable?: unknown}).retryable === false
  );
}

async function cloudRequest(
  backend: OmiBackend,
  id: string,
  method: 'GET' | 'POST',
  path: `/${string}`,
): Promise<{status: number; body: unknown}> {
  const response = await backend.request({id, method, path});
  if (response.status === 401) {
    const unauthorized = new Error(desktopBackendUnauthorizedCopy) as Error & {
      code: string;
    };
    unauthorized.code = 'unauthorized';
    throw unauthorized;
  }
  if (
    response.status !== 200 &&
    nestedErrorRetryable(response.body) === false
  ) {
    const unavailable = new Error(
      path.startsWith('/v1/apps')
        ? desktopAppsUnavailableCopy
        : path.startsWith('/v1/users/')
        ? desktopAccountSettingUnavailableCopy
        : desktopBackendUnavailableCopy,
    ) as Error & {retryable: boolean};
    unavailable.retryable = false;
    throw unavailable;
  }
  if (response.status !== 200) {
    throw new Error(`${id} failed (${response.status})`);
  }
  return {status: response.status, body: parseJson(response.body, id)};
}

export function parseCloudApp(value: unknown, label: string): CloudApp {
  const record = object(value, label);
  const id = typeof record.id === 'string' ? record.id : null;
  const name =
    record.name === undefined
      ? ''
      : typeof record.name === 'string'
      ? record.name
      : null;
  if (id === null || name === null) {
    throw new Error(`${label} is malformed`);
  }
  if (record.deleted === true) {
    throw new Error(`${label} is deleted`);
  }
  if (
    record.connected_accounts !== undefined &&
    record.connected_accounts !== null &&
    (!Array.isArray(record.connected_accounts) ||
      !record.connected_accounts.every(item => typeof item === 'string'))
  ) {
    throw new Error(`${label} connected_accounts are malformed`);
  }
  const ratingCount = optionalInteger(record.rating_count) ?? 0;
  return {
    id,
    name,
    description:
      typeof record.description === 'string' ? record.description : '',
    category: typeof record.category === 'string' ? record.category : '',
    author: typeof record.author === 'string' ? record.author : '',
    enabled: record.enabled === true,
    uid: optionalString(record.uid),
    private: record.private === true,
    official: record.official === true,
    installs: optionalInteger(record.installs) ?? 0,
    ratingAvg: optionalFiniteNumber(record.rating_avg),
    ratingCount: ratingCount >= 0 ? ratingCount : null,
    image: typeof record.image === 'string' ? record.image : '',
    hasExternalIntegration:
      record.external_integration !== null &&
      record.external_integration !== undefined,
    connectedAccounts: Array.isArray(record.connected_accounts)
      ? [...(record.connected_accounts as string[])]
      : [],
  };
}

export function parseCloudApps(value: unknown, label: string): CloudApp[] {
  if (!Array.isArray(value)) {
    throw new Error(`${label} is malformed`);
  }
  return value.flatMap((entry, index) => {
    try {
      return [parseCloudApp(entry, `${label} item ${index}`)];
    } catch (error) {
      if (
        error instanceof Error &&
        error.message === `${label} item ${index} is deleted`
      ) {
        return [];
      }
      throw error;
    }
  });
}

export function parseEnabledAppIds(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || !value.every(item => typeof item === 'string')) {
    throw new Error(`${label} is malformed`);
  }
  return [...value];
}

export function parseCloudProfile(value: unknown, label: string): CloudProfile {
  const record = object(value, label);
  const uid = optionalString(record.uid);
  if (uid === null) {
    throw new Error(`${label} is malformed`);
  }
  presentPaddedKnown(record.created_at, label);
  return {
    uid,
    name: optionalString(record.name),
    email: optionalString(record.email),
    company: optionalString(record.company),
    job: optionalString(record.job),
    dataProtectionLevel: optionalString(record.data_protection_level),
  };
}

function requiredUsageInteger(value: unknown, label: string): number {
  if (value === undefined) {
    return 0;
  }
  if (typeof value === 'string') {
    if (!/^[+-]?[0-9]+$/.test(value)) {
      throw new Error(`${label} is malformed`);
    }
    return Number(value);
  }
  if (typeof value === 'number' && Number.isSafeInteger(value)) {
    return value;
  }
  throw new Error(`${label} is malformed`);
}

export function parseCloudLanguage(
  value: unknown,
  label: string,
): string | null {
  const record = object(value, label);
  if (record.language === undefined || record.language === null) {
    return null;
  }
  if (typeof record.language !== 'string') {
    throw new Error(`${label} language is malformed`);
  }
  return record.language === '' ? null : record.language;
}

export function parseCloudLanguageNames(
  value: unknown,
  label: string,
): CloudLanguageOption[] | null {
  const record = object(value, label);
  if (!Array.isArray(record.languages)) {
    throw new Error(`${label} languages is malformed`);
  }
  if (record.languages.length === 0) {
    return null;
  }
  const names: CloudLanguageOption[] = [];
  record.languages.forEach((item, index) => {
    const entry = object(item, `${label} languages[${index}]`);
    if (typeof entry.code !== 'string' || typeof entry.name !== 'string') {
      throw new Error(`${label} languages[${index}] is malformed`);
    }
    names.push({code: entry.code, name: entry.name});
  });
  return names.length === 0 ? null : names;
}

const USAGE_PERIODS = ['today', 'monthly', 'yearly', 'all_time'] as const;

function parseUsageStats(
  value: unknown,
  label: string,
): CloudUsageStats {
  const stats = object(value, label);
  requiredUsageInteger(stats.speech_seconds, `${label} speech_seconds`);
  return {
    transcriptionSeconds: requiredUsageInteger(
      stats.transcription_seconds,
      `${label} transcription_seconds`,
    ),
    wordsTranscribed: requiredUsageInteger(
      stats.words_transcribed,
      `${label} words_transcribed`,
    ),
    insightsGained: requiredUsageInteger(
      stats.insights_gained,
      `${label} insights_gained`,
    ),
    memoriesCreated: requiredUsageInteger(
      stats.memories_created,
      `${label} memories_created`,
    ),
  };
}

export function parseCloudUsage(
  value: unknown,
  label: string,
): CloudUsageStats | null {
  const record = object(value, label);
  for (const key of USAGE_PERIODS) {
    const raw = record[key];
    if (raw === undefined || raw === null) {
      continue;
    }
    const prefix = key === 'today' ? label : `${label} ${key}`;
    parseUsageStats(raw, prefix);
  }
  if (record.history !== undefined && record.history !== null) {
    if (!Array.isArray(record.history)) {
      throw new Error(`${label} history is malformed`);
    }
    record.history.forEach((item, index) => {
      const point = object(item, `${label} history[${index}]`);
      if (typeof point.date !== 'string') {
        throw new Error(`${label} history[${index}] date is malformed`);
      }
      requiredUsageInteger(
        point.transcription_seconds,
        `${label} history[${index}] transcription_seconds`,
      );
      requiredUsageInteger(
        point.words_transcribed,
        `${label} history[${index}] words_transcribed`,
      );
      requiredUsageInteger(
        point.insights_gained,
        `${label} history[${index}] insights_gained`,
      );
      requiredUsageInteger(
        point.memories_created,
        `${label} history[${index}] memories_created`,
      );
      requiredUsageInteger(
        point.speech_seconds,
        `${label} history[${index}] speech_seconds`,
      );
    });
  }
  if (record.today === undefined || record.today === null) {
    return null;
  }
  return parseUsageStats(record.today, label);
}

function malformed(label: string): never {
  throw new Error(`${label} is malformed`);
}

function requiredPresentInteger(value: unknown, label: string): number {
  if (value === undefined || value === null) {
    malformed(label);
  }
  if (typeof value === 'string') {
    if (!/^[+-]?[0-9]+$/.test(value)) {
      malformed(label);
    }
    return Number(value);
  }
  if (typeof value === 'number' && Number.isSafeInteger(value)) {
    return value;
  }
  malformed(label);
}

function optionalNullableInteger(value: unknown, label: string): number | null {
  if (value === undefined || value === null) {
    return null;
  }
  return requiredPresentInteger(value, label);
}

function optionalBooleanDefault(
  value: unknown,
  label: string,
  defaultValue: boolean,
): boolean {
  if (value === undefined) {
    return defaultValue;
  }
  if (typeof value === 'boolean') {
    return value;
  }
  malformed(label);
}

function optionalNullableString(value: unknown, label: string): string | null {
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value === 'string') {
    return value;
  }
  malformed(label);
}

function optionalStringList(value: unknown, label: string): string[] {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value)) {
    malformed(label);
  }
  return value.map(item => {
    if (typeof item !== 'string') {
      malformed(label);
    }
    return item;
  });
}

function optionalFiniteDefault(
  value: unknown,
  label: string,
  defaultValue: number,
): number {
  if (value === undefined) {
    return defaultValue;
  }
  const parsed = optionalFiniteNumber(value);
  if (parsed === null) {
    malformed(label);
  }
  return parsed;
}

function optionalNullableFinite(value: unknown, label: string): number | null {
  if (value === undefined || value === null) {
    return null;
  }
  const parsed = optionalFiniteNumber(value);
  if (parsed === null) {
    malformed(label);
  }
  return parsed;
}

function parseSubscriptionPricingOption(value: unknown, label: string): void {
  const record = object(value, label);
  if (typeof record.id !== 'string') {
    malformed(label);
  }
  if (typeof record.price_string !== 'string') {
    malformed(label);
  }
  if (typeof record.title !== 'string') {
    malformed(label);
  }
  optionalNullableString(record.description, `${label} description`);
}

function parseSubscriptionPlan(value: unknown, label: string): void {
  const record = object(value, label);
  if (typeof record.id !== 'string') {
    malformed(label);
  }
  if (typeof record.title !== 'string') {
    malformed(label);
  }
  optionalNullableString(record.description, `${label} description`);
  optionalNullableString(record.eyebrow, `${label} eyebrow`);
  optionalNullableString(record.subtitle, `${label} subtitle`);
  optionalStringList(record.features, `${label} features`);
  optionalBooleanDefault(record.legacy, `${label} legacy`, false);
  if (record.prices === undefined) {
    return;
  }
  if (!Array.isArray(record.prices)) {
    malformed(`${label} prices`);
  }
  record.prices.forEach((item, index) => {
    parseSubscriptionPricingOption(item, `${label} prices[${index}]`);
  });
}

function parsePhoneCallQuota(value: unknown, label: string): void {
  const record = object(value, label);
  optionalStringList(record.allowed_countries, `${label} allowed_countries`);
  if (typeof record.has_access !== 'boolean') {
    malformed(label);
  }
  if (typeof record.is_paid !== 'boolean') {
    malformed(label);
  }
  optionalNullableInteger(
    record.max_duration_seconds,
    `${label} max_duration_seconds`,
  );
  optionalNullableInteger(record.monthly_limit, `${label} monthly_limit`);
  if (record.monthly_used !== undefined) {
    requiredPresentInteger(record.monthly_used, `${label} monthly_used`);
  }
  optionalNullableInteger(record.remaining, `${label} remaining`);
  optionalNullableInteger(record.reset_at, `${label} reset_at`);
}

function parseTranscriptionAllowance(value: unknown, label: string): void {
  const record = object(value, label);
  if (typeof record.mode !== 'string') {
    malformed(label);
  }
  if (record.reason !== undefined && typeof record.reason !== 'string') {
    malformed(`${label} reason`);
  }
  optionalNullableInteger(
    record.remaining_seconds,
    `${label} remaining_seconds`,
  );
}

function parsePlanLimits(
  value: unknown,
  label: string,
): Record<string, unknown> {
  if (value === undefined) {
    return {};
  }
  const record = object(value, label);
  optionalNullableFinite(
    record.chat_cost_usd_per_month,
    `${label} chat_cost_usd_per_month`,
  );
  optionalNullableInteger(
    record.chat_questions_per_month,
    `${label} chat_questions_per_month`,
  );
  optionalNullableInteger(record.insights_gained, `${label} insights_gained`);
  optionalNullableInteger(
    record.transcription_seconds,
    `${label} transcription_seconds`,
  );
  optionalNullableInteger(
    record.words_transcribed,
    `${label} words_transcribed`,
  );
  return record;
}

export function parseCloudSubscription(
  value: unknown,
  label: string,
): CloudSubscription {
  const record = object(value, label);
  if (record.available_plans !== undefined) {
    if (!Array.isArray(record.available_plans)) {
      malformed(`${label} available_plans`);
    }
    record.available_plans.forEach((item, index) => {
      parseSubscriptionPlan(item, `${label} available_plans[${index}]`);
    });
  }
  optionalBooleanDefault(
    record.chat_quota_allowed,
    `${label} chat_quota_allowed`,
    true,
  );
  optionalFiniteDefault(
    record.chat_quota_percent,
    `${label} chat_quota_percent`,
    0,
  );
  optionalNullableInteger(
    record.chat_quota_reset_at,
    `${label} chat_quota_reset_at`,
  );
  const chatQuotaUnit = optionalNullableString(
    record.chat_quota_unit,
    `${label} chat_quota_unit`,
  );
  const chatQuotaUsed = optionalFiniteDefault(
    record.chat_quota_used,
    `${label} chat_quota_used`,
    0,
  );
  optionalNullableInteger(
    record.desktop_grandfather_until,
    `${label} desktop_grandfather_until`,
  );
  const insightsGainedLimit = requiredPresentInteger(
    record.insights_gained_limit,
    `${label} insights_gained_limit`,
  );
  const insightsGainedUsed = requiredPresentInteger(
    record.insights_gained_used,
    `${label} insights_gained_used`,
  );
  const phoneCallQuota = optionalNullableObject(
    record.phone_call_quota,
    `${label} phone_call_quota`,
  );
  if (phoneCallQuota !== null) {
    parsePhoneCallQuota(phoneCallQuota, `${label} phone_call_quota`);
  }
  optionalBooleanDefault(
    record.show_subscription_ui,
    `${label} show_subscription_ui`,
    true,
  );
  const subscription = object(
    record.subscription,
    `${label} subscription`,
  );
  optionalBooleanDefault(
    subscription.cancel_at_period_end,
    `${label} subscription cancel_at_period_end`,
    false,
  );
  optionalNullableInteger(
    subscription.current_period_end,
    `${label} subscription current_period_end`,
  );
  optionalNullableInteger(
    subscription.current_period_start,
    `${label} subscription current_period_start`,
  );
  optionalNullableString(
    subscription.current_price_id,
    `${label} subscription current_price_id`,
  );
  optionalBooleanDefault(
    subscription.deprecated,
    `${label} subscription deprecated`,
    false,
  );
  optionalNullableString(
    subscription.deprecation_message,
    `${label} subscription deprecation_message`,
  );
  optionalStringList(
    subscription.features,
    `${label} subscription features`,
  );
  const limits = parsePlanLimits(
    subscription.limits,
    `${label} subscription limits`,
  );
  const plan =
    subscription.plan === undefined
      ? 'basic'
      : typeof subscription.plan === 'string'
      ? subscription.plan
      : null;
  const status =
    subscription.status === undefined
      ? 'active'
      : typeof subscription.status === 'string'
      ? subscription.status
      : null;
  if (plan === null || status === null) {
    malformed(label);
  }
  optionalNullableString(
    subscription.stripe_subscription_id,
    `${label} subscription stripe_subscription_id`,
  );
  const transcriptionAllowance = optionalNullableObject(
    record.transcription_allowance,
    `${label} transcription_allowance`,
  );
  if (transcriptionAllowance !== null) {
    parseTranscriptionAllowance(
      transcriptionAllowance,
      `${label} transcription_allowance`,
    );
  }
  return {
    plan,
    status,
    transcriptionSecondsUsed: requiredPresentInteger(
      record.transcription_seconds_used,
      `${label} transcription_seconds_used`,
    ),
    transcriptionSecondsLimit: requiredPresentInteger(
      record.transcription_seconds_limit,
      `${label} transcription_seconds_limit`,
    ),
    wordsTranscribedUsed: requiredPresentInteger(
      record.words_transcribed_used,
      `${label} words_transcribed_used`,
    ),
    wordsTranscribedLimit: requiredPresentInteger(
      record.words_transcribed_limit,
      `${label} words_transcribed_limit`,
    ),
    insightsGainedUsed,
    insightsGainedLimit,
    chatQuotaUsed,
    chatQuotaUnit,
    chatQuestionsPerMonth: optionalNullableInteger(
      limits.chat_questions_per_month,
      `${label} subscription limits chat_questions_per_month`,
    ),
    chatCostUsdPerMonth: optionalNullableFinite(
      limits.chat_cost_usd_per_month,
      `${label} subscription limits chat_cost_usd_per_month`,
    ),
  };
}

function optionalNullableObject(
  value: unknown,
  label: string,
): Record<string, unknown> | null {
  if (value === undefined || value === null) {
    return null;
  }
  return object(value, label);
}

export function parseStoreRecordingPermission(
  value: unknown,
  label: string,
): boolean {
  const record = object(value, label);
  const permission = optionalBoolean(record.store_recording_permission);
  if (permission === null) {
    throw new Error(`${label} is malformed`);
  }
  return permission;
}

export function parseTrainingOptIn(value: unknown, label: string): boolean {
  const record = object(value, label);
  const optedIn = optionalBoolean(record.opted_in);
  if (optedIn === null) {
    throw new Error(`${label} is malformed`);
  }
  return optedIn;
}

export function parsePrivateCloudSync(value: unknown, label: string): boolean {
  const record = object(value, label);
  const enabled = optionalBoolean(record.private_cloud_sync_enabled);
  if (enabled === null) {
    throw new Error(`${label} is malformed`);
  }
  return enabled;
}

export function parseWebhookStatuses(
  value: unknown,
  label: string,
): CloudWebhookStatus[] {
  const record = object(value, label);
  return Object.entries(record).flatMap(([type, entry]) => {
    if (typeof entry === 'boolean') {
      return [{type, enabled: entry, url: null}];
    }
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
      return [];
    }
    const item = entry as Record<string, unknown>;
    return [
      {
        type,
        enabled: optionalBoolean(item.enabled ?? item.status),
        url: optionalString(item.url),
      },
    ];
  });
}

function settledError(reason: unknown): string {
  return desktopReadErrorCopy(reason);
}

async function loadCloudSubscription(
  backend: OmiBackend,
): Promise<{value: CloudSubscription | null; error: string | null}> {
  let response: {status: number; body: string | null};
  try {
    response = await backend.request({
      id: 'desktop-subscription-read',
      method: 'GET',
      path: '/v1/users/me/subscription',
    });
  } catch {
    return {value: null, error: null};
  }
  if (response.status !== 200 || response.body === null) {
    return {value: null, error: null};
  }
  try {
    return {
      value: parseCloudSubscription(
        parseJson(response.body, 'desktop-subscription-read'),
        'Subscription response',
      ),
      error: null,
    };
  } catch {
    return {value: null, error: subscriptionLoadErrorCopy()};
  }
}

export async function loadConnectors(
  backend: OmiBackend,
): Promise<ConnectorsSnapshot> {
  const [appsResult, enabledResult] = await Promise.allSettled([
    cloudRequest(backend, 'desktop-apps-read', 'GET', '/v1/apps'),
    cloudRequest(backend, 'desktop-apps-enabled', 'GET', '/v1/apps/enabled'),
  ]);
  if (appsResult.status === 'rejected') {
    throw appsResult.reason;
  }
  const apps = parseCloudApps(appsResult.value.body, 'Apps response');
  const owner = await readOptional(async () =>
    parseCloudProfile(
      (
        await cloudRequest(
          backend,
          'desktop-connectors-profile',
          'GET',
          '/v1/users/profile',
        )
      ).body,
      'Profile response',
    ),
  );
  if (enabledResult.status === 'rejected') {
    return {
      apps: apps.map(app => ({
        ...app,
        enabled: false,
      })),
      enabledIds: null,
      enabledError: settledError(enabledResult.reason),
      ownerUid: owner.value?.uid ?? null,
      ownerError: owner.error,
    };
  }
  const enabledIds = parseEnabledAppIds(
    enabledResult.value.body,
    'Enabled apps response',
  );
  const enabled = new Set(enabledIds);
  return {
    apps: apps.map(app => ({
      ...app,
      enabled: enabled.has(app.id),
    })),
    enabledIds,
    enabledError: null,
    ownerUid: owner.value?.uid ?? null,
    ownerError: owner.error,
  };
}

async function readOptional<T>(
  load: () => Promise<T>,
): Promise<{value: T | null; error: string | null}> {
  try {
    return {value: await load(), error: null};
  } catch (error) {
    return {value: null, error: settledError(error)};
  }
}

export async function loadAccountSettings(
  backend: OmiBackend,
): Promise<AccountSettingsSnapshot> {
  const [
    profile,
    subscription,
    recording,
    training,
    privateCloudSync,
    webhooks,
    usage,
    language,
    languageNames,
  ] = await Promise.all([
    readOptional(async () =>
      parseCloudProfile(
        (
          await cloudRequest(
            backend,
            'desktop-profile-read',
            'GET',
            '/v1/users/profile',
          )
        ).body,
        'Profile response',
      ),
    ),
    loadCloudSubscription(backend),
    readOptional(async () =>
      parseStoreRecordingPermission(
        (
          await cloudRequest(
            backend,
            'desktop-recording-permission-read',
            'GET',
            '/v1/users/store-recording-permission',
          )
        ).body,
        'Recording permission response',
      ),
    ),
    readOptional(async () =>
      parseTrainingOptIn(
        (
          await cloudRequest(
            backend,
            'desktop-training-opt-in-read',
            'GET',
            '/v1/users/training-data-opt-in',
          )
        ).body,
        'Training opt-in response',
      ),
    ),
    readOptional(async () =>
      parsePrivateCloudSync(
        (
          await cloudRequest(
            backend,
            'desktop-private-cloud-sync-read',
            'GET',
            '/v1/users/private-cloud-sync',
          )
        ).body,
        'Private cloud sync response',
      ),
    ),
    readOptional(async () =>
      parseWebhookStatuses(
        (
          await cloudRequest(
            backend,
            'desktop-webhooks-read',
            'GET',
            '/v1/users/developer/webhooks/status',
          )
        ).body,
        'Webhooks response',
      ),
    ),
    readOptional(async () =>
      parseCloudUsage(
        (
          await cloudRequest(
            backend,
            'desktop-usage-read',
            'GET',
            '/v1/users/me/usage?period=today',
          )
        ).body,
        'Usage response',
      ),
    ),
    readOptional(async () =>
      parseCloudLanguage(
        (
          await cloudRequest(
            backend,
            'desktop-language-read',
            'GET',
            '/v1/users/language',
          )
        ).body,
        'Language response',
      ),
    ),
    readOptional(async () =>
      parseCloudLanguageNames(
        (
          await cloudRequest(
            backend,
            'desktop-language-names-read',
            'GET',
            '/v1/users/available-languages',
          )
        ).body,
        'Available languages response',
      ),
    ),
  ]);
  return {
    profile: profile.value,
    profileError: profile.error,
    subscription: subscription.value,
    subscriptionError: subscription.error,
    storeRecordingPermission: recording.value,
    storeRecordingError: recording.error,
    trainingOptedIn: training.value,
    trainingError: training.error,
    privateCloudSync: privateCloudSync.value,
    privateCloudSyncError: privateCloudSync.error,
    webhooks: webhooks.value,
    webhooksError: webhooks.error,
    usage: usage.value,
    usageError: usage.error == null ? null : usageLoadErrorCopy(),
    language: language.value,
    languageError: language.error,
    languageNames: languageNames.value,
    languageNamesError: languageNames.error,
  };
}

async function expectOk(
  backend: OmiBackend,
  id: string,
  path: `/${string}`,
): Promise<void> {
  const result = await cloudRequest(backend, id, 'POST', path);
  const record = object(result.body, `${id} response`);
  if (record.status !== 'ok') {
    throw new Error(`${id} failed`);
  }
}

export async function enableCloudApp(
  backend: OmiBackend,
  appId: string,
): Promise<void> {
  if (appId.length === 0) {
    throw new Error('App id is malformed');
  }
  await expectOk(
    backend,
    'desktop-app-enable',
    `/v1/apps/enable?app_id=${encodeURIComponent(appId)}`,
  );
}

export async function disableCloudApp(
  backend: OmiBackend,
  appId: string,
): Promise<void> {
  if (appId.length === 0) {
    throw new Error('App id is malformed');
  }
  await expectOk(
    backend,
    'desktop-app-disable',
    `/v1/apps/disable?app_id=${encodeURIComponent(appId)}`,
  );
}

export async function setStoreRecordingPermission(
  backend: OmiBackend,
  value: boolean,
): Promise<void> {
  await expectOk(
    backend,
    'desktop-recording-permission-write',
    `/v1/users/store-recording-permission?value=${value}`,
  );
}

export async function setPrivateCloudSync(
  backend: OmiBackend,
  value: boolean,
): Promise<void> {
  await expectOk(
    backend,
    'desktop-private-cloud-sync-write',
    `/v1/users/private-cloud-sync?value=${value}`,
  );
}

export async function optInTrainingData(backend: OmiBackend): Promise<void> {
  await expectOk(
    backend,
    'desktop-training-opt-in-write',
    '/v1/users/training-data-opt-in',
  );
}

export function cloudSessionUnavailableCopy(
  backend: OmiBackend | null | undefined,
): string {
  return backend === undefined || backend === null
    ? desktopBackendConfigurationCopy
    : desktopBackendUnauthorizedCopy;
}

export const serviceSettingsUnavailableCopy =
  'Account profile and usage are not available from this service yet.';
const serviceSettingsLoadFailureCopy =
  'Settings could not be loaded. Try again.';

export function serviceSettingsCanRetry(error: unknown): boolean {
  return cloudErrorCanRetry(error);
}

export function serviceSettingsErrorCopy(error: unknown): string {
  if (
    error instanceof Error &&
    error.message === serviceSettingsUnavailableCopy
  ) {
    return serviceSettingsUnavailableCopy;
  }
  const mapped = desktopReadErrorCopy(error);
  if (
    mapped === desktopBackendUnauthorizedCopy ||
    mapped === desktopBackendConfigurationCopy ||
    mapped === desktopBackendServiceCopy
  ) {
    return mapped;
  }
  return serviceSettingsLoadFailureCopy;
}

export function exploreApps(snapshot: ConnectorsSnapshot): CloudApp[] {
  return snapshot.apps;
}

export function installedApps(snapshot: ConnectorsSnapshot): CloudApp[] {
  if (snapshot.enabledIds === null) {
    return [];
  }
  return snapshot.apps.filter(app => app.enabled);
}

export function myApps(
  snapshot: ConnectorsSnapshot,
  uid: string | null,
): CloudApp[] {
  if (uid === null) {
    return [];
  }
  return snapshot.apps.filter(app => app.uid === uid);
}

export function serviceApps(snapshot: ConnectorsSnapshot): CloudApp[] {
  return snapshot.apps.filter(
    app => app.hasExternalIntegration || app.connectedAccounts.length > 0,
  );
}

export type ServiceSettingsSnapshot = {
  identity: {displayName: string; email: string} | null;
  entitlement: {
    planLabel: string;
    limitKey: string;
    used: number;
    limit: number | null;
    limitReached: boolean;
  } | null;
};

export async function loadServiceSettings(
  backend: OmiBackend,
): Promise<ServiceSettingsSnapshot> {
  const response = await backend.request({
    id: 'service-settings-read',
    method: 'GET',
    path: '/v1/settings',
  });
  if (response.status === 401) {
    const unauthorized = new Error(desktopBackendUnauthorizedCopy) as Error & {
      code: string;
    };
    unauthorized.code = 'unauthorized';
    throw unauthorized;
  }
  if (response.status === 503) {
    const unavailable = new Error(serviceSettingsUnavailableCopy) as Error & {
      retryable: boolean;
    };
    unavailable.retryable = nestedErrorRetryable(response.body) !== false;
    throw unavailable;
  }
  if (response.status !== 200) {
    throw new Error(serviceSettingsLoadFailureCopy);
  }
  const body = object(
    parseJson(response.body, 'service-settings-read'),
    'Settings response',
  );
  let identity: ServiceSettingsSnapshot['identity'] = null;
  if (body.identity !== null) {
    const value = object(body.identity, 'Connection identity');
    if (
      typeof value.displayName !== 'string' ||
      typeof value.email !== 'string'
    ) {
      throw new Error('Connection identity is malformed');
    }
    identity = {displayName: value.displayName, email: value.email};
  }
  if (body.entitlement === null) {
    return {identity, entitlement: null};
  }
  const entitlement = object(body.entitlement, 'Usage allowance');
  if (
    typeof entitlement.limitKey !== 'string' ||
    typeof entitlement.used !== 'number' ||
    !Number.isFinite(entitlement.used) ||
    (entitlement.limitKey === 'chat' &&
      !Number.isSafeInteger(entitlement.used)) ||
    entitlement.used < 0 ||
    (entitlement.limitReached !== undefined &&
      typeof entitlement.limitReached !== 'boolean') ||
    (entitlement.limit !== null &&
      (typeof entitlement.limit !== 'number' ||
        !Number.isFinite(entitlement.limit) ||
        (entitlement.limitKey === 'chat' &&
          !Number.isSafeInteger(entitlement.limit)) ||
        entitlement.limit < 0))
  ) {
    throw new Error('Usage allowance response is malformed');
  }
  return {
    identity,
    entitlement: {
      planLabel:
        typeof entitlement.planLabel === 'string' ? entitlement.planLabel : '',
      limitKey: entitlement.limitKey,
      used: entitlement.used,
      limit: entitlement.limit as number | null,
      limitReached: entitlement.limitReached === true,
    },
  };
}
