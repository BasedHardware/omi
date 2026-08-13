import { isProxy } from "node:util/types";

import {
  DELETION_CLEANUP_SURFACES,
  DELETION_DISPOSAL_GROUPS,
  type DeletionCleanupSurface,
  type DeletionInventorySourceReceipt,
} from "../../../core/control/deletion-cleanup-inventory";
import type {
  AccountDeletionCleanupPort,
  DeletionCleanupDispositionReceipt,
  HeldDeletionCleanupSession,
} from "./account-deletion-cleanup";

const DIGEST = /^[0-9a-f]{64}$/;
const OPERATION_REF = /^opref1_[0-9a-f]{64}$/;
const PARTICIPANT_ID = /^[a-z][a-z0-9_-]{0,62}$/;

export type DeletionCleanupCompositeErrorCode =
  | "invalid_configuration"
  | "invalid_input"
  | "eligibility_fence_failed"
  | "eligibility_revalidation_failed"
  | "participant_fence_failed"
  | "scan_failed"
  | "disposal_failed";

export class DeletionCleanupCompositeError extends Error {
  readonly code: DeletionCleanupCompositeErrorCode;

  constructor(code: DeletionCleanupCompositeErrorCode) {
    super(code);
    this.name = "DeletionCleanupCompositeError";
    this.code = code;
  }
}

export interface DeletionCleanupCoordinate {
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
}

export interface EligibilityFenceRevalidationReceipt {
  readonly version: "deletion-cleanup-eligibility-fence-v1";
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly eligibility_digest: string;
  readonly state: "held";
  readonly fence_receipt_digest: string;
}

/**
 * The authority that can keep the exact terminal deletion coordinate and its
 * external eligibility inputs stable while independently fenced stores run.
 * This is deliberately not described as a cross-system transaction.
 */
export interface HeldDeletionEligibilityFence {
  revalidateExact(): Promise<EligibilityFenceRevalidationReceipt>;
}

export interface DeletionEligibilityFenceCoordinator {
  withHeldEligibilityFence<T>(
    coordinate: DeletionCleanupCoordinate,
    operationRef: string,
    eligibilityDigest: string,
    callback: (fence: HeldDeletionEligibilityFence) => Promise<T>,
  ): Promise<T>;
}

export interface HeldDeletionSurfaceSession {
  scanOwned(): Promise<readonly DeletionInventorySourceReceipt[]>;
  disposeOwned(
    surfaces: readonly DeletionCleanupSurface[],
  ): Promise<readonly DeletionCleanupDispositionReceipt[]>;
}

/** Each participant owns complete surfaces and supplies its own honest fence. */
export interface DeletionSurfaceParticipant {
  readonly participant_id: string;
  readonly owned_surfaces: readonly DeletionCleanupSurface[];
  withHeldSurfaceFence<T>(
    coordinate: DeletionCleanupCoordinate,
    operationRef: string,
    eligibilityDigest: string,
    callback: (session: HeldDeletionSurfaceSession) => Promise<T>,
  ): Promise<T>;
}

const exactDataRecord = (
  value: unknown,
  keys: readonly string[],
  code: DeletionCleanupCompositeErrorCode = "eligibility_revalidation_failed",
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new DeletionCleanupCompositeError(code);
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) {
    throw new DeletionCleanupCompositeError(code);
  }
  const result: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      throw new DeletionCleanupCompositeError(code);
    }
    result[key] = descriptor.value;
  }
  return result;
};

const validatedCoordinate = (value: DeletionCleanupCoordinate): DeletionCleanupCoordinate => {
  const coordinate = exactDataRecord(
    value, ["account_id", "control_revision", "deletion_epoch"], "invalid_input",
  );
  if (typeof coordinate["account_id"] !== "string" || coordinate["account_id"].length === 0
    || !Number.isSafeInteger(coordinate["control_revision"])
    || (coordinate["control_revision"] as number) <= 0
    || !Number.isSafeInteger(coordinate["deletion_epoch"])
    || (coordinate["deletion_epoch"] as number) <= 0) {
    throw new DeletionCleanupCompositeError("invalid_input");
  }
  return Object.freeze({
    account_id: coordinate["account_id"],
    control_revision: coordinate["control_revision"],
    deletion_epoch: coordinate["deletion_epoch"],
  }) as DeletionCleanupCoordinate;
};

const assertRevalidation = (
  value: unknown,
  coordinate: DeletionCleanupCoordinate,
  eligibilityDigest: string,
): void => {
  const receipt = exactDataRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch",
    "eligibility_digest", "state", "fence_receipt_digest",
  ]);
  if (receipt["version"] !== "deletion-cleanup-eligibility-fence-v1"
    || receipt["account_id"] !== coordinate.account_id
    || receipt["control_revision"] !== coordinate.control_revision
    || receipt["deletion_epoch"] !== coordinate.deletion_epoch
    || receipt["eligibility_digest"] !== eligibilityDigest
    || receipt["state"] !== "held"
    || typeof receipt["fence_receipt_digest"] !== "string"
    || !DIGEST.test(receipt["fence_receipt_digest"])) {
    throw new DeletionCleanupCompositeError("eligibility_revalidation_failed");
  }
};

const sameSurfaces = (
  actual: readonly DeletionCleanupSurface[],
  expected: readonly DeletionCleanupSurface[],
): boolean => actual.length === expected.length
  && new Set(actual).size === expected.length
  && actual.every((surface) => expected.includes(surface));

const denseArrayValues = <T>(
  value: unknown,
  code: DeletionCleanupCompositeErrorCode,
): readonly T[] => {
  if (!Array.isArray(value) || isProxy(value)) throw new DeletionCleanupCompositeError(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== value.length + 1
    || !Object.prototype.hasOwnProperty.call(descriptors, "length")) {
    throw new DeletionCleanupCompositeError(code);
  }
  const result: T[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
      throw new DeletionCleanupCompositeError(code);
    }
    result.push(descriptor.value as T);
  }
  return result;
};

interface ParticipantBinding {
  readonly id: string;
  readonly surfaces: readonly DeletionCleanupSurface[];
  readonly withFence: DeletionSurfaceParticipant["withHeldSurfaceFence"];
}

const bindParticipants = (
  participants: readonly DeletionSurfaceParticipant[],
): readonly ParticipantBinding[] => {
  if (!Array.isArray(participants) || participants.length === 0) {
    throw new DeletionCleanupCompositeError("invalid_configuration");
  }
  const allowed = new Set<DeletionCleanupSurface>(DELETION_CLEANUP_SURFACES);
  const owner = new Map<DeletionCleanupSurface, string>();
  const ids = new Set<string>();
  const bindings: ParticipantBinding[] = [];
  for (const participant of participants) {
    if (participant === null || typeof participant !== "object" || isProxy(participant)) {
      throw new DeletionCleanupCompositeError("invalid_configuration");
    }
    const descriptors = Object.getOwnPropertyDescriptors(participant);
    const idDescriptor = descriptors["participant_id"];
    const surfacesDescriptor = descriptors["owned_surfaces"];
    const methodDescriptor = descriptors["withHeldSurfaceFence"];
    if (!idDescriptor || !("value" in idDescriptor) || !idDescriptor.enumerable
      || !surfacesDescriptor || !("value" in surfacesDescriptor) || !surfacesDescriptor.enumerable
      || !methodDescriptor || !("value" in methodDescriptor)
      || typeof idDescriptor.value !== "string" || !PARTICIPANT_ID.test(idDescriptor.value)
      || ids.has(idDescriptor.value) || !Array.isArray(surfacesDescriptor.value)
      || isProxy(surfacesDescriptor.value) || surfacesDescriptor.value.length === 0
      || typeof methodDescriptor.value !== "function") {
      throw new DeletionCleanupCompositeError("invalid_configuration");
    }
    const id = idDescriptor.value;
    ids.add(id);
    const surfaces = Object.freeze([...denseArrayValues<DeletionCleanupSurface>(
      surfacesDescriptor.value, "invalid_configuration",
    )]);
    for (const surface of surfaces) {
      if (!allowed.has(surface) || owner.has(surface)) {
        throw new DeletionCleanupCompositeError("invalid_configuration");
      }
      owner.set(surface, id);
    }
    bindings.push(Object.freeze({
      id, surfaces,
      withFence: methodDescriptor.value.bind(participant) as DeletionSurfaceParticipant["withHeldSurfaceFence"],
    }));
  }
  if (owner.size !== DELETION_CLEANUP_SURFACES.length) {
    throw new DeletionCleanupCompositeError("invalid_configuration");
  }
  // A cyclic atomic disposal group cannot be split across independent stores.
  for (const group of DELETION_DISPOSAL_GROUPS) {
    if (new Set(group.map((surface) => owner.get(surface))).size !== 1) {
      throw new DeletionCleanupCompositeError("invalid_configuration");
    }
  }
  const rank = new Map(DELETION_DISPOSAL_GROUPS.flat()
    .map((surface, index) => [surface, index] as const));
  bindings.sort((left, right) => Math.min(...left.surfaces.map((surface) => rank.get(surface)!))
    - Math.min(...right.surfaces.map((surface) => rank.get(surface)!)));
  return Object.freeze(bindings);
};

const validateScan = (
  value: readonly DeletionInventorySourceReceipt[],
  expected: readonly DeletionCleanupSurface[],
): readonly DeletionInventorySourceReceipt[] => {
  const copies = denseArrayValues<DeletionInventorySourceReceipt>(value, "scan_failed")
    .map((receipt) => exactDataRecord(receipt, [
    "version", "inventory_contract_version", "scanner_contract_version", "account_id",
    "control_revision", "deletion_epoch", "surface", "source_frontier_digest",
    "source_authorization_digest", "scan_fence_state", "scan_fence_receipt_digest",
    "remaining_count", "remaining_set_digest",
    ], "scan_failed"));
  if (!sameSurfaces(copies.map((receipt) => receipt["surface"] as DeletionCleanupSurface), expected)) {
    throw new DeletionCleanupCompositeError("scan_failed");
  }
  return Object.freeze(copies.map((receipt) => Object.freeze(receipt) as unknown as DeletionInventorySourceReceipt));
};

const validateDisposition = (
  value: readonly DeletionCleanupDispositionReceipt[],
  expected: readonly DeletionCleanupSurface[],
): readonly DeletionCleanupDispositionReceipt[] => {
  const copies = denseArrayValues<DeletionCleanupDispositionReceipt>(value, "disposal_failed")
    .map((receipt) => exactDataRecord(
    receipt, ["version", "surface", "result", "receipt_digest"], "disposal_failed",
  ));
  if (!sameSurfaces(copies.map((receipt) => receipt["surface"] as DeletionCleanupSurface), expected)) {
    throw new DeletionCleanupCompositeError("disposal_failed");
  }
  for (const receipt of copies) {
    if (receipt["version"] !== "deletion-cleanup-disposition-v1"
      || (receipt["result"] !== "disposed" && receipt["result"] !== "already_absent")
      || typeof receipt["receipt_digest"] !== "string" || !DIGEST.test(receipt["receipt_digest"])) {
      throw new DeletionCleanupCompositeError("disposal_failed");
    }
  }
  return Object.freeze(copies.map((receipt) => Object.freeze(receipt) as unknown as DeletionCleanupDispositionReceipt));
};

/**
 * Adapts independently fenced stores to the complete cleanup coordinator. The
 * outer authority fence dominates all participant fences, and is revalidated
 * after the coordinator's final zero scan. Disposals remain independently
 * committed: retries repair partial progress, but no global rollback is
 * claimed.
 */
export const createCompositeAccountDeletionCleanupPort = (
  fenceCoordinator: DeletionEligibilityFenceCoordinator,
  participantValues: readonly DeletionSurfaceParticipant[],
): AccountDeletionCleanupPort => {
  if (fenceCoordinator === null || typeof fenceCoordinator !== "object" || isProxy(fenceCoordinator)) {
    throw new DeletionCleanupCompositeError("invalid_configuration");
  }
  const coordinatorMethod = Object.getOwnPropertyDescriptor(
    fenceCoordinator, "withHeldEligibilityFence",
  );
  if (!coordinatorMethod || !("value" in coordinatorMethod)
    || typeof coordinatorMethod.value !== "function") {
    throw new DeletionCleanupCompositeError("invalid_configuration");
  }
  const withEligibilityFence = coordinatorMethod.value.bind(fenceCoordinator) as
    DeletionEligibilityFenceCoordinator["withHeldEligibilityFence"];
  const participants = bindParticipants(participantValues);
  const owner = new Map<DeletionCleanupSurface, ParticipantBinding>();
  for (const participant of participants) {
    for (const surface of participant.surfaces) owner.set(surface, participant);
  }

  return Object.freeze({
    async withHeldFence<T>(
      coordinate: DeletionCleanupCoordinate,
      operationRef: string,
      eligibilityDigest: string,
      callback: (session: HeldDeletionCleanupSession) => Promise<T>,
    ): Promise<T> {
      let exactCoordinate: DeletionCleanupCoordinate;
      try { exactCoordinate = validatedCoordinate(coordinate); } catch {
        throw new DeletionCleanupCompositeError("invalid_input");
      }
      if (!OPERATION_REF.test(operationRef) || !DIGEST.test(eligibilityDigest)
        || typeof callback !== "function" || isProxy(callback)) {
        throw new DeletionCleanupCompositeError("invalid_input");
      }
      try {
        let eligibilityCallbackInvoked = false;
        let eligibilityCallbackBox: Readonly<{ result: T }> | null = null;
        let outerCallbackOpen = true;
        let returnedBox: Readonly<{ result: T }>;
        try {
          returnedBox = await withEligibilityFence(
          exactCoordinate, operationRef, eligibilityDigest, async (eligibilityFence) => {
            if (!outerCallbackOpen || eligibilityCallbackInvoked) {
              throw new DeletionCleanupCompositeError("eligibility_fence_failed");
            }
            eligibilityCallbackInvoked = true;
            const revalidateDescriptor = eligibilityFence !== null
              && typeof eligibilityFence === "object" && !isProxy(eligibilityFence)
              ? Object.getOwnPropertyDescriptor(eligibilityFence, "revalidateExact") : undefined;
            if (!revalidateDescriptor || !("value" in revalidateDescriptor)
              || typeof revalidateDescriptor.value !== "function") {
              throw new DeletionCleanupCompositeError("eligibility_fence_failed");
            }
            const revalidateExact = revalidateDescriptor.value.bind(eligibilityFence) as
              HeldDeletionEligibilityFence["revalidateExact"];
            const sessions = new Map<string, HeldDeletionSurfaceSession>();
            const acquire = async (index: number): Promise<T> => {
              if (index < participants.length) {
                const binding = participants[index]!;
                try {
                  let participantCallbackInvoked = false;
                  let participantCallbackBox: Readonly<{ result: T }> | null = null;
                  let participantCallbackOpen = true;
                  let participantReturnedBox: Readonly<{ result: T }>;
                  try {
                    participantReturnedBox = await binding.withFence(
                    exactCoordinate, operationRef, eligibilityDigest, async (session) => {
                      if (!outerCallbackOpen || !participantCallbackOpen || participantCallbackInvoked) {
                        throw new DeletionCleanupCompositeError("participant_fence_failed");
                      }
                      participantCallbackInvoked = true;
                      const sessionDescriptors: Record<string, PropertyDescriptor> =
                        session !== null && typeof session === "object" && !isProxy(session)
                          ? Object.getOwnPropertyDescriptors(session) : {};
                      const scan = sessionDescriptors["scanOwned"];
                      const dispose = sessionDescriptors["disposeOwned"];
                      if (!scan || !("value" in scan) || typeof scan.value !== "function"
                        || !dispose || !("value" in dispose) || typeof dispose.value !== "function") {
                        throw new DeletionCleanupCompositeError("participant_fence_failed");
                      }
                      sessions.set(binding.id, Object.freeze({
                        scanOwned: scan.value.bind(session) as HeldDeletionSurfaceSession["scanOwned"],
                        disposeOwned: dispose.value.bind(session) as HeldDeletionSurfaceSession["disposeOwned"],
                      }));
                      try {
                        const result = await acquire(index + 1);
                        if (!outerCallbackOpen || !participantCallbackOpen) {
                          throw new DeletionCleanupCompositeError("participant_fence_failed");
                        }
                        participantCallbackBox = Object.freeze({ result });
                        return participantCallbackBox;
                      } finally {
                        sessions.delete(binding.id);
                      }
                    });
                  } finally {
                    participantCallbackOpen = false;
                  }
                  if (!outerCallbackOpen) {
                    throw new DeletionCleanupCompositeError("eligibility_fence_failed");
                  }
                  if (participantCallbackBox === null
                    || participantReturnedBox !== participantCallbackBox) {
                    throw new DeletionCleanupCompositeError("participant_fence_failed");
                  }
                  return (participantCallbackBox as Readonly<{ result: T }>).result;
                } catch (error) {
                  if (error instanceof DeletionCleanupCompositeError) throw error;
                  throw new DeletionCleanupCompositeError("participant_fence_failed");
                }
              }

              if (!outerCallbackOpen) {
                throw new DeletionCleanupCompositeError("eligibility_fence_failed");
              }
              try {
                const receipt = await revalidateExact();
                if (!outerCallbackOpen) {
                  throw new DeletionCleanupCompositeError("eligibility_fence_failed");
                }
                assertRevalidation(receipt, exactCoordinate, eligibilityDigest);
              } catch (error) {
                if (error instanceof DeletionCleanupCompositeError) throw error;
                throw new DeletionCleanupCompositeError("eligibility_revalidation_failed");
              }

              let active = true;
              const pending = new Set<Promise<unknown>>();
              let pendingFailure: unknown = null;
              const track = <R>(operation: () => Promise<R>): Promise<R> => {
                if (!active) return Promise.reject(new DeletionCleanupCompositeError("scan_failed"));
                const promise = operation();
                pending.add(promise);
                void promise.then(
                  () => pending.delete(promise),
                  (error) => {
                    if (pendingFailure === null) pendingFailure = error;
                    pending.delete(promise);
                  },
                );
                return promise;
              };
              const combined: HeldDeletionCleanupSession = Object.freeze({
                async scanAll() {
                  return track(async () => {
                    const receipts: DeletionInventorySourceReceipt[] = [];
                    for (const binding of participants) {
                      const session = sessions.get(binding.id);
                      if (session === undefined) throw new DeletionCleanupCompositeError("scan_failed");
                      try {
                        receipts.push(...validateScan(await session.scanOwned(), binding.surfaces));
                      } catch {
                        throw new DeletionCleanupCompositeError("scan_failed");
                      }
                    }
                    return Object.freeze(receipts);
                  });
                },
                async dispose(surfaces: readonly DeletionCleanupSurface[]) {
                  return track(async () => {
                    let exactSurfaces: readonly DeletionCleanupSurface[];
                    try {
                      exactSurfaces = denseArrayValues<DeletionCleanupSurface>(
                        surfaces, "disposal_failed",
                      );
                    } catch {
                      throw new DeletionCleanupCompositeError("disposal_failed");
                    }
                    if (exactSurfaces.length === 0) {
                      throw new DeletionCleanupCompositeError("disposal_failed");
                    }
                    const binding = owner.get(exactSurfaces[0]!);
                    if (binding === undefined
                      || exactSurfaces.some((surface) => owner.get(surface) !== binding)
                      || !DELETION_DISPOSAL_GROUPS.some((group) => sameSurfaces(exactSurfaces, group))) {
                      throw new DeletionCleanupCompositeError("disposal_failed");
                    }
                    const session = sessions.get(binding.id);
                    if (session === undefined) throw new DeletionCleanupCompositeError("disposal_failed");
                    try {
                      return validateDisposition(
                        await session.disposeOwned(exactSurfaces), exactSurfaces,
                      );
                    } catch {
                      throw new DeletionCleanupCompositeError("disposal_failed");
                    }
                  });
                },
              });
              let result: T;
              let callbackFailure: unknown = null;
              try { result = await callback(combined); } catch (error) {
                callbackFailure = error;
                result = undefined as T;
              } finally {
                active = false;
                while (pending.size > 0) await Promise.allSettled([...pending]);
              }
              if (callbackFailure !== null) throw callbackFailure;
              if (pendingFailure !== null) throw pendingFailure;
              try {
                const receipt = await revalidateExact();
                if (!outerCallbackOpen) {
                  throw new DeletionCleanupCompositeError("eligibility_fence_failed");
                }
                assertRevalidation(receipt, exactCoordinate, eligibilityDigest);
              } catch (error) {
                if (error instanceof DeletionCleanupCompositeError) throw error;
                throw new DeletionCleanupCompositeError("eligibility_revalidation_failed");
              }
              return result;
            };
            const result = await acquire(0);
            if (!outerCallbackOpen) {
              throw new DeletionCleanupCompositeError("eligibility_fence_failed");
            }
            eligibilityCallbackBox = Object.freeze({ result });
            return eligibilityCallbackBox;
          });
        } finally {
          outerCallbackOpen = false;
        }
        if (eligibilityCallbackBox === null || returnedBox !== eligibilityCallbackBox) {
          throw new DeletionCleanupCompositeError("eligibility_fence_failed");
        }
        return (eligibilityCallbackBox as Readonly<{ result: T }>).result;
      } catch (error) {
        if (error instanceof DeletionCleanupCompositeError) throw error;
        throw new DeletionCleanupCompositeError("eligibility_fence_failed");
      }
    },
  });
};
