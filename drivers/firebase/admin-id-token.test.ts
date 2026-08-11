import { afterEach, describe, expect, test } from "bun:test";

import { getApp, getApps } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

import { createFirebaseAdminIdTokenAdapter } from "./admin-id-token";

const PROJECT = "omi-firebase-adapter-fixture";
const created: Array<Awaited<ReturnType<typeof createFirebaseAdminIdTokenAdapter>>> = [];
let appOrdinal = 0;

const nextAppName = (): string => `omi-firebase-adapter-test-${process.pid}-${appOrdinal += 1}`;

const construct = async (
  overrides: Partial<Parameters<typeof createFirebaseAdminIdTokenAdapter>[0]> = {},
) => {
  const handle = await createFirebaseAdminIdTokenAdapter({
    project_id: PROJECT,
    app_name: nextAppName(),
    runtime_mode: "local_test",
    ...overrides,
  });
  created.push(handle);
  return handle;
};

const withoutEmulator = async <T>(run: () => Promise<T>): Promise<T> => {
  const present = Object.prototype.hasOwnProperty.call(process.env, "FIREBASE_AUTH_EMULATOR_HOST");
  const previous = process.env.FIREBASE_AUTH_EMULATOR_HOST;
  delete process.env.FIREBASE_AUTH_EMULATOR_HOST;
  try {
    return await run();
  } finally {
    if (present) process.env.FIREBASE_AUTH_EMULATOR_HOST = previous;
    else delete process.env.FIREBASE_AUTH_EMULATOR_HOST;
  }
};

afterEach(async () => {
  for (const handle of created.splice(0)) {
    try {
      await handle.close();
    } catch {
      // A test may deliberately exercise a closed or failed SDK boundary.
    }
  }
  delete process.env.FIREBASE_AUTH_EMULATOR_HOST;
});

describe("official Firebase Admin ID-token adapter", () => {
  test("pins one named app to the exact project and delegates revocation checking", async () => {
    await withoutEmulator(async () => {
      const appName = nextAppName();
      const handle = await construct({ app_name: appName });
      const app = getApp(appName);
      expect(app.options.projectId).toBe(PROJECT);
      expect(app.options.credential).toBeDefined();
      expect(handle.adapter.verification_source).toBe("firebase_production");
      expect(Object.keys(handle.adapter).sort()).toEqual(["verification_source", "verifyIdToken"]);
      expect(Object.isFrozen(handle.adapter)).toBe(true);
      expect(Object.isFrozen(handle)).toBe(true);

      const auth = getAuth(app);
      const original = auth.verifyIdToken;
      const decoded = { uid: "firebase-user", private_claim: "not-authority" };
      const calls: unknown[][] = [];
      auth.verifyIdToken = (async (...args: unknown[]) => {
        calls.push(args);
        return decoded;
      }) as unknown as typeof auth.verifyIdToken;
      try {
        expect(await handle.adapter.verifyIdToken("header.payload.signature", true)).toBe(decoded);
        expect(calls).toEqual([["header.payload.signature", true]]);
      } finally {
        auth.verifyIdToken = original;
      }
    });
  });

  test("deployed mode refuses any ambient emulator value before app construction", async () => {
    for (const value of ["", "127.0.0.1:9099"]) {
      process.env.FIREBASE_AUTH_EMULATOR_HOST = value;
      const before = getApps().map((app) => app.name).sort();
      await expect(createFirebaseAdminIdTokenAdapter({
        project_id: PROJECT,
        app_name: nextAppName(),
        runtime_mode: "deployed",
      })).rejects.toThrow("forbids");
      expect(getApps().map((app) => app.name).sort()).toEqual(before);
    }
  });

  test("local-test source is derived from the actual emulator environment", async () => {
    process.env.FIREBASE_AUTH_EMULATOR_HOST = "127.0.0.1:9099";
    const handle = await construct();
    expect(handle.adapter.verification_source).toBe("firebase_auth_emulator");
  });

  test("hostile configuration fails before app construction without invoking getters", async () => {
    let getterCalls = 0;
    const accessor = Object.create(Object.prototype, {
      project_id: { enumerable: true, get: () => { getterCalls += 1; return PROJECT; } },
      app_name: { enumerable: true, value: nextAppName() },
      runtime_mode: { enumerable: true, value: "local_test" },
    });
    const hostile: unknown[] = [
      accessor,
      new Proxy({ project_id: PROJECT, app_name: nextAppName(), runtime_mode: "local_test" }, {}),
      { project_id: PROJECT, app_name: nextAppName(), runtime_mode: "local_test", extra: true },
      { project_id: "bad/project", app_name: nextAppName(), runtime_mode: "local_test" },
      { project_id: PROJECT, app_name: "bad app", runtime_mode: "local_test" },
      { project_id: PROJECT, app_name: nextAppName(), runtime_mode: "production" },
    ];
    const before = getApps().length;
    for (const candidate of hostile) {
      await expect(createFirebaseAdminIdTokenAdapter(candidate as never)).rejects.toThrow(
        "invalid Firebase Admin adapter configuration",
      );
    }
    expect(getApps()).toHaveLength(before);
    expect(getterCalls).toBe(0);
  });

  test("SDK verification failures collapse to a closed adapter error", async () => {
    await withoutEmulator(async () => {
      const appName = nextAppName();
      const handle = await construct({ app_name: appName });
      const auth = getAuth(getApp(appName));
      const original = auth.verifyIdToken;
      auth.verifyIdToken = (async () => {
        throw new Error("raw SDK provider sentinel and credential path");
      }) as typeof auth.verifyIdToken;
      try {
        await expect(handle.adapter.verifyIdToken("header.payload.signature", true))
          .rejects.toThrow(/^firebase_admin_identity_unavailable$/);
      } finally {
        auth.verifyIdToken = original;
      }
    });
  });

  test("an emulator-environment change after construction fails closed", async () => {
    await withoutEmulator(async () => {
      const appName = nextAppName();
      const handle = await construct({ app_name: appName });
      const auth = getAuth(getApp(appName));
      const original = auth.verifyIdToken;
      let calls = 0;
      auth.verifyIdToken = (async () => {
        calls += 1;
        return {} as never;
      }) as typeof auth.verifyIdToken;
      process.env.FIREBASE_AUTH_EMULATOR_HOST = "127.0.0.1:9099";
      try {
        await expect(handle.adapter.verifyIdToken("header.payload.signature", true))
          .rejects.toThrow(/^firebase_admin_identity_unavailable$/);
        expect(calls).toBe(0);
      } finally {
        auth.verifyIdToken = original;
        delete process.env.FIREBASE_AUTH_EMULATOR_HOST;
      }
    });
  });

  test("close deletes only its app, is idempotent, and fences later verification", async () => {
    await withoutEmulator(async () => {
      const appName = nextAppName();
      const handle = await construct({ app_name: appName });
      expect(getApps().map((app) => app.name)).toContain(appName);
      await handle.close();
      await handle.close();
      expect(getApps().map((app) => app.name)).not.toContain(appName);
      await expect(handle.adapter.verifyIdToken("header.payload.signature", true))
        .rejects.toThrow(/^firebase_admin_identity_unavailable$/);
    });
  });

  test("a duplicate app name fails closed instead of reusing ambient configuration", async () => {
    await withoutEmulator(async () => {
      const appName = nextAppName();
      await construct({ app_name: appName });
      await expect(createFirebaseAdminIdTokenAdapter({
        project_id: "different-project",
        app_name: appName,
        runtime_mode: "local_test",
      })).rejects.toThrow(/^firebase_admin_identity_unavailable$/);
      expect(getApp(appName).options.projectId).toBe(PROJECT);
    });
  });

  test("the concrete driver has no application-authority or persistence imports", async () => {
    const source = await Bun.file(new URL("./admin-id-token.ts", import.meta.url)).text();
    for (const forbidden of [
      "apps/service/routes",
      "apps/service/control",
      "authorized-context",
      "drivers/postgres",
      "drivers/sqlite",
      "core/ledger",
      "drivers/model",
    ]) expect(source).not.toContain(forbidden);
  });
});
