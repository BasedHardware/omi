import Foundation

/// Attribution travels with the selected display structure, including through the GRDB mirror.
/// This grants no canonical task or memory authority to client-authored content.
struct ConversationLocalSummary: Codable, Equatable {
  let modelId: String
  let runtime: String
  let deviceClass: String
  let generatedAt: String
  let transcriptSha256: String
  let schemaVersion: Int
  /// False on list responses: the server bound the projection, but omitted the transcript.
  var transcriptVerified: Bool
}

enum ConversationProjectionRendering {
  /// Ignore a future envelope before decoding its version-specific body. A future schema may
  /// have an entirely different structure; it must not make the whole conversation unreadable.
  static func decodeWire(from decoder: Decoder) throws -> OmiAPI.Conversation {
    enum Keys: String, CodingKey { case clientProcessing = "client_processing" }
    struct Version: Decodable {
      let schemaVersion: Int
      enum CodingKeys: String, CodingKey { case schemaVersion = "schema_version" }
    }
    let container = try decoder.container(keyedBy: Keys.self)
    guard container.contains(.clientProcessing),
      try !container.decodeNil(forKey: .clientProcessing)
    else { return try OmiAPI.Conversation(from: decoder) }
    if let version = try? container.decode(Version.self, forKey: .clientProcessing),
      version.schemaVersion == 1,
      (try? container.decode(OmiAPI.ClientProcessing.self, forKey: .clientProcessing)) != nil
    {
      return try OmiAPI.Conversation(from: decoder)
    }
    recordRejection()
    var fields = try [String: OmiAnyCodable](from: decoder)
    fields.removeValue(forKey: "client_processing")
    // Generated DTO dates are strings; no domain date-decoding strategy is needed here.
    return try JSONDecoder().decode(OmiAPI.Conversation.self, from: JSONEncoder().encode(fields))
  }

  static func resolve(_ wire: OmiAPI.Conversation, transcriptIncluded: Bool) -> (
    structured: Structured, localSummary: ConversationLocalSummary?
  ) {
    let canonical = Structured(wire.structured)
    guard let projection = wire.clientProcessing else { return (canonical, nil) }
    guard projection.schemaVersion == 1 else {
      recordRejection()
      return (canonical, nil)
    }
    // The backend retains client_processing on cloud reprocessing. processing_state is absent
    // for BOTH enriched and initially projected rows, so it cannot establish precedence.
    // A minimum has empty overview/sections/events and category other. Action items are merged
    // separately because a user may have toggled or added one since local generation.
    guard canonical.overview.isEmpty, canonical.sections.isEmpty, canonical.events.isEmpty,
      canonical.category == "other"
    else { return (canonical, nil) }
    if transcriptIncluded {
      let segments = wire.transcriptSegments ?? []
      let digest = TranscriptHash.sha256(
        segments: segments.map {
          TranscriptHash.Segment(
            speaker: $0.speaker, speakerId: $0.speakerId, isUser: $0.isUser,
            personId: $0.personId, text: $0.text)
        })
      guard digest == projection.transcriptSha256 else {
        recordRejection()
        return (canonical, nil)
      }
    }
    // Match the domain's action identity (exact description). Canonical values win even when
    // completed is false: OR-ing completion would resurrect a task the user reopened.
    var items = canonical.actionItems
    var descriptions = Set(items.map(\.description))
    for item in projection.actionItems ?? [] where descriptions.insert(item.description_).inserted {
      items.append(ActionItem(description: item.description_, completed: item.completed ?? false, deleted: false))
    }
    let structure = projection.structure
    let rendered = Structured(
      title: structure.title, overview: structure.overview ?? "", emoji: structure.emoji ?? "🧠",
      category: structure.category.flatMap { $0 == ._unknown ? nil : $0.rawValue } ?? "other",
      actionItems: items,
      events: (structure.events ?? []).map {
        Event(
          OmiAPI.Event(
            created: false, description_: $0.description_, duration: $0.duration,
            start: $0.start, title: $0.title))
      },
      sections: (structure.sections ?? []).map { SummarySection(heading: $0.heading, bodyMarkdown: $0.bodyMarkdown) }
    )
    let provenance = projection.provenance
    return (
      rendered,
      ConversationLocalSummary(
        modelId: provenance.modelId, runtime: provenance.runtime, deviceClass: provenance.deviceClass,
        generatedAt: provenance.generatedAt, transcriptSha256: projection.transcriptSha256,
        schemaVersion: projection.schemaVersion, transcriptVerified: transcriptIncluded)
    )
  }

  private static func recordRejection() {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "local_llm", from: "client_projection", to: "server_structure", reason: "other", outcome: .degraded)
  }
}
