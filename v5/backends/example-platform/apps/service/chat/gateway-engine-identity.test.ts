import { describe, expect, test } from "bun:test";

import {
  UNKNOWN_GATEWAY_ENGINE_IDENTITY,
  bootGatewayKind,
  bootGatewayModel,
  parseGatewayReadyBody,
  probeGatewayEngineIdentity,
  stampForGatewayEngine,
} from "./gateway-engine-identity";

describe("gateway /ready identity", () => {
  test("canned local-test-gateway body stays unknown and is never real-provider", () => {
    const identity = parseGatewayReadyBody({
      schema: "omi.local-test-gateway.v1",
      disclosure: "local test gateway",
      production_model: false,
    });
    expect(identity).toEqual({
      schema: "omi.local-test-gateway.v1",
      realModelProxy: false,
      model: null,
    });
    expect(stampForGatewayEngine(identity, "default")).toEqual({
      tier: "unknown",
      adapter: "omi.local-test-gateway.v1",
      deterministic: false,
    });
    expect(bootGatewayKind(identity)).toBe("omi.local-test-gateway.v1");
    expect(bootGatewayModel(identity)).toBeNull();
  });

  test("real-model proxy body mints real-provider only from the boolean flag plus schema", () => {
    const identity = parseGatewayReadyBody({
      schema: "omi.local-model-gateway.v1",
      disclosure: "local real-model proxy",
      real_model_proxy: true,
      provider_host: "api.z.ai",
      model: "glm-4.7",
    });
    expect(identity).toEqual({
      schema: "omi.local-model-gateway.v1",
      realModelProxy: true,
      model: "glm-4.7",
    });
    expect(stampForGatewayEngine(identity, "default")).toEqual({
      tier: "real-provider",
      adapter: "omi.local-model-gateway.v1/glm-4.7",
      deterministic: false,
    });
    expect(bootGatewayKind(identity)).toBe("omi.local-model-gateway.v1");
    expect(bootGatewayModel(identity)).toBe("glm-4.7");
  });

  test("missing schema, stringy flags, and production_model never default to real", () => {
    expect(parseGatewayReadyBody({ real_model_proxy: true, model: "glm-4.7" }))
      .toEqual(UNKNOWN_GATEWAY_ENGINE_IDENTITY);
    expect(parseGatewayReadyBody({
      schema: "omi.local-model-gateway.v1",
      real_model_proxy: "true",
      model: "glm-4.7",
    })).toEqual({
      schema: "omi.local-model-gateway.v1",
      realModelProxy: false,
      model: "glm-4.7",
    });
    expect(stampForGatewayEngine(parseGatewayReadyBody({
      schema: "omi.local-model-gateway.v1",
      production_model: true,
      model: "glm-4.7",
    }), "default").tier).toBe("unknown");
    expect(parseGatewayReadyBody(null)).toEqual(UNKNOWN_GATEWAY_ENGINE_IDENTITY);
    expect(parseGatewayReadyBody("omi.local-model-gateway.v1")).toEqual(UNKNOWN_GATEWAY_ENGINE_IDENTITY);
    expect(bootGatewayKind(null)).toBe("none");
    expect(bootGatewayModel(null)).toBeNull();
    expect(stampForGatewayEngine(UNKNOWN_GATEWAY_ENGINE_IDENTITY, "injected")).toEqual({
      tier: "unknown",
      adapter: "omi-llm-gateway-injected-transport",
      deterministic: false,
    });
  });

  test("probe records unknown when /ready is absent or has no schema", async () => {
    const silent = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      fetch() { return new Response("not found", { status: 404 }); },
    });
    const schemaless = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      fetch() { return Response.json({ disclosure: "mystery" }); },
    });
    try {
      expect(await probeGatewayEngineIdentity(`http://127.0.0.1:${silent.port}`))
        .toEqual(UNKNOWN_GATEWAY_ENGINE_IDENTITY);
      expect(await probeGatewayEngineIdentity(`http://127.0.0.1:${schemaless.port}`))
        .toEqual(UNKNOWN_GATEWAY_ENGINE_IDENTITY);
      expect(await probeGatewayEngineIdentity("not-a-url")).toEqual(UNKNOWN_GATEWAY_ENGINE_IDENTITY);
    } finally {
      silent.stop(true);
      schemaless.stop(true);
    }
  });

  test("probe reads the gateway's declared schema from /ready", async () => {
    const server = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      fetch() {
        return Response.json({
          schema: "omi.local-test-gateway.v1",
          disclosure: "local test gateway",
          production_model: false,
        });
      },
    });
    try {
      expect(await probeGatewayEngineIdentity(`http://127.0.0.1:${server.port}`)).toEqual({
        schema: "omi.local-test-gateway.v1",
        realModelProxy: false,
        model: null,
      });
    } finally {
      server.stop(true);
    }
  });
});
