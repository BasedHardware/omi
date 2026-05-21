import Foundation

enum BackgroundTranscriptionRoutingDecision: Equatable {
  case cloudBatchAssembly
  case cloudListenStreaming(reason: String?)
}

struct BackgroundTranscriptionRoutingGuard {
  func decide(
    serverAssemblyBackgroundEnabled: Bool,
    audioSource: AudioSource
  ) -> BackgroundTranscriptionRoutingDecision {
    guard serverAssemblyBackgroundEnabled else {
      return .cloudListenStreaming(reason: "server_background_batch_disabled")
    }
    guard audioSource == .microphone else {
      return .cloudListenStreaming(reason: "batch_microphone_only")
    }
    return .cloudBatchAssembly
  }
}
