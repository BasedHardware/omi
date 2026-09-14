import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

class FirmwareError extends Error {
  constructor() {
    super('Omi firmware is malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new FirmwareError();
  }
  return value as Record<string, unknown>;
}

function firmwareChangelog(value: unknown): string[] | undefined {
  if (value === undefined || value === null || typeof value === 'string') {
    return undefined;
  }
  if (!Array.isArray(value)) {
    return undefined;
  }
  const changelog: string[] = [];
  for (const raw of value) {
    if (typeof raw !== 'string') {
      continue;
    }
    const copy = visibleDisplayText(raw);
    if (copy !== '') {
      changelog.push(copy);
    }
  }
  return changelog.length === 0 ? undefined : changelog;
}

export type FirmwareLatestQuery = {
  model: string;
  firmware: string;
  hardware: string;
  manufacturer: string;
};

export type FirmwareLatestDetails = {
  version: string;
  draft: boolean;
  minVersion: string | null;
  changelog?: string[];
};

export function firmwareLatestQuery(information?: {
  model?: string;
  firmware?: string;
  hardware?: string;
  manufacturer?: string;
}): FirmwareLatestQuery | null {
  const model = visibleDisplayText(information?.model ?? '');
  const firmware = visibleDisplayText(information?.firmware ?? '');
  const hardware = visibleDisplayText(information?.hardware ?? '');
  const manufacturer = visibleDisplayText(information?.manufacturer ?? '');
  if (
    model === '' ||
    firmware === '' ||
    hardware === '' ||
    manufacturer === ''
  ) {
    return null;
  }
  return {model, firmware, hardware, manufacturer};
}

export function parseOmiLatestFirmware(
  body: string,
): FirmwareLatestDetails | null {
  const record = object(JSON.parse(body));
  if (record.draft !== undefined && typeof record.draft !== 'boolean') {
    throw new FirmwareError();
  }
  const draft = record.draft === true;
  if (record.version === undefined || record.version === null) {
    return null;
  }
  if (typeof record.version !== 'string') {
    throw new FirmwareError();
  }
  const version = visibleDisplayText(record.version);
  if (version === '') {
    return null;
  }
  if (
    record.min_version !== undefined &&
    record.min_version !== null &&
    typeof record.min_version !== 'string'
  ) {
    throw new FirmwareError();
  }
  const minVersion =
    typeof record.min_version === 'string'
      ? visibleDisplayText(record.min_version)
      : '';
  const changelog = firmwareChangelog(record.changelog);
  return {
    version,
    draft,
    minVersion: minVersion === '' ? null : minVersion,
    ...(changelog === undefined ? {} : {changelog}),
  };
}

export async function loadOmiLatestFirmware(
  backend: OmiBackend,
  query: FirmwareLatestQuery,
  signal?: AbortSignal,
): Promise<FirmwareLatestDetails | null> {
  if (signal?.aborted) {
    return null;
  }
  const path =
    `/v2/firmware/latest?device_model=${encodeURIComponent(query.model)}` +
    `&firmware_revision=${encodeURIComponent(query.firmware)}` +
    `&hardware_revision=${encodeURIComponent(query.hardware)}` +
    `&manufacturer_name=${encodeURIComponent(query.manufacturer)}`;
  const response = await backend.request({
    id: 'omi-firmware-latest',
    method: 'GET',
    expectedApiContract: 'omi',
    path,
  });
  if (signal?.aborted) {
    return null;
  }
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return null;
  }
  try {
    return parseOmiLatestFirmware(response.body);
  } catch {
    return null;
  }
}
