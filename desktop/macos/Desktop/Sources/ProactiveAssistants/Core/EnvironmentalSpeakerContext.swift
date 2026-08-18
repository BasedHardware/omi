import Foundation

/// Environmental analysis of ambient audio: detects multi-party calls, meetings,
/// active speaker count, and identified participant names from live diarization.
///
/// Bridges raw diarization segments into a structured context signal for the
/// assistant and director prompt, enabling awareness of other people in the
/// conversation (e.g. "I noticed another person in your call").
struct EnvironmentalSpeakerSignal: Equatable, Sendable {
  let totalUniqueSpeakers: Int
  let otherSpeakerCount: Int
  let otherParticipantLabels: [String]
  let recentOtherSpeakerTurns: Int
  let isMultiPartyCall: Bool

  init(
    totalUniqueSpeakers: Int,
    otherSpeakerCount: Int,
    otherParticipantLabels: [String],
    recentOtherSpeakerTurns: Int,
    isMultiPartyCall: Bool
  ) {
    self.totalUniqueSpeakers = totalUniqueSpeakers
    self.otherSpeakerCount = otherSpeakerCount
    self.otherParticipantLabels = otherParticipantLabels
    self.recentOtherSpeakerTurns = recentOtherSpeakerTurns
    self.isMultiPartyCall = isMultiPartyCall
  }

  /// Empty / solo baseline when no other speakers are present
  static let solo = EnvironmentalSpeakerSignal(
    totalUniqueSpeakers: 1,
    otherSpeakerCount: 0,
    otherParticipantLabels: [],
    recentOtherSpeakerTurns: 0,
    isMultiPartyCall: false
  )
}

/// Pure analyzer for extracting environmental speaker context from live segments
enum EnvironmentalSpeakerAnalyzer {
  /// Recent window (seconds) to consider a speaker active in the current interaction
  static let activeWindowSeconds: Double = 180.0

  /// Analyze speaker segments and optional person map to produce an environmental signal
  static func analyze(
    segments: [SpeakerSegment],
    speakerPersonMap: [Int: String] = [:],
    now: Double? = nil
  ) -> EnvironmentalSpeakerSignal {
    guard !segments.isEmpty else { return .solo }

    // Reference time: use the end time of the latest segment if not explicitly supplied
    let referenceTime = now ?? (segments.last?.end ?? 0.0)
    let windowStart = max(0.0, referenceTime - activeWindowSeconds)

    // Filter segments within the active window
    let recentSegments = segments.filter { $0.end >= windowStart }
    guard !recentSegments.isEmpty else { return .solo }

    var userSeen = false
    var otherSpeakers = Set<Int>()
    var otherSpeakerTurnCount = 0

    for segment in recentSegments {
      if segment.isUser || segment.speaker == 0 {
        userSeen = true
      } else {
        otherSpeakers.insert(segment.speaker)
        otherSpeakerTurnCount += 1
      }
    }

    let otherSpeakerCount = otherSpeakers.count
    let totalSpeakers = (userSeen ? 1 : 0) + otherSpeakerCount

    guard otherSpeakerCount > 0 else {
      return EnvironmentalSpeakerSignal(
        totalUniqueSpeakers: max(1, totalSpeakers),
        otherSpeakerCount: 0,
        otherParticipantLabels: [],
        recentOtherSpeakerTurns: 0,
        isMultiPartyCall: false
      )
    }

    // Resolve human-readable labels for each non-user speaker
    let labels: [String] = otherSpeakers.sorted().map { speakerId in
      if let personName = speakerPersonMap[speakerId],
        !personName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      {
        return sanitizeLabel(personName)
      }
      return "Participant (Speaker \(speakerId))"
    }

    return EnvironmentalSpeakerSignal(
      totalUniqueSpeakers: totalSpeakers,
      otherSpeakerCount: otherSpeakerCount,
      otherParticipantLabels: labels,
      recentOtherSpeakerTurns: otherSpeakerTurnCount,
      isMultiPartyCall: true
    )
  }

  /// Format as a volatile prompt section for the director / assistant
  static func promptSection(_ signal: EnvironmentalSpeakerSignal) -> String? {
    guard signal.isMultiPartyCall, !signal.otherParticipantLabels.isEmpty else {
      return nil
    }

    let participantsList = signal.otherParticipantLabels.joined(separator: ", ")
    let plural = signal.otherSpeakerCount == 1 ? "participant" : "participants"

    return """
      == ENVIRONMENTAL / CALL CONTEXT ==
      Multi-party interaction detected: \(signal.totalUniqueSpeakers) active speakers (You + \(participantsList)).
      Recent turns from other \(plural): \(signal.recentOtherSpeakerTurns).
      Context: User is on a call or in a meeting with other people. Ground recommendations and actions in the presence of other participants.
      """
  }

  private static func sanitizeLabel(_ name: String) -> String {
    // Flatten newlines and limit length to prevent prompt injection
    let singleLine = name.replacingOccurrences(of: "\n", with: " ")
      .replacingOccurrences(of: "\r", with: "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    if singleLine.count > 40 {
      return String(singleLine.prefix(40))
    }
    return singleLine
  }
}
