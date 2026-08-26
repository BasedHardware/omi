import type {OmiBackend} from './omiNative';
import {
  desktopBackendConfigurationCopy,
  desktopBackendUnauthorizedCopy,
  desktopReadErrorCopy,
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
  hasExternalIntegration: boolean;
  connectedAccounts: string[];
};

export type ConnectorsSnapshot = {
  apps: CloudApp[];
  enabledIds: string[] | null;
  enabledError: string | null;
  ownerUid: string | null;
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

function optionalBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function optionalInteger(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value)
    ? value
    : null;
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
  if (response.status !== 200) {
    throw new Error(`${id} failed (${response.status})`);
  }
  return {status: response.status, body: parseJson(response.body, id)};
}

export function parseCloudApp(value: unknown, label: string): CloudApp {
  const record = object(value, label);
  const id = optionalString(record.id);
  const name = optionalString(record.name);
  if (id === null || name === null) {
    throw new Error(`${label} is malformed`);
  }
  if (record.deleted === true) {
    throw new Error(`${label} is deleted`);
  }
  if (
    record.connected_accounts !== undefined &&
    (!Array.isArray(record.connected_accounts) ||
      !record.connected_accounts.every(item => typeof item === 'string'))
  ) {
    throw new Error(`${label} connected_accounts are malformed`);
  }
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
  return {
    uid,
    name: optionalString(record.name),
    email: optionalString(record.email),
    company: optionalString(record.company),
    job: optionalString(record.job),
    dataProtectionLevel: optionalString(record.data_protection_level),
  };
}

export function parseCloudSubscription(
  value: unknown,
  label: string,
): CloudSubscription {
  const record = object(value, label);
  const subscription =
    record.subscription === undefined
      ? record
      : object(record.subscription, `${label} subscription`);
  const plan = optionalString(subscription.plan);
  const status = optionalString(subscription.status);
  if (plan === null || status === null) {
    throw new Error(`${label} is malformed`);
  }
  return {
    plan,
    status,
    transcriptionSecondsUsed: optionalInteger(
      record.transcription_seconds_used,
    ),
    transcriptionSecondsLimit: optionalInteger(
      record.transcription_seconds_limit,
    ),
  };
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
  return Object.entries(record).map(([type, entry]) => {
    if (typeof entry === 'boolean') {
      return {type, enabled: entry, url: null};
    }
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
      throw new Error(`${label} ${type} is malformed`);
    }
    const item = entry as Record<string, unknown>;
    return {
      type,
      enabled: optionalBoolean(item.enabled ?? item.status),
      url: optionalString(item.url),
    };
  });
}

function settledError(reason: unknown): string {
  return desktopReadErrorCopy(reason);
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
      apps,
      enabledIds: null,
      enabledError: settledError(enabledResult.reason),
      ownerUid: owner.value?.uid ?? null,
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
      enabled: app.enabled || enabled.has(app.id),
    })),
    enabledIds,
    enabledError: null,
    ownerUid: owner.value?.uid ?? null,
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
    readOptional(async () =>
      parseCloudSubscription(
        (
          await cloudRequest(
            backend,
            'desktop-subscription-read',
            'GET',
            '/v1/users/me/subscription',
          )
        ).body,
        'Subscription response',
      ),
    ),
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

export function exploreApps(snapshot: ConnectorsSnapshot): CloudApp[] {
  return snapshot.apps;
}

export function installedApps(snapshot: ConnectorsSnapshot): CloudApp[] {
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
