export interface RuntimeOwnerAuthorityState {
  ownerId: string;
  established: boolean;
}

export interface RuntimeOwnerAuthorityTransition {
  previousOwnerId: string;
  ownerId: string;
  changed: boolean;
  firstEstablishment: boolean;
  state: RuntimeOwnerAuthorityState;
}

export interface ClearedRuntimeOwnerAuthority {
  previousOwnerId: string;
  state: RuntimeOwnerAuthorityState;
}

export interface PreparedRuntimeOwnerRevocation extends ClearedRuntimeOwnerAuthority {
  duplicate: boolean;
}

export interface RuntimeOwnerRevocationReceipt {
  ownerId: string;
}

export interface RuntimeOwnerRevocationBarrierResult<Receipt extends RuntimeOwnerRevocationReceipt> {
  state: RuntimeOwnerAuthorityState;
  receipt: Receipt;
  duplicate: boolean;
}

/** Owner-scoped runtime work is unavailable until Swift completes its handshake. */
export function requireActiveRuntimeOwner(
  state: RuntimeOwnerAuthorityState,
  requestedOwnerId: string | undefined,
): string {
  if (!state.established) {
    throw new Error("owner_uninitialized: runtime owner handshake has not completed");
  }
  const requested = requestedOwnerId?.trim();
  if (requested && requested !== state.ownerId) {
    throw new Error("owner_mismatch: request owner does not match the active runtime owner");
  }
  return state.ownerId;
}

export function establishRuntimeOwner(
  state: RuntimeOwnerAuthorityState,
  requestedOwnerId: string | undefined,
): RuntimeOwnerAuthorityTransition {
  const ownerId = requestedOwnerId?.trim() ?? "";
  if (!ownerId) throw new Error("Runtime owner handshake requires a non-empty ownerId");
  return {
    previousOwnerId: state.ownerId,
    ownerId,
    changed: ownerId !== state.ownerId,
    firstEstablishment: !state.established,
    state: { ownerId, established: true },
  };
}

/**
 * Token refresh may establish the first explicit owner or refresh the current
 * owner. A different owner must first clear the old authority, preventing a
 * delayed owner-A token from switching a live owner-B runtime back to A.
 * Credential mutation runs only after this validation succeeds.
 */
export function authorizeRuntimeTokenRefresh(
  state: RuntimeOwnerAuthorityState,
  requestedOwnerId: string | undefined,
  commitCredentials: () => void,
): RuntimeOwnerAuthorityTransition {
  const transition = establishRuntimeOwner(state, requestedOwnerId);
  if (state.established && transition.changed) {
    throw new Error("owner_mismatch: token refresh owner does not match the active runtime owner");
  }
  commitCredentials();
  return transition;
}

export function clearRuntimeOwnerAuthority(
  state: RuntimeOwnerAuthorityState,
  requestedOwnerId: string | undefined,
  inertOwnerId: string,
): ClearedRuntimeOwnerAuthority {
  const previousOwnerId = requireActiveRuntimeOwner(state, requestedOwnerId);
  const inert = inertOwnerId.trim();
  if (!inert) throw new Error("Cleared runtime owner requires a non-empty inert owner id");
  return {
    previousOwnerId,
    state: { ownerId: inert, established: false },
  };
}

/**
 * Prepares the correlated owner-runtime barrier. An already-inert runtime is
 * accepted only when the process has an exact successful revocation receipt for
 * the requested owner; arbitrary uninitialized state is never treated as proof.
 */
export function prepareRuntimeOwnerRevocation(
  state: RuntimeOwnerAuthorityState,
  requestedOwnerId: string | undefined,
  inertOwnerId: string,
  lastSynchronouslyRevokedOwnerId: string | null,
): PreparedRuntimeOwnerRevocation {
  const requested = requestedOwnerId?.trim() ?? "";
  if (!requested) throw new Error("Owner runtime revocation requires a non-empty ownerId");
  if (!state.established) {
    if (lastSynchronouslyRevokedOwnerId !== requested) {
      throw new Error("owner_uninitialized: exact previous-owner revocation was not proven");
    }
    return {
      previousOwnerId: requested,
      state,
      duplicate: true,
    };
  }
  const cleared = clearRuntimeOwnerAuthority(state, requested, inertOwnerId);
  return { ...cleared, duplicate: false };
}

/**
 * Executes the synchronous correlated barrier used by the stdin handler. The
 * authority commit deliberately precedes every terminalization callback, so no
 * nested admission seam can observe owner A as active while revocation runs.
 */
export function runRuntimeOwnerRevocationBarrier<Receipt extends RuntimeOwnerRevocationReceipt>(
  input: {
    state: RuntimeOwnerAuthorityState;
    requestedOwnerId: string | undefined;
    inertOwnerId: string;
    lastReceipt: Receipt | null;
    commitAuthority: (state: RuntimeOwnerAuthorityState) => void;
    revokeAndClear: (previousOwnerId: string) => Receipt;
  },
): RuntimeOwnerRevocationBarrierResult<Receipt> {
  const prepared = prepareRuntimeOwnerRevocation(
    input.state,
    input.requestedOwnerId,
    input.inertOwnerId,
    input.lastReceipt?.ownerId ?? null,
  );
  if (prepared.duplicate) {
    if (!input.lastReceipt) throw new Error("owner_runtime_revocation_receipt_missing");
    return { state: prepared.state, receipt: input.lastReceipt, duplicate: true };
  }
  input.commitAuthority(prepared.state);
  const receipt = input.revokeAndClear(prepared.previousOwnerId);
  if (receipt.ownerId !== prepared.previousOwnerId) {
    throw new Error("owner_runtime_revocation_receipt_owner_mismatch");
  }
  return { state: prepared.state, receipt, duplicate: false };
}

export function runtimeOwnerForEffects(state: RuntimeOwnerAuthorityState): string {
  return state.established ? state.ownerId : "";
}
