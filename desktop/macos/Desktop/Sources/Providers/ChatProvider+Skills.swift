import Foundation

extension ChatProvider {
  func skillContextProjection() -> [String: Any] {
    ChatSkillCatalog.contextProjection(
      globalSkills: discoveredSkills,
      projectSkills: projectDiscoveredSkills,
      disabledSkills: getDisabledSkillNames()
    )
  }

  /// Get the set of enabled skill names (all skills minus explicitly disabled ones).
  func getEnabledSkillNames() -> Set<String> {
    Set(
      ChatSkillCatalog.enabledSkills(
        globalSkills: discoveredSkills,
        projectSkills: projectDiscoveredSkills,
        disabledSkills: getDisabledSkillNames()
      ).map(\.name)
    )
  }
}
