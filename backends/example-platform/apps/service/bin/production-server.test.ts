import { expect, test } from "bun:test";
import { requestTimeoutMilliseconds } from "./production-server";

test("transcription has a bounded provider budget while other routes retain their deadline", () => {
  expect(requestTimeoutMilliseconds("POST", "/v1/device-sessions/id/transcribe")).toBe(135000);
  expect(requestTimeoutMilliseconds("GET", "/v1/device-sessions/id/transcribe")).toBe(25000);
  expect(requestTimeoutMilliseconds("POST", "/v1/device-sessions/id/complete")).toBe(25000);
  expect(requestTimeoutMilliseconds("POST", "/v1/device-sessions//transcribe")).toBe(25000);
});
