import { describe, expect, it } from "vitest";
import {
  isFirebaseTokenError,
  planFirebaseAdminInit,
} from "@/lib/firebase/admin";

describe("isFirebaseTokenError", () => {
  it("classifies the SDK's bad-token codes (malformed, bad signature, expired, revoked)", () => {
    for (const code of [
      "auth/argument-error",
      "auth/id-token-expired",
      "auth/id-token-revoked",
    ]) {
      expect(
        isFirebaseTokenError(Object.assign(new Error(code), { code })),
        code
      ).toBe(true);
    }
  });

  it("does not classify server faults as token faults", () => {
    for (const code of ["auth/internal-error", "auth/network-request-failed"]) {
      expect(
        isFirebaseTokenError(Object.assign(new Error(code), { code })),
        code
      ).toBe(false);
    }
    expect(isFirebaseTokenError(new Error("plain"))).toBe(false);
    expect(isFirebaseTokenError(null)).toBe(false);
    expect(isFirebaseTokenError("auth/argument-error")).toBe(false);
  });
});

describe("planFirebaseAdminInit", () => {
  it("uses the runtime service account when no key is configured", () => {
    expect(
      planFirebaseAdminInit({
        NEXT_PUBLIC_FIREBASE_PROJECT_ID: "based-hardware",
      })
    ).toEqual({
      mode: "application-default",
      projectId: "based-hardware",
      projectIdSource: "NEXT_PUBLIC_FIREBASE_PROJECT_ID",
    });
  });

  it("prefers an explicit FIREBASE_PROJECT_ID over the public build value", () => {
    const plan = planFirebaseAdminInit({
      FIREBASE_PROJECT_ID: "explicit",
      NEXT_PUBLIC_FIREBASE_PROJECT_ID: "public",
    });
    expect(plan).toMatchObject({
      mode: "application-default",
      projectId: "explicit",
    });
  });

  it("lets the SDK discover the project from the metadata server as a last resort", () => {
    expect(planFirebaseAdminInit({})).toEqual({
      mode: "application-default",
      projectId: undefined,
      projectIdSource: "metadata-server",
    });
  });

  it("keeps the service-account-key path for local non-production use", () => {
    const plan = planFirebaseAdminInit({
      FIREBASE_PROJECT_ID: "local-dev",
      FIREBASE_CLIENT_EMAIL: "sa@local-dev.iam.gserviceaccount.com",
      FIREBASE_PRIVATE_KEY: "not-a-real-key",
    });
    expect(plan).toEqual({
      mode: "service-account-key",
      projectId: "local-dev",
      projectIdSource: "FIREBASE_PROJECT_ID",
    });
  });

  it("refuses half a key instead of silently switching identity", () => {
    expect(() => planFirebaseAdminInit({ FIREBASE_PRIVATE_KEY: "x" })).toThrow(
      /set together/
    );
    expect(() => planFirebaseAdminInit({ FIREBASE_CLIENT_EMAIL: "x" })).toThrow(
      /set together/
    );
  });

  it("requires a project id for the key path", () => {
    expect(() =>
      planFirebaseAdminInit({
        FIREBASE_CLIENT_EMAIL: "x",
        FIREBASE_PRIVATE_KEY: "y",
      })
    ).toThrow(/FIREBASE_PROJECT_ID/);
  });

  it("treats blank values as unset", () => {
    expect(
      planFirebaseAdminInit({
        FIREBASE_CLIENT_EMAIL: " ",
        FIREBASE_PRIVATE_KEY: "",
        FIREBASE_PROJECT_ID: "p",
      })
    ).toMatchObject({ mode: "application-default", projectId: "p" });
  });
});
