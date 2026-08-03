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
}

extension CaptureHostPolicy {
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
        case .idle, .failed:
            if !isSignedIn {
                return "Transcription needs an Omi account — sign in to keep transcripts on this Mac"
            }
            return "Transcription needs a network connection to Omi — audio is still captured but nothing is being transcribed"
        }
    }
}
