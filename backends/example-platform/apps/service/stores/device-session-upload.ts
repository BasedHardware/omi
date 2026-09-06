import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";

export interface DeviceSessionUpload {
  readonly id: string;
  readonly deviceId: string;
  readonly deviceName: string | null;
  readonly codec: number;
  readonly state: "open" | "complete";
  readonly byteCount: number;
  readonly chunkCount: number;
  readonly startedAt: number;
  readonly endedAt: number | null;
}
export interface DeviceSessionUploadCreate {
  readonly captureId: string;
  readonly deviceId: string;
  readonly deviceName: string | null;
  readonly codec: number;
}
export interface DeviceSessionUploadRepository {
  open(context: AuthorizedLedgerWriteContext, input: DeviceSessionUploadCreate): Promise<DeviceSessionUpload>;
  read(context: AuthorizedLedgerWriteContext, id: string): Promise<DeviceSessionUpload | null>;
  append(context: AuthorizedLedgerWriteContext, id: string, index: number, bytes: Uint8Array): Promise<DeviceSessionUpload | null>;
  complete(context: AuthorizedLedgerWriteContext, id: string): Promise<DeviceSessionUpload | null>;
}
export const DEVICE_UPLOAD_MAX_BODY = 1_398_256;
export const DEVICE_UPLOAD_SESSION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const record = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new TypeError("invalid_device_request");
  return value as Record<string, unknown>;
};
const bounded = (value: unknown, limit: number): value is string => typeof value === "string" && value.length > 0 && value.length <= limit && !value.includes("\0");
export function parseDeviceSessionUploadCreate(value: unknown): DeviceSessionUploadCreate {
  const input = record(value);
  if (Object.keys(input).some(key => !["captureId", "deviceId", "deviceName", "codec"].includes(key))
    || typeof input.captureId !== "string" || !DEVICE_UPLOAD_SESSION_ID.test(input.captureId)
    || !bounded(input.deviceId, 128)
    || (input.deviceName !== undefined && input.deviceName !== null && !bounded(input.deviceName, 256))
    || !Number.isInteger(input.codec) || (input.codec as number) < 0 || (input.codec as number) > 255) throw new TypeError("invalid_device_request");
  return { captureId: input.captureId, deviceId: input.deviceId, deviceName: input.deviceName as string | null ?? null, codec: input.codec as number };
}
export function parseDeviceSessionUploadAudio(value: unknown): { index: number; bytes: Uint8Array } {
  const input = record(value);
  if (Object.keys(input).sort().join(",") !== "bytesBase64,chunkIndex"
    || !Number.isSafeInteger(input.chunkIndex) || (input.chunkIndex as number) < 0 || (input.chunkIndex as number) > 65535
    || typeof input.bytesBase64 !== "string" || input.bytesBase64.length > 1_398_104
    || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(input.bytesBase64)) throw new TypeError("invalid_device_request");
  const bytes = Buffer.from(input.bytesBase64, "base64");
  if (bytes.length < 1 || bytes.length > 1_048_576 || bytes.toString("base64") !== input.bytesBase64) throw new TypeError("invalid_device_request");
  return { index: input.chunkIndex as number, bytes };
}
