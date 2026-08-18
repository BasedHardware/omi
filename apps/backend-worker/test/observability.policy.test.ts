import { describe, expect, test } from "bun:test";

import {
  generationAdmittedEvent,
  gatewayFailureEvent,
  parseObservabilitySinkMode,
  requestCompletedEvent,
} from "../src/observability";

describe("observability sink configuration", () => {
  test("accepts only deliberate sink modes", () => {
    expect(parseObservabilitySinkMode("cloudflare_only")).toBe(
      "cloudflare_only"
    );
    expect(parseObservabilitySinkMode("better_stack")).toBe("better_stack");
    expect(parseObservabilitySinkMode("")).toBeNull();
    expect(parseObservabilitySinkMode("enabled")).toBeNull();
    expect(parseObservabilitySinkMode("better_stack ")).toBeNull();
  });
});

describe("operational telemetry redaction", () => {
  test("keeps request telemetry schema-stable and content-safe", () => {
    const event = requestCompletedEvent({
      requestId: "request-1",
      method: "POST",
      route: "/v1/chat-messages",
      status: 201,
      durationMs: 12,
    });

    expect(event).toEqual({
      event: "request_completed",
      request_id: "request-1",
      correlation_id: "request-1",
      method: "POST",
      route: "/v1/chat-messages",
      status: 201,
      duration_ms: 12,
    });
    expect(JSON.stringify(event)).not.toContain("authorization");
    expect(JSON.stringify(event)).not.toContain("prompt");
  });

  test("keeps gateway failures correlated without emitting transport details", () => {
    const event = gatewayFailureEvent({
      message: "gateway_http_error",
      correlationId: "generation-1",
      model: "openai/gpt-5.6-luna",
      status: 502,
    });

    expect(event).toEqual({
      event: "ai_gateway_failed",
      message: "gateway_http_error",
      correlation_id: "generation-1",
      model: "openai/gpt-5.6-luna",
      status: 502,
    });
    expect(JSON.stringify(event)).not.toContain("url");
    expect(JSON.stringify(event)).not.toContain("secret");
  });

  test("bridges a Worker request to asynchronous AI generation safely", () => {
    const event = generationAdmittedEvent({
      requestId: "request-1",
      generationId: "generation-1",
    });

    expect(event).toEqual({
      event: "generation_admitted",
      request_id: "request-1",
      correlation_id: "generation-1",
    });
    expect(JSON.stringify(event)).not.toContain("account");
    expect(JSON.stringify(event)).not.toContain("message");
  });
});
