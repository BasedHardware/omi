/**
 * Unit tests for mapGeminiErrorToMessage — the Gemini error → human message
 * mapping function used by companionAssistant.ts.
 */
import { describe, it, expect } from "vitest";
import { mapGeminiErrorToMessage } from "./companionAssistant";

describe("mapGeminiErrorToMessage", () => {
  it("returns an API-key message for 401", () => {
    const msg = mapGeminiErrorToMessage(401, new Error("Unauthorized"));
    expect(msg).toBe("AI key missing or invalid — check Settings.");
  });

  it("returns a rate-limit message for 429", () => {
    const msg = mapGeminiErrorToMessage(429, new Error("Too Many Requests"));
    expect(msg).toBe("AI rate limit hit — wait a moment and try again.");
  });

  it("returns a server-error message for 5xx codes", () => {
    const msg500 = mapGeminiErrorToMessage(500, new Error("Internal Server Error"));
    expect(msg500).toBe("AI service error — try again shortly.");

    const msg503 = mapGeminiErrorToMessage(503, new Error("Service Unavailable"));
    expect(msg503).toBe("AI service error — try again shortly.");
  });

  it("returns a generic retry message for null status (network error)", () => {
    const msg = mapGeminiErrorToMessage(null, new Error("Failed to fetch"));
    // "Failed to fetch" matches the network/fetch pattern
    expect(msg).toBe("Couldn't reach AI — check your connection.");
  });

  it("returns a timeout message for timeout errors", () => {
    const msg = mapGeminiErrorToMessage(null, new Error("Request timed out"));
    expect(msg).toBe("Request timed out — check your connection.");
  });

  it("returns a generic message for unrecognised 4xx errors", () => {
    const msg = mapGeminiErrorToMessage(403, new Error("Forbidden"));
    expect(msg).toBe("AI request failed — please try again.");
  });
});
