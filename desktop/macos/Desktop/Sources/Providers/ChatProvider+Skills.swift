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

  // MARK: - Lane gating

  /// Whether the ACP lane's user-skills plugin is active. The runtime itself
  /// gates the plugin on `.claude-plugin/plugin.json` (user-extensions.ts), so
  /// the desktop asks the exact same question.
  nonisolated static func acpSkillsPluginActive() -> Bool {
    FileManager.default.fileExists(atPath: LocalSkillsStore.pluginManifestURL.path)
  }

  /// The skill catalog has one source of truth per lane. On the pi-mono lane it
  /// is the compact catalog plus the load_skill/search_skills tools. On the ACP
  /// lane the user-skills plugin already ships the skills natively, so the
  /// compact catalog would hand the model the same index twice.
  nonisolated static func shouldInjectSkillCatalog(adapterId: String) -> Bool {
    adapterId != AgentAdapterId.acp.rawValue || !acpSkillsPluginActive()
  }

  // MARK: - Disabled skills

  /// Explicitly disabled skill names straight from UserDefaults, for callers
  /// without a provider instance (task chat, runtime spawn env). The parse —
  /// and the set's rename/delete upkeep — live on `LocalSkillsStore`, which
  /// owns the slug identity.
  nonisolated static func disabledSkillNamesFromDefaults() -> Set<String> {
    LocalSkillsStore.disabledSkillNames()
  }

  /// Canonical JSON array exported to the runtime as `OMI_DISABLED_SKILLS`, so
  /// load_skill/search_skills enforce the toggle the same way this catalog
  /// does. Nil when nothing is disabled, keeping the env unset.
  nonisolated static func disabledSkillsRuntimeEnvValue() -> String? {
    let names = disabledSkillNamesFromDefaults().sorted()
    guard !names.isEmpty,
      let data = try? JSONEncoder().encode(names),
      let json = String(data: data, encoding: .utf8)
    else { return nil }
    return json
  }

  // MARK: - Disk-backed projection

  /// The compact skill catalog built straight from disk, for runtimes that have
  /// no ChatProvider instance (task-chat workstreams). Same builder, same
  /// disabled filtering as the per-turn injection.
  nonisolated static func skillCatalogProjectionFromDisk(workspace: String) -> [String: Any] {
    let config = loadClaudeConfigFromDisk(workspace: workspace)
    return ChatSkillCatalog.contextProjection(
      globalSkills: config.skills,
      projectSkills: config.projectSkills,
      disabledSkills: disabledSkillNamesFromDefaults()
    )
  }
}
