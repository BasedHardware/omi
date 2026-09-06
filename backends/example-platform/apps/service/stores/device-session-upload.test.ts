import { expect, test } from "bun:test";
import { parseDeviceSessionUploadAudio, parseDeviceSessionUploadCreate } from "./device-session-upload";

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
  for (const value of [{ ...create, captureId: "legacy" }, { ...create, transcript: "invented" }, { ...create, codec: 256 }, { ...create, deviceId: "" }]) {
    expect(() => parseDeviceSessionUploadCreate(value)).toThrow();
  }
  for (const value of [{ chunkIndex: 65536, bytesBase64: "AQ==" }, { chunkIndex: 0, bytesBase64: "AR==" }, { chunkIndex: 0, bytesBase64: "" }, { chunkIndex: 0, bytesBase64: "AQ==", transcript: "invented" }]) {
    expect(() => parseDeviceSessionUploadAudio(value)).toThrow();
  }
});
