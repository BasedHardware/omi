import Foundation

@MainActor
final class FloatingBarVoicePlaybackService {
  static let shared = FloatingBarVoicePlaybackService()

  private init() {}

  func playResponseIfEnabled(_ message: ChatMessage?) {}

  func updateStreamingResponseIfEnabled(_ message: ChatMessage?, isFinal: Bool) {}

  func stop() {}
}
