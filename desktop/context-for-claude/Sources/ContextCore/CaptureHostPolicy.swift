import Foundation

/// Pure host/capture policy for Context for Claude.
///
/// Inject `isAppleSilicon` in tests so Intel behavior can be asserted on any runner.
/// Runtime detection lives in the app (`HostArchitecture`); this type never touches sysctl.
public struct CaptureHostPolicy: Equatable, Sendable {
    public let isAppleSilicon: Bool

    public init(isAppleSilicon: Bool) {
        self.isAppleSilicon = isAppleSilicon
    }

    /// On-device Parakeet (FluidAudio / ANE) is Apple Silicon only. Intel is cloud ASR only.
    public var usesLocalSTT: Bool { isAppleSilicon }

    /// Screen OCR stays on-device everywhere; Intel runs a slower cadence so always-on capture
    /// stays usable on 2020-class Intel machines.
    public var screenCaptureInterval: TimeInterval {
        isAppleSilicon ? Self.appleSiliconScreenInterval : Self.intelScreenInterval
    }

    public static let appleSiliconScreenInterval: TimeInterval = 3.0
    public static let intelScreenInterval: TimeInterval = 9.0

    /// A local model failure must never stop mic/system capture or the cloud audio feed.
    public static let localSTTFailureStopsCapture = false
}

/// Whether one audio source should start a local Parakeet instance, and what happens if that
/// load fails. Kept separate from `CaptureHostPolicy` so Engine can branch without re-deriving.
public struct AudioCaptureDecision: Equatable, Sendable {
    public let startLocalSTT: Bool
    /// Always false: local STT is resilience under cloud, never a gate on capture.
    public let teardownCaptureOnLocalSTTFailure: Bool

    public init(startLocalSTT: Bool, teardownCaptureOnLocalSTTFailure: Bool) {
        self.startLocalSTT = startLocalSTT
        self.teardownCaptureOnLocalSTTFailure = teardownCaptureOnLocalSTTFailure
    }

    public static func make(usesLocalSTT: Bool) -> AudioCaptureDecision {
        AudioCaptureDecision(
            startLocalSTT: usesLocalSTT,
            teardownCaptureOnLocalSTTFailure: CaptureHostPolicy.localSTTFailureStopsCapture
        )
    }
}

/// Coarse cloud socket state, mirrored from the app's `ListenSocket.State` so policy stays free
/// of UI / networking types.
public enum CloudTranscriptionState: String, Sendable, Equatable {
    case idle
    case connecting
    case live
    case failed
    case paywalled
    case airgapped
}

/// Raw listen-socket snapshot before Engine softens it for gap UI (signed-in idle → connecting,
/// reconnecting failure → connecting).
public enum CloudSocketSnapshot: Equatable, Sendable {
    case idle
    case connecting
    case live
    case failed(String)
    case paywalled
    case airgapped
}

/// What to do with a PCM chunk that cannot leave the client immediately.
public enum CloudOutboundPCMAction: String, Sendable, Equatable {
    case transmit
    case buffer
    case drop
}

/// Socket phase for outbound PCM policy — same cases as `ListenSocket.State` without networking types.
public enum CloudOutboundPCMPhase: String, Sendable, Equatable {
    case idle
    case connecting
    case live
    case failed
    case paywalled
    case airgapped
}

extension CaptureHostPolicy {
    /// Maps a listen-socket snapshot onto the coarse cloud state Engine uses for gap copy.
    ///
    /// Signed-in `.idle` is the brief window after `wantsConnection` flips true and before the
    /// socket reports `.connecting` — treat it as connecting so Intel does not flash an offline
    /// gap. A `.failed` detail that says "reconnecting" is the same recoverable window.
    public static func resolvedCloudTranscriptionState(
        socket: CloudSocketSnapshot,
        isSignedIn: Bool
    ) -> CloudTranscriptionState {
        switch socket {
        case .idle:
            return isSignedIn ? .connecting : .idle
        case .connecting:
            return .connecting
        case .live:
            return .live
        case .failed(let detail):
            return detail.localizedCaseInsensitiveContains("reconnecting") ? .connecting : .failed
        case .paywalled:
            return .paywalled
        case .airgapped:
            return .airgapped
        }
    }

    /// Whether outbound PCM should be held until the socket can take it.
    ///
    /// Critical for Intel: there is no local Parakeet under the mixer, so dropping audio while
    /// `wantsConnection` is true but the phase is still `.idle` (start has run, connect has not
    /// flipped state yet) permanently loses those words. `.airgapped` always drops — buffering
    /// would keep audio for an upload the user has forbidden.
    public static func outboundPCMAction(
        phase: CloudOutboundPCMPhase,
        wantsConnection: Bool,
        hasLiveTask: Bool
    ) -> CloudOutboundPCMAction {
        switch phase {
        case .live:
            return hasLiveTask ? .transmit : .buffer
        case .connecting:
            return .buffer
        case .idle, .failed:
            return wantsConnection ? .buffer : .drop
        case .paywalled, .airgapped:
            return .drop
        }
    }

    /// Resume wipe keeps only storage; transcription gaps must be re-applied afterwards.
    public static func reasonsAfterResumeWipe<Key: Hashable>(
        _ reasons: [Key: String],
        storageKey: Key
    ) -> [Key: String] {
        reasons.filter { $0.key == storageKey }
    }

    /// Honest gap copy when this host has no local STT and cloud is not producing transcripts.
    ///
    /// Returns nil while cloud is live or still connecting, and always nil when local STT is
    /// available (Silicon can fall back on-device).
    public static func cloudTranscriptionGapReason(
        usesLocalSTT: Bool,
        isSignedIn: Bool,
        cloud: CloudTranscriptionState
    ) -> String? {
        guard !usesLocalSTT else { return nil }
        switch cloud {
        case .live, .connecting:
            return nil
        case .paywalled:
            return "Transcription off — Omi trial expired; upgrade to keep transcripts on this Mac"
        case .airgapped:
            return "Transcription off — Airgap Mode is on; turn it off to send audio to Omi"
        case .idle, .failed:
            if !isSignedIn {
                return "Transcription needs an Omi account — sign in to keep transcripts on this Mac"
            }
            return "Transcription needs a network connection to Omi — audio is still captured but nothing is being transcribed"
        }
    }
}
