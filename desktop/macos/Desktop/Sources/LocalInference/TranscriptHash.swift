import CryptoKit
import Foundation

/// Client copy of `backend/utils/conversations/transcript_hash.py` encoding v5.
///
/// The digest is a wire contract with the server projection binder. The version
/// names this framing; it is not mixed into the digest bytes.
enum TranscriptHash {
  static let encodingVersion = 5
  static let defaultSpeaker = "SPEAKER_00"
  static let defaultSpeakerId = 0
  static let isUserToken = "Y"
  static let notUserToken = "N"

  struct Segment: Sendable, Equatable {
    var speaker: String?
    var speakerId: Int?
    var isUser: Bool?
    var personId: String?
    var text: String

    init(
      speaker: String? = nil,
      speakerId: Int? = nil,
      isUser: Bool? = nil,
      personId: String? = nil,
      text: String
    ) {
      self.speaker = speaker
      self.speakerId = speakerId
      self.isUser = isUser
      self.personId = personId
      self.text = text
    }
  }

  struct CanonicalSegment: Sendable, Equatable {
    var speaker: String
    var speakerId: Int
    var isUser: Bool
    var personId: String?
    var text: String
  }

  static func canonicalize(_ segment: Segment) -> CanonicalSegment {
    let speaker = stripOrDefault(segment.speaker, defaultSpeaker)
    let person = stripOrDefault(segment.personId, "")
    return CanonicalSegment(
      speaker: speaker,
      speakerId: segment.speakerId ?? derivedSpeakerId(speaker),
      isUser: segment.isUser == true,
      personId: person.isEmpty ? nil : person,
      text: stripOrDefault(segment.text, "")
    )
  }

  static func sha256(segments: [Segment]) -> String {
    sha256(canonical: segments.map(canonicalize))
  }

  static func sha256(canonical parts: [CanonicalSegment]) -> String {
    let digest = SHA256.hash(data: Data(canonicalBytes(parts)))
    return digest.map { String(format: "%02x", $0) }.joined()
  }

  /// Python `split('_', 1)[1]` — only the first underscore is the cut.
  static func derivedSpeakerId(_ speaker: String) -> Int {
    guard let idx = speaker.firstIndex(of: "_") else { return defaultSpeakerId }
    let rest = speaker[speaker.index(after: idx)...]
    return Int(rest) ?? defaultSpeakerId
  }

  static func canonicalBytes(_ parts: [CanonicalSegment]) -> [UInt8] {
    var out: [UInt8] = []
    out.reserveCapacity(parts.count * 24)
    for part in parts {
      out.append(contentsOf: frame(part.speaker))
      out.append(contentsOf: frame(String(part.speakerId)))
      out.append(contentsOf: frame(part.isUser ? isUserToken : notUserToken))
      out.append(contentsOf: frame(part.personId ?? ""))
      out.append(contentsOf: frame(part.text))
    }
    return out
  }

  private static func stripOrDefault(_ raw: String?, _ defaultValue: String) -> String {
    guard let raw else { return defaultValue }
    let stripped = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    return stripped.isEmpty ? defaultValue : stripped
  }

  private static func frame(_ value: String) -> [UInt8] {
    let encoded = Array(value.utf8)
    return Array("\(encoded.count)\n".utf8) + encoded
  }
}

extension TranscriptionSegmentRecord {
  var hashSegment: TranscriptHash.Segment {
    TranscriptHash.Segment(
      speaker: speakerLabel,
      speakerId: speaker,
      isUser: isUser,
      personId: personId,
      text: text
    )
  }
}
