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
  appendBatch(context: AuthorizedLedgerWriteContext, id: string, chunks: readonly DeviceSessionUploadChunk[]): Promise<DeviceSessionUpload | null>;
  complete(context: AuthorizedLedgerWriteContext, id: string): Promise<DeviceSessionUpload | null>;
}
export interface DeviceSessionUploadChunk {
  readonly index: number;
  readonly bytes: Uint8Array;
}
export const DEVICE_UPLOAD_MAX_BATCH_CHUNKS = 128;
export const DEVICE_UPLOAD_MAX_BATCH_BYTES = 1_048_576;
export const DEVICE_UPLOAD_MAX_BATCH_BODY = 2_097_152;
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
export function validateDeviceSessionUploadBatch(chunks: readonly DeviceSessionUploadChunk[]): void {
  if (!Array.isArray(chunks) || chunks.length < 1 || chunks.length > DEVICE_UPLOAD_MAX_BATCH_CHUNKS) throw new TypeError("invalid_device_request");
  let total = 0;
  for (let position = 0; position < chunks.length; position += 1) {
    const chunk = chunks[position];
    if (!chunk || !Number.isSafeInteger(chunk.index) || chunk.index < 0 || chunk.index > 65535
      || !(chunk.bytes instanceof Uint8Array) || chunk.bytes.length < 1
      || (position > 0 && chunk.index !== chunks[position - 1]!.index + 1)) throw new TypeError("invalid_device_request");
    total += chunk.bytes.length;
    if (total > DEVICE_UPLOAD_MAX_BATCH_BYTES) throw new TypeError("invalid_device_request");
  }
}
export function parseDeviceSessionUploadBatch(value: unknown): readonly DeviceSessionUploadChunk[] {
  const input = record(value);
  if (Object.keys(input).join(",") !== "chunks" || !Array.isArray(input.chunks)
    || input.chunks.length < 1 || input.chunks.length > DEVICE_UPLOAD_MAX_BATCH_CHUNKS) throw new TypeError("invalid_device_request");
  const chunks: DeviceSessionUploadChunk[] = [];
  for (const value of input.chunks) {
    chunks.push(parseDeviceSessionUploadAudio(value));
    validateDeviceSessionUploadBatch(chunks);
  }
  return chunks;
}
