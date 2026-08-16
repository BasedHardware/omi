import { describe, expect, it } from "vitest";

import {
  authorizeRuntimeTokenRefresh,
  clearRuntimeOwnerAuthority,
  establishRuntimeOwner,
  prepareRuntimeOwnerRevocation,
  requireActiveRuntimeOwner,
  runRuntimeOwnerRevocationBarrier,
  runtimeOwnerForEffects,
} from "../src/runtime/runtime-owner-authority.js";

describe("runtime owner handshake authority", () => {
  it("blocks placeholder-owner work until the signed-in owner handshake completes", () => {
    const startup = { ownerId: "desktop-local-user", established: false };
    expect(() => requireActiveRuntimeOwner(startup, undefined)).toThrow(/owner_uninitialized/);
    expect(() => requireActiveRuntimeOwner(startup, "desktop-local-user")).toThrow(/owner_uninitialized/);

    const transition = establishRuntimeOwner(startup, "signed-owner");
    expect(transition).toMatchObject({
      previousOwnerId: "desktop-local-user",
      ownerId: "signed-owner",
      changed: true,
      firstEstablishment: true,
    });
    expect(requireActiveRuntimeOwner(transition.state, "signed-owner")).toBe("signed-owner");
    expect(() => requireActiveRuntimeOwner(transition.state, "other-owner")).toThrow(/owner_mismatch/);
  });

  it("allows only first establishment or idempotent same-owner refresh in one process", () => {
    const first = establishRuntimeOwner({ ownerId: "owner-a", established: false }, "owner-a");
    expect(first).toMatchObject({ changed: false, firstEstablishment: true });
    const repeated = establishRuntimeOwner(first.state, "owner-a");
    expect(repeated).toMatchObject({ changed: false, firstEstablishment: false });
    expect(() => establishRuntimeOwner(repeated.state, "owner-b")).toThrow(
      /established runtime owner replacement requires correlated revoke and a fresh process/,
    );
    expect(runtimeOwnerForEffects(repeated.state)).toBe("owner-a");
  });

  it("rejects ownerless and stale-owner token refresh before any credential side effect", () => {
    const startup = { ownerId: "desktop-local-user", established: false };
    let committedToken: string | undefined;
    expect(() => authorizeRuntimeTokenRefresh(startup, undefined, () => {
      committedToken = "ownerless-token";
    })).toThrow(/non-empty ownerId/);
    expect(committedToken).toBeUndefined();
    expect(runtimeOwnerForEffects(startup)).toBe("");

    const established = authorizeRuntimeTokenRefresh(startup, "owner-a", () => {
      committedToken = "owner-a-token";
    });
    expect(committedToken).toBe("owner-a-token");
    expect(runtimeOwnerForEffects(established.state)).toBe("owner-a");

    committedToken = undefined;
    expect(() => authorizeRuntimeTokenRefresh(established.state, "owner-b", () => {
      committedToken = "stale-owner-b-token";
    })).toThrow(/owner_mismatch/);
    expect(committedToken).toBeUndefined();
    expect(runtimeOwnerForEffects(established.state)).toBe("owner-a");
  });

  it("clear revokes owner effects until a new explicit handshake", () => {
    const active = establishRuntimeOwner(
      { ownerId: "desktop-local-user", established: false },
      "owner-a",
    ).state;
    const cleared = clearRuntimeOwnerAuthority(active, "owner-a", "desktop-local-user");
    expect(cleared.previousOwnerId).toBe("owner-a");
    expect(cleared.state).toEqual({ ownerId: "desktop-local-user", established: false });
    expect(runtimeOwnerForEffects(cleared.state)).toBe("");
    expect(() => requireActiveRuntimeOwner(cleared.state, undefined)).toThrow(/owner_uninitialized/);
    expect(() => requireActiveRuntimeOwner(cleared.state, "owner-a")).toThrow(/owner_uninitialized/);

    const ownerB = establishRuntimeOwner(cleared.state, "owner-b");
    expect(runtimeOwnerForEffects(ownerB.state)).toBe("owner-b");
  });

  it("accepts an inert runtime only with the exact prior synchronous revocation receipt", () => {
    const active = establishRuntimeOwner(
      { ownerId: "desktop-local-user", established: false },
      "owner-a",
    ).state;
    const prepared = prepareRuntimeOwnerRevocation(
      active,
      "owner-a",
      "desktop-local-user",
      null,
    );
    expect(prepared).toMatchObject({
      previousOwnerId: "owner-a",
      duplicate: false,
      state: { ownerId: "desktop-local-user", established: false },
    });
    expect(() => prepareRuntimeOwnerRevocation(
      prepared.state,
      "owner-a",
      "desktop-local-user",
      null,
    )).toThrow(/exact previous-owner revocation was not proven/);
    expect(prepareRuntimeOwnerRevocation(
      prepared.state,
      "owner-a",
      "desktop-local-user",
      "owner-a",
    )).toMatchObject({ previousOwnerId: "owner-a", duplicate: true });
    expect(() => prepareRuntimeOwnerRevocation(
      prepared.state,
      "owner-b",
      "desktop-local-user",
      "owner-a",
    )).toThrow(/exact previous-owner revocation was not proven/);
  });

  it("commits inert authority before terminalization and accepts only exact duplicate ACKs", () => {
    let authority = establishRuntimeOwner(
      { ownerId: "desktop-local-user", established: false },
      "owner-a",
    ).state;
    let revocationCount = 0;
    const first = runRuntimeOwnerRevocationBarrier({
      state: authority,
      requestedOwnerId: "owner-a",
      inertOwnerId: "desktop-local-user",
      lastReceipt: null,
      commitAuthority: (state) => { authority = state; },
      revokeAndClear: (ownerId) => {
        expect(authority).toEqual({ ownerId: "desktop-local-user", established: false });
        revocationCount += 1;
        return { ownerId, revokedRunIds: ["run-a"], invalidatedBindingIds: ["binding-a"] };
      },
    });
    expect(first.duplicate).toBe(false);
    expect(revocationCount).toBe(1);

    const duplicate = runRuntimeOwnerRevocationBarrier({
      state: authority,
      requestedOwnerId: "owner-a",
      inertOwnerId: "desktop-local-user",
      lastReceipt: first.receipt,
      commitAuthority: () => { throw new Error("duplicate must not recommit authority"); },
      revokeAndClear: () => { throw new Error("duplicate must not revoke twice"); },
    });
    expect(duplicate).toMatchObject({ duplicate: true, receipt: first.receipt });
    expect(() => runRuntimeOwnerRevocationBarrier({
      state: authority,
      requestedOwnerId: "owner-b",
      inertOwnerId: "desktop-local-user",
      lastReceipt: first.receipt,
      commitAuthority: () => {},
      revokeAndClear: (ownerId) => ({ ownerId }),
    })).toThrow(/exact previous-owner revocation was not proven/);

    authority = establishRuntimeOwner(authority, "owner-b").state;
    expect(() => runRuntimeOwnerRevocationBarrier({
      state: authority,
      requestedOwnerId: "owner-a",
      inertOwnerId: "desktop-local-user",
      lastReceipt: null,
      commitAuthority: () => {},
      revokeAndClear: (ownerId) => ({ ownerId }),
    })).toThrow(/owner_mismatch/);
  });
});
