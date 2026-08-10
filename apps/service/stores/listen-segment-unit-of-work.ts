// domain-pending(DIV-DOMCORE-012)
// domain-pending(UNK-DOMAPPS-001)

import type { SettingsEntitlementProjection } from "../control/settings-projection";
import type { ListenTranscriptSegment } from "./listen-store";
import type {
  UnitOfWorkContext,
  UnitOfWorkEffect,
} from "./unit-of-work-context";

const LISTEN_SEGMENT_UNIT_OF_WORK_PORT: unique symbol = Symbol("listen-segment-unit-of-work");

export interface ListenSegmentReservationInput {
  readonly accountId: string;
  readonly sessionId: string;
  readonly segment: ListenTranscriptSegment;
  readonly consumedSeconds: number;
  readonly at: string;
}

export interface ListenSegmentReservationOutcome {
  readonly kind: "accepted";
  readonly segment: ListenTranscriptSegment;
  readonly inserted: boolean;
  readonly entitlement: SettingsEntitlementProjection | null;
}

/** One atomic, idempotent reservation of transcript durability and metered usage. */
export interface ListenSegmentUnitOfWork {
  readonly [LISTEN_SEGMENT_UNIT_OF_WORK_PORT]: true;
  reserve(input: ListenSegmentReservationInput): Promise<ListenSegmentReservationOutcome>;
}

export interface ListenSegmentUnitOfWorkTransaction<Connection extends object> {
  execute<Result>(
    input: ListenSegmentReservationInput,
    operation: (context: UnitOfWorkContext<Connection>) => Result,
  ): Promise<Result>;
}

export interface ListenSegmentUnitOfWorkOperations<Connection extends object> {
  readEntitlement(
    context: UnitOfWorkContext<Connection>,
    input: ListenSegmentReservationInput,
  ): UnitOfWorkEffect<Connection, SettingsEntitlementProjection | null>;
  appendSegment(
    context: UnitOfWorkContext<Connection>,
    input: ListenSegmentReservationInput,
  ): UnitOfWorkEffect<Connection, { readonly segment: ListenTranscriptSegment; readonly inserted: boolean }>;
  consumeTranscriptionSeconds(
    context: UnitOfWorkContext<Connection>,
    input: ListenSegmentReservationInput,
  ): UnitOfWorkEffect<Connection, SettingsEntitlementProjection | null>;
}

/** The only constructor for the sealed listen reservation port. */
export const defineListenSegmentUnitOfWork = <Connection extends object>(
  transaction: ListenSegmentUnitOfWorkTransaction<Connection>,
  operations: ListenSegmentUnitOfWorkOperations<NoInfer<Connection>>,
): ListenSegmentUnitOfWork => Object.freeze({
  [LISTEN_SEGMENT_UNIT_OF_WORK_PORT]: true as const,
  reserve(input: ListenSegmentReservationInput): Promise<ListenSegmentReservationOutcome> {
    return transaction.execute(input, (context) => {
      const before = context.resolve(operations.readEntitlement(context, input));
      const appended = context.resolve(operations.appendSegment(context, input));
      const entitlement = appended.inserted
        ? context.resolve(operations.consumeTranscriptionSeconds(context, input))
        : before;
      return Object.freeze({
        kind: "accepted" as const,
        segment: appended.segment,
        inserted: appended.inserted,
        entitlement,
      });
    });
  },
});
