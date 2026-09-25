//
//  SpeakerLabelFormatter.swift — what a transcript speaker is called, everywhere.
//
//  One speaker used to have up to four names depending on where you looked: "Speaker 1" in the
//  bubble, "SPEAKER_01" in the Participants line, "Speaker SPEAKER_01" in the copied transcript, and
//  "Speaker 1" again (ignoring a named person) from the row menu's copy. A label that could not be
//  parsed became "Speaker 0".
//
//  Numbering is 1-based to match mobile (`TranscriptSegment.getDisplaySpeakerId`), so the same
//  conversation shows the same speaker number on every client.
//

import Foundation
import OmiSupport

struct SpeakerLabelFormatter {
  /// Resolves `personId` to a display name.
  let names: [String: String]

  init(people: [Person]) {
    names = Dictionary(lastWriteWins: people.map { ($0.id, $0.name) })
  }

  init(names: [String: String]) {
    self.names = names
  }

  /// "You", the person's name, or "Speaker N" (1-based).
  func label(isUser: Bool, personId: String?, speakerId: Int) -> String {
    if isUser { return "You" }
    if let personId, let name = names[personId], !name.isEmpty { return name }
    return Self.anonymousLabel(speakerId: speakerId)
  }

  func label(for segment: TranscriptSegment) -> String {
    label(isUser: segment.isUser, personId: segment.personId, speakerId: segment.speakerId)
  }

  /// "Speaker N" for a raw diarization index. 1-based, matching mobile.
  static func anonymousLabel(speakerId: Int) -> String {
    "Speaker \(displayNumber(speakerId: speakerId))"
  }

  /// The number shown in avatars and labels for a raw diarization index.
  static func displayNumber(speakerId: Int) -> Int {
    max(0, speakerId) + 1
  }

  /// Distinct participants in order of first appearance.
  func participants(in segments: [TranscriptSegment]) -> [String] {
    var seen = Set<String>()
    var ordered: [String] = []
    for segment in segments {
      let name = label(for: segment)
      if seen.insert(name).inserted { ordered.append(name) }
    }
    return ordered
  }

  /// The plain-text transcript every copy action produces: "Name: text", blank line between turns.
  func transcript(_ segments: [TranscriptSegment]) -> String {
    segments
      .filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
      .map { "\(label(for: $0)): \($0.text)" }
      .joined(separator: "\n\n")
  }
}
