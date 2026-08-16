import type { PlatformListenPreflightSnapshot } from "@omi-core/adapters-platform";
import type { MessageKey } from "@omi-core/i18n";
import type { CaptureDescription, CaptureState } from "./capture-state.js";

type CatalogKey<T extends MessageKey> = T;

export type ListenIdleReason =
  | "ready"
  | "ended"
  | "ended-empty"
  | "permission-needed"
  | "permission-checking"
  | "permission-denied"
  | "permission-restricted"
  | "permission-unavailable"
  | "device-unavailable";

export type ListenPanelTitleKey = CatalogKey<
  | CaptureDescription["titleKey"]
  | "listen.stateEnded"
  | "listen.stateEndedEmpty"
  | "listen.statePermissionNeeded"
  | "listen.statePermissionChecking"
  | "listen.statePermissionDenied"
  | "listen.statePermissionRestricted"
  | "listen.statePermissionUnavailable"
  | "listen.stateDeviceUnavailable"
>;

export type ListenPanelBodyKey = CatalogKey<
  | CaptureDescription["bodyKey"]
  | "listen.stateEndedBody"
  | "listen.stateEndedEmptyBody"
  | "listen.statePermissionNeededBody"
  | "listen.statePermissionCheckingBody"
  | "listen.statePermissionDeniedBody"
  | "listen.statePermissionRestrictedBody"
  | "listen.statePermissionUnavailableBody"
  | "listen.stateDeviceUnavailableBody"
>;

export type ListenPanelCopy = {
  readonly titleKey: ListenPanelTitleKey;
  readonly bodyKey: ListenPanelBodyKey;
  readonly idleReason: ListenIdleReason | null;
  readonly showConversationsLink: boolean;
};

/**
 * Single fold for the Listen state-panel heading. Idle is not "ready" when
 * permission, device, or a just-ended session say otherwise. Callers must
 * render these keys; a leftover `else` Ready claim is the bug this exists to
 * prevent.
 */
export function listenPanelCopy(input: {
  capture: CaptureState;
  description: CaptureDescription;
  preflight: PlatformListenPreflightSnapshot;
  segmentCount: number;
  emptyEnded: boolean;
}): ListenPanelCopy {
  if (input.capture.kind !== "idle") {
    return {
      titleKey: input.description.titleKey,
      bodyKey: input.description.bodyKey,
      idleReason: null,
      showConversationsLink: false,
    };
  }

  const permission = input.preflight.permission;
  const device = input.preflight.device.state;
  if (permission === "checking") {
    return {
      titleKey: "listen.statePermissionChecking",
      bodyKey: "listen.statePermissionCheckingBody",
      idleReason: "permission-checking",
      showConversationsLink: false,
    };
  }
  if (permission === "unknown" || input.preflight.recovery === "request-permission") {
    return {
      titleKey: "listen.statePermissionNeeded",
      bodyKey: "listen.statePermissionNeededBody",
      idleReason: "permission-needed",
      showConversationsLink: false,
    };
  }
  if (permission === "denied") {
    return {
      titleKey: "listen.statePermissionDenied",
      bodyKey: "listen.statePermissionDeniedBody",
      idleReason: "permission-denied",
      showConversationsLink: false,
    };
  }
  if (permission === "restricted") {
    return {
      titleKey: "listen.statePermissionRestricted",
      bodyKey: "listen.statePermissionRestrictedBody",
      idleReason: "permission-restricted",
      showConversationsLink: false,
    };
  }
  if (permission === "unavailable") {
    return {
      titleKey: "listen.statePermissionUnavailable",
      bodyKey: "listen.statePermissionUnavailableBody",
      idleReason: "permission-unavailable",
      showConversationsLink: false,
    };
  }
  if (device !== "available") {
    return {
      titleKey: "listen.stateDeviceUnavailable",
      bodyKey: "listen.stateDeviceUnavailableBody",
      idleReason: "device-unavailable",
      showConversationsLink: false,
    };
  }
  if (input.emptyEnded) {
    return {
      titleKey: "listen.stateEndedEmpty",
      bodyKey: "listen.stateEndedEmptyBody",
      idleReason: "ended-empty",
      showConversationsLink: false,
    };
  }
  if (input.segmentCount > 0) {
    return {
      titleKey: "listen.stateEnded",
      bodyKey: "listen.stateEndedBody",
      idleReason: "ended",
      showConversationsLink: true,
    };
  }
  return {
    titleKey: input.description.titleKey,
    bodyKey: input.description.bodyKey,
    idleReason: "ready",
    showConversationsLink: false,
  };
}
