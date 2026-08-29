import Foundation

/// A source selected for the next main-chat turn. Unlike a file attachment, a
/// reference has no upload lifecycle: it is a small, removable composer chip
/// that the next query can use as typed context.
struct ChatComposerReference: Identifiable, Equatable, Sendable {
  enum Kind: String, Equatable, Sendable {
    case conversation

    var systemImage: String {
      switch self {
      case .conversation: return "text.bubble"
      }
    }

    var label: String {
      switch self {
      case .conversation: return "Conversation"
      }
    }
  }

  let id: String
  let kind: Kind
  let sourceID: String
  let title: String
  let preview: String
  let momentTimestampMs: Int?

  init(
    id: String? = nil,
    kind: Kind,
    sourceID: String,
    title: String,
    preview: String = "",
    momentTimestampMs: Int? = nil
  ) {
    let normalizedSourceID = sourceID.trimmingCharacters(in: .whitespacesAndNewlines)
    self.id = id ?? "\(kind.rawValue):\(normalizedSourceID)"
    self.kind = kind
    self.sourceID = normalizedSourceID
    self.title = Self.bounded(title, limit: 160)
    self.preview = Self.bounded(preview, limit: 600, flattenLines: false)
    self.momentTimestampMs = momentTimestampMs
  }

  var displayTitle: String {
    let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? kind.label : trimmed
  }

  var displaySubtitle: String {
    if let momentTimestampMs {
      let seconds = max(0, momentTimestampMs) / 1_000
      return "\(kind.label) · \(Self.format(seconds: seconds))"
    }
    return kind.label
  }

  /// The source shape used by the existing prompt citation ledger. The
  /// source ID stays out of the visible user turn while remaining available to
  /// the model as selected context.
  var promptCitationSource: ChatPromptCitationSource {
    ChatPromptCitationSource(
      kind: .conversation,
      sourceID: sourceID,
      title: displayTitle,
      preview: preview,
      createdAt: nil)
  }

  /// Navigation shape for the persisted pill. Its ordinal is presentation-only
  /// here; the prompt ledger still owns the model-visible citation ordinals.
  var navigationReference: ChatCitationReference {
    ChatCitationReference(
      ordinal: ChatPromptCitationLedger.firstOrdinal,
      kind: .conversation,
      sourceID: sourceID,
      title: displayTitle,
      preview: preview,
      momentTimestampMs: momentTimestampMs
    )
  }

  private static func bounded(_ value: String, limit: Int, flattenLines: Bool = true) -> String {
    let normalized =
      flattenLines
      ? value.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
      : value
    return String(normalized.prefix(limit))
  }

  private static func format(seconds: Int) -> String {
    let minutes = seconds / 60
    let remainder = seconds % 60
    return String(format: "%02d:%02d", minutes, remainder)
  }
}

/// Pure staging semantics for the composer reference row. Keeping this
/// reducer independent from `ChatProvider` makes the no-submit/preserve-draft
/// contract directly testable without constructing the network-backed provider.
struct ChatComposerReferenceState: Equatable, Sendable {
  private(set) var references: [ChatComposerReference] = []

  mutating func stage(_ reference: ChatComposerReference) {
    guard !reference.sourceID.isEmpty else { return }
    references.removeAll { $0.kind == reference.kind && $0.sourceID == reference.sourceID }
    references.append(reference)
  }

  mutating func remove(id: String) {
    references.removeAll { $0.id == id }
  }

  mutating func clear() {
    references.removeAll()
  }
}
