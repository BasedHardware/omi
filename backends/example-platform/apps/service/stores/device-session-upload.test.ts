import { expect, test } from "bun:test";
import { parseDeviceSessionUploadAudio, parseDeviceSessionUploadBatch, parseDeviceSessionUploadCreate } from "./device-session-upload";

test("audio batches preserve packet boundaries and reject gaps and aggregate limits", () => {
  const chunks = Array.from({ length: 128 }, (_, index) => ({ chunkIndex: 65408 + index, bytesBase64: Buffer.alloc(8192, index).toString("base64") }));
  const parsed = parseDeviceSessionUploadBatch({ chunks });
  expect(parsed.length).toBe(128);
  expect(parsed.at(-1)?.index).toBe(65535);
  expect(parsed.at(-1)?.bytes).toEqual(Buffer.alloc(8192, 127));
  for (const value of [
    { chunks: [] }, { chunks: [...chunks, chunks[0]] },
    { chunks: [chunks[0], chunks[0]] }, { chunks: [chunks[0], chunks[2]] },
    { chunks: [{ chunkIndex: 0, bytesBase64: Buffer.alloc(1048576).toString("base64") }, { chunkIndex: 1, bytesBase64: "AQ==" }] },
    { chunks: [chunks[0]], text: "substituted" },
  ]) expect(() => parseDeviceSessionUploadBatch(value)).toThrow();
});

const create = { captureId: "ad99598c-36a8-4e12-a428-63d0a3e06170", deviceId: "omi-device", codec: 20 };
test("device capture wire preserves stable UUID and accepts the native indexed byte envelope", () => {
  expect(parseDeviceSessionUploadCreate(create)).toEqual({ ...create, deviceName: null });
  const bytes = Uint8Array.of(0, 255, 128, 1);
  const parsed = parseDeviceSessionUploadAudio({ chunkIndex: 0, bytesBase64: Buffer.from(bytes).toString("base64") });
  expect(parsed.index).toBe(0);
  expect([...parsed.bytes]).toEqual([...bytes]);
  expect(parseDeviceSessionUploadAudio({ chunkIndex: 65535, bytesBase64: Buffer.alloc(1048576, 1).toString("base64") }).bytes.length).toBe(1048576);
});
test("invalid identities, substituted transcript text and ambiguous audio encoding are refused", () => {
  for (const value of [{ ...create, captureId: "legacy" }, { ...create, transcript: "invented" }, { ...create, codec: 256 }, { ...create, deviceId: "" }, { ...create, deviceId: "omi\0device" }, { ...create, deviceName: "Omi\0" }]) {
    expect(() => parseDeviceSessionUploadCreate(value)).toThrow();
  }
  for (const value of [{ chunkIndex: 65536, bytesBase64: "AQ==" }, { chunkIndex: 0, bytesBase64: "AR==" }, { chunkIndex: 0, bytesBase64: "" }, { chunkIndex: 0, bytesBase64: "AQ==", transcript: "invented" }]) {
    expect(() => parseDeviceSessionUploadAudio(value)).toThrow();
  }
});

test("capture provenance preserves absence and exact millisecond bounds", () => {
  expect(parseDeviceSessionUploadCreate(create)).not.toHaveProperty("capturedAtMs");
  for (const capturedAtMs of [0, 1, 8640000000000000]) {
    expect(parseDeviceSessionUploadCreate({ ...create, capturedAtMs }).capturedAtMs).toBe(capturedAtMs);
  }
  for (const capturedAtMs of [null, -1, 0.5, NaN, Infinity, "1", 8640000000000001]) {
    expect(() => parseDeviceSessionUploadCreate({ ...create, capturedAtMs })).toThrow();
  }
});
