import Foundation

@MainActor
final class WakeWordService {
  static let shared = WakeWordService()

  private var lastTriggeredAt: Date?
  private var firedSegmentIDs: [String] = []
  private let maxRememberedSegmentIDs = 100
  private let minimumCommandWords = 2

  var now: @MainActor () -> Date = { Date() }
  var onTrigger: @MainActor (String) -> Void = { command in
    log("WakeWord: submitting '\(command)' to the assistant")
    FloatingControlBarManager.shared.openAIInputWithQuery(command, fromVoice: false)
  }
  private(set) var lastTriggeredCommand: String?

  init() {}

  func observe(
    _ segment: SpeakerSegment,
    isConversationActive: Bool = WakeWordService.defaultIsConversationActive()
  ) {
    guard AssistantSettings.shared.wakeWordEnabled else { return }
    guard !isConversationActive else { return }
    guard segment.isUser else { return }
    if let id = segment.segmentId, firedSegmentIDs.contains(id) { return }
    guard
      let command = WakeWordSegmentParser.command(
        after: segment.text,
        wakePhrase: AssistantSettings.shared.wakeWordPhrase)
    else { return }
    guard Self.wordCount(command) >= minimumCommandWords else { return }
    let current = now()
    if let last = lastTriggeredAt {
      let interval = current.timeIntervalSince(last)
      if interval >= 0 && interval < AssistantSettings.shared.wakeWordCooldown { return }
    }
    if let id = segment.segmentId {
      firedSegmentIDs.append(id)
      if firedSegmentIDs.count > maxRememberedSegmentIDs {
        firedSegmentIDs.removeFirst(firedSegmentIDs.count - maxRememberedSegmentIDs)
      }
    }
    lastTriggeredAt = current
    lastTriggeredCommand = command
    onTrigger(command)
  }

  static func wordCount(_ text: String) -> Int {
    text.split(whereSeparator: \.isWhitespace).count
  }

  static func defaultIsConversationActive() -> Bool {
    if let provider = ChatProvider.mainInstance, provider.isSending { return true }
    if VoiceTurnCoordinator.shared.activeTurnID != nil { return true }
    return false
  }
}