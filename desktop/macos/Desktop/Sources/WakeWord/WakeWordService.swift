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
    let parsed = WakeWordSegmentParser.command(
      after: segment.text,
      wakePhrase: AssistantSettings.shared.wakeWordPhrase)

    // Every rejection below used to be silent, so a wake word that never fired
    // was indistinguishable from one that was never spoken. Only segments that
    // actually carry the wake phrase are reported, so ordinary speech stays quiet.
    func ignore(_ reason: String) {
      if parsed != nil { log("WakeWord: ignored — \(reason)") }
    }

    guard AssistantSettings.shared.wakeWordEnabled else { return ignore("disabled in settings") }
    guard !isConversationActive else { return ignore("assistant already busy") }
    // Diarization only sets `isUser` once a speech profile is enrolled, so requiring
    // it alone makes the wake word silently dead for every user who has not enrolled
    // one. Speaker 0 is the primary user everywhere else in this feature set —
    // `VoiceBargeInPolicy` gates on `isUser || speaker == 0` for exactly this reason.
    guard segment.isUser || segment.speaker == 0 else {
      return ignore("segment not attributed to the user (speaker \(segment.speaker))")
    }
    guard let command = parsed else { return }
    // The backend re-delivers a growing segment under one id (observed live:
    // [206.0s-217.1s] → [206.0s-228.9s]), so deduping on the id alone silently
    // drops every later command that lands inside an id that already fired.
    // Key on the extracted command so a re-sent segment is suppressed but a new
    // instruction inside the same segment still runs.
    let dedupKey = segment.segmentId.map { "\($0)|\(command)" }
    if let key = dedupKey, firedSegmentIDs.contains(key) {
      return ignore("segment \(segment.segmentId ?? "?") already fired for '\(command)'")
    }
    guard Self.wordCount(command) >= minimumCommandWords else {
      return ignore("command '\(command)' is shorter than \(minimumCommandWords) words")
    }
    let current = now()
    // The cooldown exists to swallow a rapid repeat of the same utterance, not to
    // ration distinct instructions. The ambient transcript lane runs ~35s behind
    // live speech (measured), so several genuinely different commands routinely
    // arrive inside one 30s window; gating on time alone silently discarded them.
    if let last = lastTriggeredAt, command == lastTriggeredCommand {
      let interval = current.timeIntervalSince(last)
      if interval >= 0 && interval < AssistantSettings.shared.wakeWordCooldown {
        return ignore("cooldown — repeat of '\(command)' \(Int(interval))s after the last trigger")
      }
    }
    if let key = dedupKey {
      firedSegmentIDs.append(key)
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
