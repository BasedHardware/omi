import { beforeAll, describe, expect, mock, test } from "bun:test";

import {
  DESKTOP_AUTH_LIFETIME_MS,
  DESKTOP_AUTH_START_RATE_LIMIT,
  browserUrlFor,
  createFirebaseCustomToken,
  deriveSessionId,
  isValidConfirmationCode,
  isValidSessionValue,
  verifierChallenge,
} from "../src/desktop-auth";
import { applyAccountScopedIds, createD1Mock } from "./d1-mock";

let handler: typeof import("../src/index")["default"];

beforeAll(async () => {
  void mock.module("cloudflare:workers", () => ({
    DurableObject: class {},
  }));
  const worker = await import("../src/index");
  handler = worker.default;
});

let d1Mock: D1Database;

const executionContext = {
  waitUntil: (_promise: Promise<unknown>) => undefined,
  passThroughOnException: () => undefined,
  props: {},
};

let serviceAccountEmail = "minter@test-project.iam.gserviceaccount.com";
let privateKeyPem = "";

const baseEnv = () => ({
  ENVIRONMENT: "test",
  API_TOKEN: "test-token",
  STAGING_ACCOUNT_ID: "test-account",
  ACCOUNTS: {
    getByName: () => {
      throw new Error("no account calls");
    },
  },
  AI_MODEL: "test-model",
  AI: { run: async () => ({ response: "test response" }) },
  STAGING_DISPLAY_NAME: "Test",
  STAGING_EMAIL: "test@omi.invalid",
  STAGING_PLAN_LABEL: "Test",
  STAGING_CHAT_LIMIT: 1,
  OBSERVABILITY_SINK_MODE: "cloudflare_only",
  OPENROUTER_GATEWAY_ENABLED: "false",
  OPENROUTER_MODEL: "openai/gpt-5.6-luna",
  FIREBASE_DESKTOP_API_KEY: "test-desktop-key",
  get DB() {
    return d1Mock;
  },
});

const desktopEnv = () => ({
  ...baseEnv(),
  FIREBASE_DESKTOP_TOKEN_SA_EMAIL: serviceAccountEmail,
  FIREBASE_DESKTOP_TOKEN_PRIVATE_KEY: privateKeyPem,
});

let requestCounter = 0;

const postJson = (
  path: string,
  body: unknown,
  headers?: HeadersInit,
  clientIp?: string
) => {
  requestCounter += 1;
  return handler.fetch(
    new Request(`https://worker.test${path}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "cf-connecting-ip":
          clientIp ?? `198.51.100.${(requestCounter % 250) + 1}`,
        ...headers,
      },
      body: JSON.stringify(body),
    }),
    desktopEnv() as never,
    executionContext as never
  );
};

// The verifier and confirmation code the native client would hold.
const handoffMaterial = async (code: string) => {
  const verifier = "verifier-verifier-verifier-verifier-verifi";
  const challenge = await verifierChallenge(verifier);
  const confirmationChallenge = await verifierChallenge(code);
  const sessionId = (await deriveSessionId(challenge, confirmationChallenge))!;
  return { verifier, challenge, confirmationChallenge, sessionId };
};

beforeAll(async () => {
  d1Mock = createD1Mock();
  await applyAccountScopedIds(d1Mock);
  const pair = await crypto.subtle.generateKey(
    {
      name: "RSASSA-PKCS1-v1_5",
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["sign", "verify"]
  );
  const der = new Uint8Array(
    await crypto.subtle.exportKey("pkcs8", pair.privateKey)
  );
  let binary = "";
  for (const byte of der) binary += String.fromCharCode(byte);
  const base64 = btoa(binary);
  const lines = base64.match(/.{1,64}/g) ?? [];
  privateKeyPem = [
    "-----BEGIN PRIVATE KEY-----",
    ...lines,
    "-----END PRIVATE KEY-----",
    "",
  ].join("\n");
  (globalThis as Record<string, unknown>)["__testVerifyKey"] = pair.publicKey;
});

describe("desktop-auth pure module", () => {
  test("session values are 32-128 url-safe characters", () => {
    expect(isValidSessionValue("a".repeat(32))).toBe(true);
    expect(isValidSessionValue("A-b_9".repeat(8))).toBe(true);
    expect(isValidSessionValue("a".repeat(31))).toBe(false);
    expect(isValidSessionValue("a".repeat(129))).toBe(false);
    expect(isValidSessionValue(`${"a".repeat(40)}!`)).toBe(false);
  });

  test("confirmation codes are six digits", () => {
    expect(isValidConfirmationCode("123456")).toBe(true);
    expect(isValidConfirmationCode("12345")).toBe(false);
    expect(isValidConfirmationCode("1234567")).toBe(false);
    expect(isValidConfirmationCode("12a456")).toBe(false);
  });

  test("verifier challenge matches the v4 vector", async () => {
    expect(await verifierChallenge("123456")).toBe(
      "jZae727K08KaOmKSgOaGzww_XVqGr_PKEgIMkjrcbJI"
    );
  });

  test("session id is derived from both challenges", async () => {
    const material = await handoffMaterial("123456");
    expect(material.sessionId).toMatch(/^[A-Za-z0-9_-]{32,128}$/);
    expect(material.sessionId).not.toBe(material.challenge);
    expect(
      await deriveSessionId("short", material.confirmationChallenge)
    ).toBeNull();
    expect(
      await deriveSessionId(material.challenge, material.confirmationChallenge)
    ).toBe(material.sessionId);
  });

  test("browser url is the worker confirmation page", () => {
    expect(
      browserUrlFor("https://omi.example.workers.dev", "a".repeat(43))
    ).toBe(
      `https://omi.example.workers.dev/auth/desktop?desktop_auth=${"a".repeat(
        43
      )}`
    );
    expect(
      browserUrlFor("https://omi.example.workers.dev", "short")
    ).toBeNull();
  });

  test("custom token round-trips and verifies", async () => {
    const now = 1_700_000_000;
    const token = await createFirebaseCustomToken(
      "user-1",
      serviceAccountEmail,
      privateKeyPem,
      now
    );
    expect(token).not.toBeNull();
    const headerPart = token!.split(".")[0]!;
    const payloadPart = token!.split(".")[1]!;
    const signaturePart = token!.split(".")[2]!;
    expect(token!.split(".")).toHaveLength(3);
    const publicKey = (globalThis as unknown as Record<string, CryptoKey>)[
      "__testVerifyKey"
    ]!;
    const signed = new TextEncoder().encode(`${headerPart}.${payloadPart}`);
    const decodeBase64Url = (value: string): Uint8Array =>
      Uint8Array.from(
        atob(
          value
            .replace(/-/g, "+")
            .replace(/_/g, "/")
            .padEnd(Math.ceil(value.length / 4) * 4, "=")
        ),
        (character) => character.charCodeAt(0)
      );
    const signature = decodeBase64Url(signaturePart);
    expect(
      await crypto.subtle.verify(
        "RSASSA-PKCS1-v1_5",
        publicKey,
        signature as unknown as BufferSource,
        signed as unknown as BufferSource
      )
    ).toBe(true);
    const payload = JSON.parse(
      new TextDecoder().decode(decodeBase64Url(payloadPart))
    ) as Record<string, unknown>;
    expect(payload["uid"]).toBe("user-1");
    expect(payload["iss"]).toBe(serviceAccountEmail);
    expect(payload["sub"]).toBe(serviceAccountEmail);
    expect(payload["aud"]).toBe(
      "https://identitytoolkit.googleapis.com/google.identity.identitytoolkit.v1.IdentityToolkit"
    );
    expect(payload["iat"]).toBe(now);
    expect(payload["exp"]).toBe(now + 3600);
  });

  test("a private key with escaped newlines still signs", async () => {
    const escaped = privateKeyPem.replaceAll("\n", "\\n");
    expect(
      await createFirebaseCustomToken("u", serviceAccountEmail, escaped, 0)
    ).not.toBeNull();
  });

  test("an unusable key returns null", async () => {
    expect(
      await createFirebaseCustomToken("u", serviceAccountEmail, "not-a-key", 0)
    ).toBeNull();
  });
});

describe("desktop-auth routes", () => {
  test("start creates a handoff and returns the confirmation page url", async () => {
    const material = await handoffMaterial("654321");
    const response = await postJson("/v1/auth/desktop/start", {
      sessionId: material.sessionId,
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    });
    expect(response.status).toBe(201);
    const body = (await response.json()) as {
      browserUrl: string;
      expiresAt: number;
    };
    expect(body.browserUrl).toBe(
      `https://worker.test/auth/desktop?desktop_auth=${material.sessionId}`
    );
    expect(body.expiresAt).toBeGreaterThan(Date.now());
    expect(body.expiresAt).toBeLessThanOrEqual(
      Date.now() + DESKTOP_AUTH_LIFETIME_MS
    );
  });

  test("start refuses a session id that does not derive from the challenges", async () => {
    const material = await handoffMaterial("111111");
    const response = await postJson("/v1/auth/desktop/start", {
      sessionId: "b".repeat(43),
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    });
    expect(response.status).toBe(400);
  });

  test("a duplicate start conflicts", async () => {
    const material = await handoffMaterial("222222");
    const body = {
      sessionId: material.sessionId,
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    };
    expect((await postJson("/v1/auth/desktop/start", body)).status).toBe(201);
    expect((await postJson("/v1/auth/desktop/start", body)).status).toBe(409);
  });

  test("the per-ip start rate limit engages", async () => {
    const ip = "198.51.100.7";
    const existing = await d1Mock
      .prepare(
        "SELECT COUNT(*) AS count FROM desktop_auth_sessions WHERE client_ip = ?1"
      )
      .bind(ip)
      .first<{ count: number }>();
    let starts = existing?.count ?? 0;
    let response: Response | null = null;
    // Keep starting distinct derived handoffs until the limit refuses one.
    while (starts < DESKTOP_AUTH_START_RATE_LIMIT + 1) {
      const material = await handoffMaterial("333333");
      const challenge = `${material.challenge}${starts}`;
      const sessionId = await deriveSessionId(
        challenge,
        material.confirmationChallenge
      );
      response = await postJson(
        "/v1/auth/desktop/start",
        {
          sessionId,
          challenge,
          confirmationChallenge: material.confirmationChallenge,
        },
        undefined,
        ip
      );
      if (response.status !== 201) break;
      starts += 1;
    }
    expect(starts).toBe(DESKTOP_AUTH_START_RATE_LIMIT);
    expect(response?.status).toBe(429);
  });

  test("the confirmation page renders for a valid handoff query", async () => {
    const material = await handoffMaterial("444444");
    await postJson("/v1/auth/desktop/start", {
      sessionId: material.sessionId,
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    });
    const response = await handler.fetch(
      new Request(
        `https://worker.test/auth/desktop?desktop_auth=${material.sessionId}`
      ),
      desktopEnv() as never,
      executionContext as never
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("content-security-policy")).toContain(
      "identitytoolkit.googleapis.com"
    );
    const html = await response.text();
    expect(html).toContain("6-digit code");
    expect(html).toContain(material.sessionId);
    expect(html).toContain("test-desktop-key");
    // The inline script must be syntactically valid JavaScript: a broken
    // quoting layer still serves 200 HTML but renders a blank page.
    const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
    expect(script).toBeDefined();
    expect(() => new Function(script!)).not.toThrow();
  });

  test("the confirmation page refuses bad queries", async () => {
    const badQueries = [
      "",
      "?desktop_auth=short",
      "?desktop_auth=a&desktop_auth=b",
      "?other=1",
    ];
    for (const query of badQueries) {
      const response = await handler.fetch(
        new Request(`https://worker.test/auth/desktop${query}`),
        desktopEnv() as never,
        executionContext as never
      );
      expect(response.status).toBe(400);
    }
  });

  const completeWithCode = async (
    sessionId: string,
    code: string,
    idToken = "firebase-id-token"
  ) =>
    postJson(
      "/v1/auth/desktop/complete",
      { sessionId, confirmationCode: code },
      { authorization: `Bearer ${idToken}` }
    );

  const stubFirebaseLookup = (
    localId: string | { status: number }
  ): (() => void) => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = mock(async (input: RequestInfo | URL) => {
      const request = new Request(input);
      if (!request.url.startsWith("https://identitytoolkit.googleapis.com/")) {
        throw new Error(`unexpected fetch: ${request.url}`);
      }
      expect(request.url).toContain("key=test-desktop-key");
      if (typeof localId !== "string")
        return new Response(null, { status: localId.status });
      return Response.json({ users: [{ localId }] });
    }) as never;
    return () => {
      globalThis.fetch = originalFetch;
    };
  };

  test("complete binds the account when the code matches", async () => {
    const material = await handoffMaterial("555555");
    await postJson("/v1/auth/desktop/start", {
      sessionId: material.sessionId,
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    });
    const restore = stubFirebaseLookup("firebase-user-1");
    try {
      const pending = await postJson("/v1/auth/desktop/exchange", {
        sessionId: material.sessionId,
        verifier: material.verifier,
      });
      expect(pending.status).toBe(409);
      const pendingBody = (await pending.json()) as { status: string };
      expect(pendingBody).toEqual({ status: "pending" });

      const completed = await completeWithCode(material.sessionId, "555555");
      expect(completed.status).toBe(200);
      const completedBody = (await completed.json()) as { completed: boolean };
      expect(completedBody).toEqual({ completed: true });

      const exchanged = await postJson("/v1/auth/desktop/exchange", {
        sessionId: material.sessionId,
        verifier: material.verifier,
      });
      expect(exchanged.status).toBe(200);
      const body = (await exchanged.json()) as { customToken: string };
      expect(body.customToken.split(".")).toHaveLength(3);

      // The handoff is single-use.
      const replay = await postJson("/v1/auth/desktop/exchange", {
        sessionId: material.sessionId,
        verifier: material.verifier,
      });
      expect(replay.status).toBe(410);
    } finally {
      restore();
    }
  });

  test("a wrong confirmation code is refused without binding", async () => {
    const material = await handoffMaterial("666666");
    await postJson("/v1/auth/desktop/start", {
      sessionId: material.sessionId,
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    });
    const restore = stubFirebaseLookup("firebase-user-2");
    try {
      const response = await completeWithCode(material.sessionId, "000000");
      expect(response.status).toBe(409);
      const exchanged = await postJson("/v1/auth/desktop/exchange", {
        sessionId: material.sessionId,
        verifier: material.verifier,
      });
      expect(exchanged.status).toBe(409);
      const exchangedBody = (await exchanged.json()) as { status: string };
      expect(exchangedBody).toEqual({ status: "pending" });
    } finally {
      restore();
    }
  });

  test("five wrong codes lock the handoff", async () => {
    const material = await handoffMaterial("777777");
    await postJson("/v1/auth/desktop/start", {
      sessionId: material.sessionId,
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    });
    const restore = stubFirebaseLookup("firebase-user-3");
    try {
      for (let attempt = 0; attempt < 5; attempt += 1) {
        const response = await completeWithCode(material.sessionId, "000000");
        expect(response.status).toBe(409);
      }
      const correct = await completeWithCode(material.sessionId, "777777");
      expect(correct.status).toBe(409);
    } finally {
      restore();
    }
  });

  test("complete refuses a bad firebase token", async () => {
    const material = await handoffMaterial("888888");
    await postJson("/v1/auth/desktop/start", {
      sessionId: material.sessionId,
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    });
    const restore = stubFirebaseLookup({ status: 401 });
    try {
      const response = await completeWithCode(material.sessionId, "888888");
      expect(response.status).toBe(401);
    } finally {
      restore();
    }
  });

  test("exchange with the wrong verifier is expired", async () => {
    const material = await handoffMaterial("999999");
    await postJson("/v1/auth/desktop/start", {
      sessionId: material.sessionId,
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    });
    const response = await postJson("/v1/auth/desktop/exchange", {
      sessionId: material.sessionId,
      verifier: "wrong-wrong-wrong-wrong-wrong-wrong-wrong-wr",
    });
    expect(response.status).toBe(410);
  });

  test("exchange needs the signing secrets", async () => {
    const material = await handoffMaterial("101010");
    await postJson("/v1/auth/desktop/start", {
      sessionId: material.sessionId,
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    });
    const response = await handler.fetch(
      new Request("https://worker.test/v1/auth/desktop/exchange", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          sessionId: material.sessionId,
          verifier: material.verifier,
        }),
      }),
      baseEnv() as never,
      executionContext as never
    );
    expect(response.status).toBe(503);
  });

  test("the handoff routes are reachable without a bearer token", async () => {
    const material = await handoffMaterial("121212");
    const started = await postJson("/v1/auth/desktop/start", {
      sessionId: material.sessionId,
      challenge: material.challenge,
      confirmationChallenge: material.confirmationChallenge,
    });
    expect(started.status).toBe(201);
    const exchanged = await postJson("/v1/auth/desktop/exchange", {
      sessionId: material.sessionId,
      verifier: material.verifier,
    });
    expect(exchanged.status).toBe(409);
  });
});
