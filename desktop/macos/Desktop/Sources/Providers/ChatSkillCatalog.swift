import Foundation

enum ChatSkillCatalog {
  typealias Skill = (name: String, description: String, path: String)

  private static let inlineCatalogLimit = 12
  private static let inlineDescriptionLimit = 160

  /// Project skills take precedence over global skills of the same name, matching the runtime
  /// loader's search order. The projection is intentionally metadata-only: CLAUDE.md stays a
  /// Settings reference and is never mixed into chat instructions.
  static func enabledSkills(
    globalSkills: [Skill],
    projectSkills: [Skill],
    disabledSkills: Set<String>
  ) -> [(name: String, description: String)] {
    var deduplicated: [String: (name: String, description: String)] = [:]
    for skill in projectSkills + globalSkills {
      let name = skill.name.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !name.isEmpty, !disabledSkills.contains(name), deduplicated[name] == nil else { continue }
      let description = skill.description
        .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
      deduplicated[name] = (name, String(description.prefix(inlineDescriptionLimit)))
    }
    return deduplicated.values.sorted {
      $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
    }
  }

  static func contextProjection(
    globalSkills: [Skill],
    projectSkills: [Skill],
    disabledSkills: Set<String>
  ) -> [String: Any] {
    let catalog = enabledSkills(
      globalSkills: globalSkills,
      projectSkills: projectSkills,
      disabledSkills: disabledSkills
    )
    let skills = catalog.prefix(inlineCatalogLimit).map { ["name": $0.name, "description": $0.description] }
    let isTruncated = catalog.count > skills.count
    return [
      "skills": skills,
      "totalCount": catalog.count,
      "isTruncated": isTruncated,
      "searchAvailable": isTruncated,
      "guidance": isTruncated
        ? "Skills are optional. Use a listed skill only when it is relevant to the user's request. Search with search_skills before loading a skill outside this compact catalog."
        : "Skills are optional. Load a listed skill only when it is relevant to the user's request.",
    ]
  }
}
