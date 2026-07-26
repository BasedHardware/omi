import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ADMIN_LLM_LANES,
  AdminLlmGatewayUnavailableError,
  invokeAdminLlmGateway,
} from "@/lib/llm-gateway";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("admin LLM gateway", () => {
  it("sends only the trusted canonical lane", async () => {
    vi.stubEnv("OMI_LLM_GATEWAY_URL", "http://gateway.internal/");
    vi.stubEnv("OMI_LLM_GATEWAY_SERVICE_TOKEN", "service-token");
    const requests: Array<[RequestInfo | URL, RequestInit | undefined]> = [];
    const fetchImpl: typeof fetch = async (input, init) => {
      requests.push([input, init]);
      return Response.json({
        choices: [{ message: { content: '{"ok":true}' } }],
      });
    };

    const result = await invokeAdminLlmGateway(
      {
        lane: ADMIN_LLM_LANES.notificationRegeneration,
        feature: "admin_notification_regeneration",
        messages: [{ role: "user", content: "generate" }],
      },
      fetchImpl,
    );

    expect(result).toBe('{"ok":true}');
    expect(requests).toHaveLength(1);
    const [url, init] = requests[0];
    expect(url).toBe("http://gateway.internal/v1/chat/completions");
    expect(JSON.parse(String(init?.body)).model).toBe(
      "omi:auto:proactive-notification",
    );
    expect(init?.headers).toMatchObject({
      "X-Omi-Service-Caller": "omi-admin-dashboard",
      "X-Omi-LLM-Feature": "admin_notification_regeneration",
    });
  });

  it("fails closed when the gateway is unavailable", async () => {
    vi.stubEnv("OMI_LLM_GATEWAY_URL", "http://gateway.internal");
    vi.stubEnv("OMI_LLM_GATEWAY_SERVICE_TOKEN", "service-token");
    let calls = 0;
    const fetchImpl: typeof fetch = async () => {
      calls += 1;
      return new Response("{}", { status: 503 });
    };

    await expect(
      invokeAdminLlmGateway(
        {
          lane: ADMIN_LLM_LANES.chatLab,
          feature: "admin_chat_lab",
          messages: [{ role: "user", content: "evaluate" }],
        },
        fetchImpl,
      ),
    ).rejects.toBeInstanceOf(AdminLlmGatewayUnavailableError);
    expect(calls).toBe(1);
  });
});
