import Foundation

enum BackgroundTranscriptionRoutingDecision: Equatable {
  case cloudBatchAssembly
  case cloudListenStreaming(reason: String?)
}

struct BackgroundTranscriptionRoutingGuard {
  func decide(
    backgroundBatchCapability: DesktopBackgroundBatchCapability?,
    audioSource: AudioSource
  ) -> BackgroundTranscriptionRoutingDecision {
    guard audioSource == .microphone else {
      return .cloudListenStreaming(reason: "batch_microphone_only")
    }
    guard let capability = backgroundBatchCapability else {
      return .cloudListenStreaming(reason: "server_background_batch_capability_unavailable")
    }
    guard capability.enabled else {
      return .cloudListenStreaming(reason: capability.reason ?? "server_background_batch_disabled")
    }
    guard let effectiveProvider = capability.effectiveProvider?.lowercased() else {
      return .cloudListenStreaming(reason: capability.reason ?? "server_background_batch_provider_unavailable")
    }
    guard effectiveProvider == "assemblyai" || effectiveProvider == "deepgram" else {
      return .cloudListenStreaming(reason: capability.reason ?? "server_background_batch_provider_unsupported")
    }
    return .cloudBatchAssembly
  }

  func shouldFallbackToStreamingAfterBatchStartupFailure(
    audioSource: AudioSource,
    captureStarted: Bool
  ) -> Bool {
    audioSource == .microphone && !captureStarted
  }
}
