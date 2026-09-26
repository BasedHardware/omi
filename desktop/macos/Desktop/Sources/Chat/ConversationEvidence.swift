import CryptoKit
import Foundation
import VoiceTurnDomain

/// The metadata contract shared by every journal surface. The runtime owns the
/// schema and strips `bodyText` before backend delivery; Swift keeps the bounded
/// body locally so an authorized evidence read can recover the original text.
enum ConversationEvidenceKind: String, Codable, Equatable, Sendable {
  case screen
  case document
  case attachment
  case toolResult = "tool_result"
}

enum ConversationEvidenceAvailability: String, Codable, Equatable, Sendable {
  case pending
  case available
  case partial
  case unavailable
}

enum ConversationEvidenceExtractionCompleteness: String, Codable, Equatable, Sendable {
  case complete
  case partial
  case none
}

struct ConversationEvidence: Codable, Equatable, Identifiable, Sendable {
  static let schema = "omi.evidence@1"
  static let maxBodyBytes = 64 * 1024
  static let maxMetadataBytes = 512 * 1024
  static let maxItems = 8
  static let maxIDCharacters = 160
  static let maxTitleCharacters = 240
  static let maxDigestCharacters = 160
  static let maxProvenanceEntries = 12
  static let maxProvenanceKeyCharacters = 64
  static let maxProvenanceValueCharacters = 256

  let id: String
  let kind: ConversationEvidenceKind
  let title: String
  let capturedAtMs: Int
  let availability: ConversationEvidenceAvailability
  let extractionCompleteness: ConversationEvidenceExtractionCompleteness
  /// Full extracted text is local journal metadata, bounded to the runtime's
  /// 64 KiB contract. Pixels and filesystem paths are deliberately absent.
  let bodyText: String?
  let digest: String?
  /// Opaque artifact identity only. Native PTT OCR has no artifact, so this is
  /// nil for screen evidence and can never accidentally become a file path.
  let artifactId: String?
  let provenance: [String: String]?

  init(
    id: String,
    kind: ConversationEvidenceKind,
    title: String,
    capturedAtMs: Int,
    availability: ConversationEvidenceAvailability,
    extractionCompleteness: ConversationEvidenceExtractionCompleteness,
    bodyText: String? = nil,
    digest: String? = nil,
    artifactId: String? = nil,
    provenance: [String: String]? = nil
  ) {
    self.id = Self.boundedRequired(id, maxCharacters: Self.maxIDCharacters)
    self.kind = kind
    self.title = Self.boundedRequired(title, maxCharacters: Self.maxTitleCharacters)
    self.capturedAtMs = max(0, capturedAtMs)
    self.availability = availability
    let boundedResult = bodyText.flatMap(Self.boundedBody)
    let boundedBody = boundedResult?.text
    self.extractionCompleteness =
      boundedResult?.wasTruncated == true && extractionCompleteness == .complete
      ? .partial
      : extractionCompleteness
    if availability == .unavailable || self.extractionCompleteness == .none {
      self.bodyText = nil
    } else {
      self.bodyText = boundedBody
    }
    // A supplied digest is only authoritative for bodyless evidence. When a
    // body is retained, the digest must describe those exact bytes or the
    // runtime rejects the item.
    self.digest =
      self.bodyText.map(Self.digest)
      ?? digest.map { Self.boundedRequired($0, maxCharacters: Self.maxDigestCharacters) }
    self.artifactId = artifactId.map { Self.boundedRequired($0, maxCharacters: Self.maxIDCharacters) }
    self.provenance = provenance.flatMap(Self.boundedProvenance)
  }

  var isReadable: Bool {
    bodyText != nil || artifactId != nil
  }

  static func nativeScreenOCR(
    evidenceID: String,
    capturedAt: Date,
    text: String?,
    turnID: VoiceTurnID,
    frontmostApp: String? = nil,
    frontmostBundleID: String? = nil,
    textWasTruncated: Bool = false
  ) -> ConversationEvidence {
    let body = text?.trimmingCharacters(in: .whitespacesAndNewlines)
    let hasText = !(body?.isEmpty ?? true)
    var provenance: [String: String] = [
      "source": "native_ptt_ocr",
      "turn_id": turnID.rawValue.uuidString.lowercased(),
    ]
    if let frontmostApp = frontmostApp?.trimmingCharacters(in: .whitespacesAndNewlines), !frontmostApp.isEmpty {
      provenance["frontmost_app"] = frontmostApp
    }
    if let frontmostBundleID = frontmostBundleID?.trimmingCharacters(in: .whitespacesAndNewlines),
      !frontmostBundleID.isEmpty
    {
      provenance["frontmost_bundle_id"] = frontmostBundleID
    }
    return ConversationEvidence(
      id: evidenceID,
      kind: .screen,
      title: "PTT screen OCR",
      capturedAtMs: Int(capturedAt.timeIntervalSince1970 * 1_000),
      availability: hasText ? .available : .unavailable,
      extractionCompleteness: hasText
        ? (textWasTruncated ? .partial : .complete)
        : .none,
      bodyText: hasText ? body : nil,
      provenance: provenance
    )
  }

  /// Stable placeholder admitted with the user row before the asynchronous
  /// native OCR producer resolves. It carries only source identity and the
  /// frozen capture instant; the runtime can render it as unavailable after
  /// restart until the producer supplies a terminal update.
  static func pendingNativeScreenOCR(
    evidenceID: String,
    capturedAt: Date,
    turnID: VoiceTurnID,
    frontmostApp: String? = nil,
    frontmostBundleID: String? = nil
  ) -> ConversationEvidence {
    var provenance: [String: String] = [
      "source": "native_ptt_ocr",
      "turn_id": turnID.rawValue.uuidString.lowercased(),
    ]
    if let frontmostApp = frontmostApp?.trimmingCharacters(in: .whitespacesAndNewlines), !frontmostApp.isEmpty {
      provenance["frontmost_app"] = frontmostApp
    }
    if let frontmostBundleID = frontmostBundleID?.trimmingCharacters(in: .whitespacesAndNewlines),
      !frontmostBundleID.isEmpty
    {
      provenance["frontmost_bundle_id"] = frontmostBundleID
    }
    return ConversationEvidence(
      id: evidenceID,
      kind: .screen,
      title: "PTT screen OCR",
      capturedAtMs: Int(capturedAt.timeIntervalSince1970 * 1_000),
      availability: .pending,
      extractionCompleteness: .none,
      provenance: provenance
    )
  }

  private enum CodingKeys: String, CodingKey {
    case id
    case kind
    case title
    case capturedAtMs
    case availability
    case extractionCompleteness
    case bodyText
    case digest
    case artifactId
    case provenance
  }

  /// Keep identity and the digest of the previously retained body when the
  /// aggregate envelope can no longer carry that body under the metadata budget.
  fileprivate func droppingRetainedBodyForMetadataBudget() -> ConversationEvidence {
    ConversationEvidence(
      id: id,
      kind: kind,
      title: title,
      capturedAtMs: capturedAtMs,
      availability: (availability == .pending || availability == .unavailable) ? availability : .partial,
      extractionCompleteness: (availability == .pending || availability == .unavailable)
        ? extractionCompleteness
        : .partial,
      bodyText: nil,
      digest: digest,
      artifactId: artifactId,
      provenance: provenance
    )
  }

  private static func boundedRequired(_ value: String, maxCharacters: Int) -> String {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return "unknown" }
    return String(trimmed.prefix(maxCharacters))
  }

  static func boundedBody(_ value: String) -> (text: String, wasTruncated: Bool)? {
    guard !value.isEmpty else { return nil }
    let data = Data(value.utf8)
    guard data.count > maxBodyBytes else { return (value, false) }
    let limit = maxBodyBytes
    var end = limit
    while end > 0, (data[end - 1] & 0xC0) == 0x80 {
      end -= 1
    }
    if end > 0 {
      let lead = data[end - 1]
      let sequenceLength: Int
      if lead & 0x80 == 0 {
        sequenceLength = 1
      } else if lead & 0xE0 == 0xC0 {
        sequenceLength = 2
      } else if lead & 0xF0 == 0xE0 {
        sequenceLength = 3
      } else {
        sequenceLength = 4
      }
      if limit - (end - 1) < sequenceLength {
        end -= 1
      } else {
        end = limit
      }
    }
    let result = String(decoding: data.prefix(end), as: UTF8.self)
    return result.isEmpty ? nil : (result, true)
  }

  private static func boundedProvenance(_ input: [String: String]) -> [String: String]? {
    var result: [String: String] = [:]
    for (key, value) in input.prefix(maxProvenanceEntries) {
      let boundedKey = boundedRequired(key, maxCharacters: maxProvenanceKeyCharacters)
      let boundedValue = boundedRequired(value, maxCharacters: maxProvenanceValueCharacters)
      result[boundedKey] = boundedValue
    }
    return result.isEmpty ? nil : result
  }

  private static func digest(_ value: String) -> String {
    let hash = SHA256.hash(data: Data(value.utf8))
    return "sha256:" + hash.map { String(format: "%02x", $0) }.joined()
  }
}

struct ConversationEvidenceEnvelope: Codable, Equatable, Sendable {
  let schema: String
  let items: [ConversationEvidence]

  init(items: [ConversationEvidence]) {
    var seen = Set<String>()
    let unique = Array(items.filter { seen.insert($0.id).inserted }.prefix(ConversationEvidence.maxItems))
    schema = ConversationEvidence.schema
    self.items = Self.fittingMetadataBudget(unique)
  }

  /// Probe constructor used only while measuring encoded size. Applying the
  /// budget here would recurse through the encoder.
  private init(uncheckedSchema schema: String, items: [ConversationEvidence]) {
    self.schema = schema
    self.items = items
  }

  /// Prefer keeping earlier full bodies. Overflowing later items become honest
  /// partial records with the digest of the bytes that had been retained,
  /// rather than dropping the envelope or pretending the source never existed.
  private static func fittingMetadataBudget(_ items: [ConversationEvidence]) -> [ConversationEvidence] {
    var result = items
    while encodedJSONByteCount(items: result) > ConversationEvidence.maxMetadataBytes {
      guard let index = result.lastIndex(where: { $0.bodyText != nil }) else { break }
      result[index] = result[index].droppingRetainedBodyForMetadataBudget()
    }
    return result
  }

  private static func encodedJSONByteCount(items: [ConversationEvidence]) -> Int {
    let probe = ConversationEvidenceEnvelope(
      uncheckedSchema: ConversationEvidence.schema, items: items)
    guard let object = ConversationEvidenceMetadataCodec.encodeEnvelope(probe),
      JSONSerialization.isValidJSONObject(object),
      let data = try? JSONSerialization.data(withJSONObject: object)
    else {
      return ConversationEvidence.maxMetadataBytes + 1
    }
    return data.count
  }
}

/// JSON metadata codec. It preserves unrelated journal metadata and uses the
/// exact `evidence` namespace consumed by the Node runtime.
enum ConversationEvidenceMetadataCodec {
  static let metadataKey = "evidence"

  static func envelope(from metadataJSON: String?) -> ConversationEvidenceEnvelope? {
    guard let metadataJSON,
      let data = metadataJSON.data(using: .utf8),
      let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let raw = root[metadataKey],
      let envelopeData = try? JSONSerialization.data(withJSONObject: raw),
      let envelope = try? JSONDecoder().decode(ConversationEvidenceEnvelope.self, from: envelopeData),
      envelope.schema == ConversationEvidence.schema
    else { return nil }
    return envelope
  }

  static func encodeEnvelope(_ envelope: ConversationEvidenceEnvelope) -> Any? {
    guard let data = try? JSONEncoder().encode(envelope),
      let object = try? JSONSerialization.jsonObject(with: data)
    else { return nil }
    return object
  }

  /// Encodes one evidence object for the journal's atomic append operation.
  /// The runtime merges this object into the owned row in the same update
  /// transaction; callers must not read and replace the row metadata first.
  static func encodeEvidence(_ evidence: ConversationEvidence) -> Any? {
    guard let data = try? JSONEncoder().encode(evidence),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return nil }
    return object
  }

  static func metadataJSON(
    existing: String?,
    adding evidence: ConversationEvidence
  ) -> String {
    var root: [String: Any] = [:]
    if let existing,
      let data = existing.data(using: .utf8),
      let decoded = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    {
      root = decoded
    }
    var items = envelope(from: existing)?.items ?? []
    if let index = items.firstIndex(where: { $0.id == evidence.id }) {
      if items[index] == evidence { return existing ?? "{}" }
      // A pending local obligation is intentionally not encoded. If a caller
      // did encode an unavailable/partial placeholder, preserve the runtime's
      // stable-ID semantics and do not silently rewrite it.
      return existing ?? "{}"
    }
    items.append(evidence)
    root[metadataKey] = encodeEnvelope(ConversationEvidenceEnvelope(items: items)) ?? [:]
    guard JSONSerialization.isValidJSONObject(root),
      let data = try? JSONSerialization.data(withJSONObject: root),
      let encoded = String(data: data, encoding: .utf8)
    else { return existing ?? "{}" }
    return encoded
  }
}
