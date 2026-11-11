import Foundation

extension RealtimeHubController {
  func observeAssistantVoiceChanges() {
    NotificationCenter.default.removeObserver(self, name: .assistantVoiceDidChange, object: nil)
    NotificationCenter.default.addObserver(
      self, selector: #selector(assistantVoiceChanged),
      name: .assistantVoiceDidChange, object: nil)
  }

  @objc private func assistantVoiceChanged() {
    requestSessionHandoff(reason: .assistantVoice)
  }

  nonisolated static func acknowledgementVoiceName(_ provider: RealtimeHubProvider, _ voiceID: String?) -> String {
    RealtimeHubVoicePolicy.voiceName(for: provider, assistantVoiceID: voiceID ?? "Charon")
  }
}
