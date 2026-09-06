import Foundation

/// Wire contract for S4 `ClientProcessing`. Schema version is `Literal[1]` on
/// the Pydantic model (`CLIENT_PROCESSING_SCHEMA_VERSION`); a float or bool is
/// rejected server-side. Use the generated `OmiAPI` types — do not hand-wire a
/// parallel DTO (plan correction 2026-09-06: S4 already regenerated them).
enum ClientProcessingContract {
  static let schemaVersion = 1
  static let localRuntime = "local"
  static let deterministicRuntime = "deterministic"
  static let deterministicModelID = "deterministic-minimum"
  static let defaultEmoji = "🧠"
  static let defaultDeviceClass = "macos"

  static let titleMax = 120
  static let overviewMax = 4000
  static let emojiMax = 8
  static let sectionHeadingMax = 120
  static let sectionBodyMax = 4000
  static let actionDescriptionMax = 500
  static let eventTitleMax = 200
  static let eventDescriptionMax = 1000
  static let maxSections = 12
  static let maxEvents = 12
  static let maxActionItems = 25

  static func encode(_ projection: OmiAPI.ClientProcessing) throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    return try encoder.encode(projection)
  }

  static func decode(_ data: Data) throws -> OmiAPI.ClientProcessing {
    try JSONDecoder().decode(OmiAPI.ClientProcessing.self, from: data)
  }

  static func iso8601(_ date: Date) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    return formatter.string(from: date)
  }

  static func assemble(
    draft: LocalSummaryDraft,
    transcriptSha256: String,
    provenance: OmiAPI.ProjectionProvenance,
    fallbackTitle: String
  ) -> OmiAPI.ClientProcessing {
    let title = clip(draft.title, max: titleMax, empty: fallbackTitle)
    let overview = clip(draft.overview, max: overviewMax, empty: "")
    let emoji = clip(draft.emoji ?? defaultEmoji, max: emojiMax, empty: defaultEmoji)
    let category = OmiAPI.CategoryEnum(rawValue: draft.category ?? "other") ?? .other
    let sections = Array(draft.sections.prefix(maxSections)).compactMap(projectedSection)
    let events = Array(draft.events.prefix(maxEvents)).compactMap(projectedEvent)
    let actions = Array(draft.actionItems.prefix(maxActionItems)).compactMap(projectedAction)
    return OmiAPI.ClientProcessing(
      actionItems: actions,
      provenance: provenance,
      schemaVersion: schemaVersion,
      structure: OmiAPI.ProjectedStructure(
        category: category == ._unknown ? .other : category,
        emoji: emoji,
        events: events,
        overview: overview,
        sections: sections,
        title: title
      ),
      transcriptSha256: transcriptSha256
    )
  }

  static func assembleMinimum(
    _ minimum: DeterministicConversationMinimum,
    transcriptSha256: String,
    generatedAt: Date,
    deviceClass: String
  ) -> OmiAPI.ClientProcessing {
    OmiAPI.ClientProcessing(
      actionItems: [],
      provenance: OmiAPI.ProjectionProvenance(
        deviceClass: deviceClass,
        generatedAt: iso8601(generatedAt),
        modelId: deterministicModelID,
        runtime: deterministicRuntime
      ),
      schemaVersion: schemaVersion,
      structure: OmiAPI.ProjectedStructure(
        category: .other,
        emoji: defaultEmoji,
        events: [],
        overview: minimum.overview,
        sections: [],
        title: clip(minimum.title, max: titleMax, empty: "Recording")
      ),
      transcriptSha256: transcriptSha256
    )
  }

  static func stored(_ projection: OmiAPI.ClientProcessing) throws -> StoredClientProjection {
    let json = try encode(projection)
    return StoredClientProjection(transcriptSha256: projection.transcriptSha256, json: json)
  }

  private static func projectedSection(_ draft: LocalSectionDraft) -> OmiAPI.ProjectedSection? {
    let heading = clip(draft.heading, max: sectionHeadingMax, empty: "")
    let body = clip(draft.bodyMarkdown, max: sectionBodyMax, empty: "")
    guard !heading.isEmpty, !body.isEmpty else { return nil }
    return OmiAPI.ProjectedSection(bodyMarkdown: body, heading: heading)
  }

  private static func projectedEvent(_ draft: LocalEventDraft) -> OmiAPI.ProjectedEvent? {
    let title = clip(draft.title, max: eventTitleMax, empty: "")
    guard !title.isEmpty, isAwareISO8601(draft.start) else { return nil }
    let duration = min(max(draft.duration, 1), 1440)
    return OmiAPI.ProjectedEvent(
      description_: clip(draft.description, max: eventDescriptionMax, empty: ""),
      duration: duration,
      start: draft.start,
      title: title
    )
  }

  private static func projectedAction(_ draft: LocalActionItemDraft) -> OmiAPI.ProjectedActionItem? {
    let description = clip(draft.description, max: actionDescriptionMax, empty: "")
    guard !description.isEmpty else { return nil }
    return OmiAPI.ProjectedActionItem(completed: draft.completed, description_: description)
  }

  private static func isAwareISO8601(_ raw: String) -> Bool {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    if formatter.date(from: raw) != nil { return true }
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.date(from: raw) != nil
  }

  /// Bound the RAW string we are about to persist. Server rejects over-cap
  /// values rather than trimming them into range.
  static func clip(_ raw: String, max: Int, empty: String) -> String {
    let stripped = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    if stripped.isEmpty { return empty }
    if stripped.count <= max { return stripped }
    let end = stripped.index(stripped.startIndex, offsetBy: max)
    return String(stripped[..<end])
  }
}
