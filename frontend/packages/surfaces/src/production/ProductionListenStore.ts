import type { StoreStatus } from "@omi-core/domain";
import type { PlatformListenPreflightSnapshot } from "@omi-core/adapters-platform";
import type { ListenEntitlementSnapshot, TranscriptSegment } from "@omi-core/wire-listen";
import type { CaptureState } from "./capture-state.js";

export type { CaptureState };

/**
 * Surface-facing composition boundary for Listen / capture.
 *
 * FE-CORE supplies the typed stream port that will drive this store; BE-INTEL
 * serves the stream. This file is only the observable surface port — status /
 * subscribe / refresh match the other production stores so the component can
 * reuse the exemplar lifecycle, plus captureState / start / stop for the
 * capture capacity contract. There is no user "pause" control: pause states
 * are entitlement- or connectivity-driven.
 */
export type ProductionListenStore = {
  status(): StoreStatus;
  subscribe(listener: () => void): () => void;
  refresh(): Promise<void>;
  captureState(): CaptureState;
  transcriptSegments(): readonly TranscriptSegment[];
  entitlementState(): ListenEntitlementSnapshot | null;
  start(): Promise<void>;
  stop(): Promise<void>;
  /** Native permission/device facts; absent only on legacy fixture stores. */
  preflight?(): PlatformListenPreflightSnapshot;
  requestPermission?(): Promise<void>;
  openSettings?(): Promise<void>;
};
