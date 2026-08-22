import Foundation

@MainActor
final class WakeWordService {
  static let shared = WakeWordService()

  /// Separates a segment id from the command it fired, in `firedSegmentIDs`.
  /// A control character so it cannot occur inside either half.
  private static let dedupSeparator: Character = "\u{1}"

  private var lastTriggeredAt: Date?
  private var firedSegmentIDs: [String] = []
  private let maxRememberedSegmentIDs = 100
  private let minimumCommandWords = 2

  var now: @MainActor () -> Date = { Date() }
  var onTrigger: @MainActor (String) -> Void = { command in
    log("WakeWord: submitting '\(command)' to the assistant")
    // `fromVoice: true` is reserved for callers that own a voice-turn lifecycle:
    // `openAIInputWithQuery` guards it behind `voiceTurnID` +
    // `VoiceTurnCoordinator.requireCurrentOwner` and returns silently when either is
    // missing, so passing it without a turn drops the query with no diagnostic.
    // Push-to-talk owns a turn and passes both; the wake word, like the automation
    // bridge, submits an already-transcribed command and owns no turn.
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
    // A backend segment is re-delivered as it grows, in place and under one id
    // (observed live: "what time it is?" → "what time it is? You speak English.
    // Got it."). Deduping on the id alone drops a genuinely new instruction that
    // lands in a reused id; deduping on the exact command re-fires on every growth
    // with a longer, more polluted string. Treat a command that extends one already
    // fired for this segment as the same instruction, and anything else as new.
    if let id = segment.segmentId {
      let priorCommands = firedSegmentIDs.compactMap { entry -> String? in
        let parts = entry.split(separator: Self.dedupSeparator, maxSplits: 1)
        guard parts.count == 2, parts[0] == id else { return nil }
        return String(parts[1])
      }
      if let prior = priorCommands.first(where: { command.hasPrefix($0) || $0.hasPrefix(command) }) {
        return ignore("segment \(id) already fired for '\(prior)'")
      }
    }
    let dedupKey = segment.segmentId.map { "\($0)\(Self.dedupSeparator)\(command)" }
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
