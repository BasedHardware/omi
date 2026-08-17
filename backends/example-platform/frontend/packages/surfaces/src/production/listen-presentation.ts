import type { PlatformListenPreflightSnapshot } from "@omi-core/adapters-platform";
import type { MessageKey } from "@omi-core/i18n";
import type { TranscriptSegment } from "@omi-core/wire-listen";
import type { CaptureDescription, CaptureState } from "./capture-state.js";

/**
 * Exact canned lines `createScriptedTranscriptionSource` emits. Keep in lockstep
 * with `SCRIPTED_LOCAL_TRANSCRIPT_TEXTS` in apps/service/listen/transcription-source.ts.
 * A Listen panel that shows only these lines is not the user's speech.
 */
export const SCRIPTED_LISTEN_TRANSCRIPT_CONNECTED = "Local transcription is connected.";
export const SCRIPTED_LISTEN_TRANSCRIPT_TIMING = "This segment arrived with real timing.";
export const SCRIPTED_LISTEN_TRANSCRIPT_TEXTS = Object.freeze([
  SCRIPTED_LISTEN_TRANSCRIPT_CONNECTED,
  SCRIPTED_LISTEN_TRANSCRIPT_TIMING,
]);

export function isScriptedListenTranscript(
  segments: readonly Pick<TranscriptSegment, "text">[],
): boolean {
  if (segments.length === 0) return false;
  return segments.every((segment) => (
    SCRIPTED_LISTEN_TRANSCRIPT_TEXTS as readonly string[]
  ).includes(segment.text.trim()));
}

/**
 * Who said a segment, as a kind rather than a rendered string, so the caller
 * owns the copy. Mirrors `LiveSegmentView.speakerLabel` in the macOS shell:
 * the user is answered before any diarisation label, because a segment can
 * carry both and "You" is the truer of the two.
 *
 * `unknown` has no Swift counterpart — its model always holds an integer
 * speaker. Our wire makes both `speaker` and `speaker_id` optional, so an
 * anonymous segment gets no attribution rather than an invented one.
 */
export type ListenSpeakerIdentity =
  | { readonly kind: "self" }
  | { readonly kind: "named"; readonly name: string }
  | { readonly kind: "numbered"; readonly number: number }
  | { readonly kind: "unknown" };

export function listenSpeakerIdentity(
  segment: Pick<TranscriptSegment, "is_user" | "speaker" | "speaker_id">,
): ListenSpeakerIdentity {
  if (segment.is_user) return { kind: "self" };
  const name = segment.speaker?.trim() ?? "";
  if (name !== "") return { kind: "named", name };
  const id = segment.speaker_id;
  if (typeof id === "number" && Number.isFinite(id)) return { kind: "numbered", number: id };
  return { kind: "unknown" };
}

/**
 * The glyph on a speaker's avatar disc. A numbered speaker shows the number
 * itself, not the "S" of "Speaker 3" — the disc has to distinguish speakers
 * from each other, and every numbered label starts with the same letter.
 */
export function listenSpeakerInitial(
  identity: ListenSpeakerIdentity,
  label: string,
): string | null {
  if (identity.kind === "unknown") return null;
  if (identity.kind === "numbered") return String(identity.number);
  const first = Array.from(label.trim())[0];
  return first === undefined ? null : first.toLocaleUpperCase();
}

/**
 * A segment's offset into the capture, as the `M:SS` clock the macOS shell
 * sets beside every speaker label (`LiveTranscriptView.formatTime`).
 *
 * Deliberately not `formatDuration`: this is a position on a running
 * recording, which reads as a clock, and the i18n duration formatter answers
 * a different question ("1m 5s"). Minutes are not wrapped into hours, so a
 * long capture reads `61:01` exactly as Swift's `%d:%02d` does.
 */
export function listenSegmentClock(seconds: number): string {
  const total = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

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
