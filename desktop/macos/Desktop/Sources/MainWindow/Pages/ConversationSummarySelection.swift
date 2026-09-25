import Foundation

/// Pure selection and composition policy for a conversation summary.
///
/// The backend keeps a compatibility `overview` alongside structured headed sections. In some
/// generations the overview is the deterministic Markdown projection of those sections; mounting
/// both values is therefore a duplicate summary. This policy chooses exactly one canonical body and
/// carries its provenance separately from the optional app id (legacy app results can be unattributed).
enum ConversationSummarySelection {
  enum Kind: String, Equatable {
    case app
    case overview
    case sections
    case empty
  }

  /// The one body every summary surface should render, together with its explicit source identity.
  struct Primary: Equatable {
    let content: String
    let kind: Kind
    let appId: String?
    /// Index in `appsResults` for app output. This remains present when `appId` is nil.
    let resultIndex: Int?

    func appDisplayName(resolvedName: String?) -> String? {
      guard kind == .app else { return nil }
      let name = resolvedName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      return name.isEmpty ? "Unknown App" : name
    }
  }

  static func primarySummary(for conversation: ServerConversation) -> Primary {
    if let (resultIndex, result) = conversation.appsResults.enumerated().first(where: {
      !$0.element.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }) {
      return Primary(
        content: result.content.trimmingCharacters(in: .whitespacesAndNewlines),
        kind: .app,
        appId: result.appId,
        resultIndex: resultIndex
      )
    }

    let overview = conversation.overview.trimmingCharacters(in: .whitespacesAndNewlines)
    let renderedSections = renderSections(conversation.structured.sections)
    if !renderedSections.isEmpty, overview == renderedSections {
      return Primary(content: renderedSections, kind: .sections, appId: nil, resultIndex: nil)
    }
    if !overview.isEmpty {
      return Primary(content: overview, kind: .overview, appId: nil, resultIndex: nil)
    }
    if !renderedSections.isEmpty {
      return Primary(content: renderedSections, kind: .sections, appId: nil, resultIndex: nil)
    }
    return Primary(content: "", kind: .empty, appId: nil, resultIndex: nil)
  }

  /// Deterministic compatibility projection used to identify an overview that duplicates sections.
  /// Empty headings with empty bodies do not create visible content; body-only sections remain valid.
  static func renderSections(_ sections: [SummarySection]) -> String {
    sections.compactMap { section in
      let heading = section.heading.trimmingCharacters(in: .whitespacesAndNewlines)
      let body = section.bodyMarkdown.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !body.isEmpty else { return nil }
      if heading.isEmpty { return body }
      return "## \(heading)\n\n\(body)"
    }
    .joined(separator: "\n\n")
  }

  struct Secondary: Identifiable {
    let id: Int
    let result: AppResponse
  }

  /// Array positions distinguish repeated or unattributed app results across decodes.
  static func secondaryResults(for conversation: ServerConversation) -> [Secondary] {
    let primaryIndex = primarySummary(for: conversation).resultIndex
    return conversation.appsResults.enumerated().compactMap { index, result in
      guard index != primaryIndex,
        !result.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      else { return nil }
      return Secondary(id: index, result: result)
    }
  }

  /// References are useful only when their source is in the loaded transcript.
  static func resolvableSourceIDs(_ ids: [String], segments: [TranscriptSegment]) -> [String] {
    let valid = Set(segments.flatMap { [$0.id, $0.backendId].compactMap { $0 } })
    var seen = Set<String>()
    return ids.filter { valid.contains($0) && seen.insert($0).inserted }
  }

  /// Suggested "Try with Apps" rows: memories-capable apps that have not
  /// produced a result for this conversation yet.
  ///
  /// Regression note: the inline closure this replaces compared `$0.appId == $0.id`
  /// inside `contains(where:)` — the inner `$0` shadowed the outer app, every
  /// appsResults entry compared to itself, and the section was always empty.
  static func suggestedApps(_ apps: [OmiApp], results: [AppResponse]) -> [OmiApp] {
    let resultAppIds = Set(results.compactMap(\.appId))
    return apps.filter { app in
      app.capabilities.contains("memories") && !resultAppIds.contains(app.id)
    }
  }
}
