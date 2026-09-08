import Foundation

/// Manages bidirectional sync of assistant settings between local UserDefaults and the backend.
/// Server is source of truth — server values override local when present.
@MainActor
class SettingsSyncManager {
  static let shared = SettingsSyncManager()
  private init() {}

  /// Pull settings from server and apply non-nil values to local singletons.
  func syncFromServer() async {
    guard AuthService.shared.isSignedIn else { return }
    do {
      let remote = try await APIClient.shared.getAssistantSettings()
      applyRemoteSettings(remote)
      log("SettingsSyncManager: synced from server")
    } catch {
      logError("SettingsSyncManager: failed to sync from server", error: error)
    }
  }

  /// Push all current local settings to the server.
  func syncToServer() async {
    let settings = buildFromLocal()
    do {
      let _ = try await APIClient.shared.updateAssistantSettings(settings)
      log("SettingsSyncManager: synced to server")
    } catch {
      logError("SettingsSyncManager: failed to sync to server", error: error)
    }
  }

  /// Fire-and-forget partial update to server.
  func pushPartialUpdate(_ settings: AssistantSettingsResponse) {
    Task {
      do {
        let _ = try await APIClient.shared.updateAssistantSettings(settings)
      } catch {
        logError("SettingsSyncManager: failed to push partial update", error: error)
      }
    }
  }

  /// Builds the narrow request used by capture-default migrations. A migration of one
  /// setting must not resend unrelated prompts or other user-authored settings.
  static func screenAnalysisEnabledUpdate(_ enabled: Bool) -> AssistantSettingsResponse {
    AssistantSettingsResponse(
      shared: SharedAssistantSettingsResponse(screenAnalysisEnabled: enabled))
  }

  // MARK: - Apply Remote → Local

  /// Applies a server-authoritative snapshot, then notifies runtime owners to
  /// reconcile services whose persisted intent may have changed after launch.
  func applyRemoteSettings(_ remote: AssistantSettingsResponse) {
    // Shared settings
    if let shared = remote.shared {
      if let v = shared.cooldownInterval { AssistantSettings.shared.cooldownInterval = v }
      if let v = shared.glowOverlayEnabled { AssistantSettings.shared.glowOverlayEnabled = v }
      if let v = shared.analysisDelay { AssistantSettings.shared.analysisDelay = v }
      // Lazy-dev bundles keep their per-bundle capture preference instead of
      // importing another bundle's remote value. Capture defaults to enabled;
      // the runtime checks TCC without prompting when permission is absent.
      if let v = shared.screenAnalysisEnabled, !shouldKeepLocalScreenAnalysisDefault {
        AssistantSettings.shared.screenAnalysisEnabled = v
      }
    }

    // Task settings
    if let task = remote.task {
      if let v = task.enabled { TaskAssistantSettings.shared.isEnabled = v }
      if let v = task.analysisPrompt {
        applyRemotePrompt(
          v,
          overLocalPrompt: TaskAssistantSettings.shared.analysisPrompt,
          assistantName: "task",
          maximumLength: TaskAssistantSettings.maximumSyncedAnalysisPromptLength,
          shippedDefault: TaskAssistantSettings.defaultAnalysisPrompt
        ) { TaskAssistantSettings.shared.analysisPrompt = $0 }
      }
      if let v = task.extractionInterval { TaskAssistantSettings.shared.extractionInterval = v }
      if let v = task.minConfidence { TaskAssistantSettings.shared.minConfidence = v }
      if let v = task.notificationsEnabled { TaskAssistantSettings.shared.notificationsEnabled = v }
      if let v = task.allowedApps { TaskAssistantSettings.shared.allowedApps = Set(v) }
      if let v = task.browserKeywords { TaskAssistantSettings.shared.browserKeywords = v }
    }

    // Insight settings
    if let insight = remote.insight {
      if let v = insight.enabled { InsightAssistantSettings.shared.isEnabled = v }
      if let v = insight.analysisPrompt {
        applyRemotePrompt(
          v,
          overLocalPrompt: InsightAssistantSettings.shared.analysisPrompt,
          assistantName: "insight",
          maximumLength: 10_000,
          shippedDefault: InsightAssistantSettings.defaultAnalysisPrompt
        ) { InsightAssistantSettings.shared.analysisPrompt = $0 }
      }
      if let v = insight.extractionInterval { InsightAssistantSettings.shared.extractionInterval = v }
      if let v = insight.minConfidence { InsightAssistantSettings.shared.minConfidence = v }
      if let v = insight.notificationsEnabled { InsightAssistantSettings.shared.notificationsEnabled = v }
      if let v = insight.excludedApps { InsightAssistantSettings.shared.excludedApps = Set(v) }
    }

    // Memory settings
    if let memory = remote.memory {
      if let v = memory.enabled { MemoryAssistantSettings.shared.isEnabled = v }
      if let v = memory.analysisPrompt {
        applyRemotePrompt(
          v,
          overLocalPrompt: MemoryAssistantSettings.shared.analysisPrompt,
          assistantName: "memory",
          maximumLength: 10_000,
          shippedDefault: MemoryAssistantSettings.defaultAnalysisPrompt
        ) { MemoryAssistantSettings.shared.analysisPrompt = $0 }
      }
      if let v = memory.extractionInterval { MemoryAssistantSettings.shared.extractionInterval = v }
      if let v = memory.minConfidence { MemoryAssistantSettings.shared.minConfidence = v }
      if let v = memory.notificationsEnabled { MemoryAssistantSettings.shared.notificationsEnabled = v }
      if let v = memory.excludedApps { MemoryAssistantSettings.shared.excludedApps = Set(v) }
    }

    // Push-to-talk voice replies are no longer configurable. Ignore the legacy
    // server field so old synced `false` values cannot suppress spoken answers.

    // Sparkle channel is identity-bound. Ignore a server-assigned update_channel
    // so a leftover user-doc "beta" cannot opt Stable.app into Mechanism 2.

    NotificationCenter.default.post(name: .assistantSettingsDidSyncFromServer, object: nil)
  }

  // MARK: - Build Local → Response

  private var shouldKeepLocalScreenAnalysisDefault: Bool {
    AppBuild.usesLazyDevPermissions
  }

  private func buildFromLocal() -> AssistantSettingsResponse {
    let shared = SharedAssistantSettingsResponse(
      cooldownInterval: AssistantSettings.shared.cooldownInterval,
      glowOverlayEnabled: AssistantSettings.shared.glowOverlayEnabled,
      analysisDelay: AssistantSettings.shared.analysisDelay,
      screenAnalysisEnabled: shouldKeepLocalScreenAnalysisDefault ? nil : AssistantSettings.shared.screenAnalysisEnabled
    )

    let task = TaskSettingsResponse(
      enabled: TaskAssistantSettings.shared.isEnabled,
      analysisPrompt: Self.promptForSync(
        TaskAssistantSettings.shared.analysisPrompt,
        assistantName: "task",
        maximumLength: TaskAssistantSettings.maximumSyncedAnalysisPromptLength,
        shippedDefault: TaskAssistantSettings.defaultAnalysisPrompt),
      extractionInterval: TaskAssistantSettings.shared.extractionInterval,
      minConfidence: TaskAssistantSettings.shared.minConfidence,
      notificationsEnabled: TaskAssistantSettings.shared.notificationsEnabled,
      allowedApps: Array(TaskAssistantSettings.shared.allowedApps),
      browserKeywords: TaskAssistantSettings.shared.browserKeywords
    )

    let insight = InsightSettingsResponse(
      enabled: InsightAssistantSettings.shared.isEnabled,
      analysisPrompt: Self.promptForSync(
        InsightAssistantSettings.shared.analysisPrompt,
        assistantName: "insight",
        maximumLength: 10_000,
        shippedDefault: InsightAssistantSettings.defaultAnalysisPrompt),
      extractionInterval: InsightAssistantSettings.shared.extractionInterval,
      minConfidence: InsightAssistantSettings.shared.minConfidence,
      notificationsEnabled: InsightAssistantSettings.shared.notificationsEnabled,
      excludedApps: Array(InsightAssistantSettings.shared.excludedApps)
    )

    let memory = MemorySettingsResponse(
      enabled: MemoryAssistantSettings.shared.isEnabled,
      analysisPrompt: Self.promptForSync(
        MemoryAssistantSettings.shared.analysisPrompt,
        assistantName: "memory",
        maximumLength: 10_000,
        shippedDefault: MemoryAssistantSettings.defaultAnalysisPrompt),
      extractionInterval: MemoryAssistantSettings.shared.extractionInterval,
      minConfidence: MemoryAssistantSettings.shared.minConfidence,
      notificationsEnabled: MemoryAssistantSettings.shared.notificationsEnabled,
      excludedApps: Array(MemoryAssistantSettings.shared.excludedApps)
    )

    let floatingBar = FloatingBarSettingsResponse(
      voiceAnswersEnabled: ShortcutSettings.shared.floatingBarVoiceAnswersEnabled
    )

    return AssistantSettingsResponse(
      shared: shared,
      task: task,
      insight: insight,
      memory: memory,
      floatingBar: floatingBar,
      updateChannel: UpdaterViewModel.shared.updateChannel.rawValue
    )
  }

  /// The backend owns a bounded prompt field. Omitting an oversized custom value keeps
  /// partial PATCH semantics: other settings can sync while neither local nor remote user
  /// data is overwritten with a truncated prompt.
  static func promptForSync(
    _ prompt: String,
    assistantName: String,
    maximumLength: Int,
    shippedDefault: String
  ) -> String? {
    // Pydantic validates Python string length in Unicode code points. Swift's
    // unicodeScalars is the corresponding count; String.count measures extended
    // grapheme clusters and can undercount emoji and composed scripts.
    let length = prompt.unicodeScalars.count
    guard length <= maximumLength else {
      if isShippedDefault(prompt, shippedDefault: shippedDefault, assistantName: assistantName) {
        // Every install already ships this text, so an oversized default is not unsynced
        // user data — a later pull has nothing of the user's to destroy. Claiming
        // ownership here is what made `applyRemotePrompt` refuse the account's real
        // prompt forever on any Mac still sitting on the default (#11481).
        UserDefaults.standard.removeObject(forKey: oversizedPromptOwnerKey(assistantName))
        log(
          "SettingsSyncManager: omitted oversized shipped \(assistantName) default from sync "
            + "(\(length) Unicode scalars; max \(maximumLength))")
        return nil
      }
      if let owner = currentOwnerID {
        UserDefaults.standard.set(owner, forKey: oversizedPromptOwnerKey(assistantName))
      }
      log(
        "SettingsSyncManager: omitted oversized \(assistantName) prompt from sync "
          + "(\(length) Unicode scalars; max \(maximumLength))")
      return nil
    }
    UserDefaults.standard.removeObject(forKey: oversizedPromptOwnerKey(assistantName))
    return prompt
  }

  /// Record prompt provenance and ownership at the local write boundary, so an oversized
  /// user-authored value is protected even before the next network sync attempt.
  ///
  /// The provenance marker is what keeps a *previously* shipped default recognisable after
  /// the app ships a new one. By then the persisted text no longer matches the current
  /// default, but this recorded the answer while it still did.
  static func recordLocalPromptOwner(_ assistantName: String, isShippedDefault: Bool) {
    UserDefaults.standard.set(
      isShippedDefault, forKey: storedPromptIsShippedDefaultKey(assistantName))
    guard !isShippedDefault else {
      // Writing a shipped default releases any claim the previous value held: there is no
      // longer unsynced user text here for a pull to destroy.
      UserDefaults.standard.removeObject(forKey: oversizedPromptOwnerKey(assistantName))
      return
    }
    guard let owner = currentOwnerID else { return }
    UserDefaults.standard.set(owner, forKey: oversizedPromptOwnerKey(assistantName))
  }

  /// Whether a local prompt is a shipped default rather than something the user authored.
  ///
  /// Text comparison alone only recognises the *current* default, and the reset path
  /// persists the default it saw. After the app ships a new one, that stored text stops
  /// matching and would be misread as user-authored — claiming ownership and blocking the
  /// account's prompt all over again. The recorded marker covers exactly that window.
  ///
  /// An absent marker means a build older than this one wrote the value, so the text
  /// comparison stands alone and behaviour is unchanged for it.
  private static func isShippedDefault(
    _ prompt: String,
    shippedDefault: String,
    assistantName: String
  ) -> Bool {
    if prompt == shippedDefault { return true }
    return UserDefaults.standard.bool(forKey: storedPromptIsShippedDefaultKey(assistantName))
  }

  /// An oversized local prompt that the user wrote is unsynced data. Preserve it across
  /// pulls until they edit it back within the contract; otherwise a later server
  /// hydration would destroy the exact value deliberately omitted from PATCH.
  ///
  /// The shipped default is excluded: it is text every install already has, so there is
  /// nothing unsynced to lose, and a default that happens to exceed the bound must not
  /// veto the account's real prompt. That exclusion is what a fresh install, and a Mac
  /// that has just reset to the default, both depend on to receive it (#11481).
  private func applyRemotePrompt(
    _ remotePrompt: String,
    overLocalPrompt localPrompt: String,
    assistantName: String,
    maximumLength: Int,
    shippedDefault: String,
    apply: (String) -> Void
  ) {
    let localLength = localPrompt.unicodeScalars.count
    let recordedOwner = UserDefaults.standard.string(forKey: Self.oversizedPromptOwnerKey(assistantName))
    if !Self.isShippedDefault(
      localPrompt, shippedDefault: shippedDefault, assistantName: assistantName),
      localLength > maximumLength,
      let currentOwner = Self.currentOwnerID,
      recordedOwner == currentOwner
    {
      log(
        "SettingsSyncManager: preserved oversized local \(assistantName) prompt during server sync "
          + "(\(localLength) Unicode scalars; max \(maximumLength))")
      return
    }
    UserDefaults.standard.removeObject(forKey: Self.oversizedPromptOwnerKey(assistantName))
    apply(remotePrompt)
  }

  private static var currentOwnerID: String? {
    guard
      let value = UserDefaults.standard.string(forKey: .authUserId)?
        .trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty
    else { return nil }
    return value
  }

  private static func oversizedPromptOwnerKey(_ assistantName: String) -> String {
    "assistantPrompt.unsyncedOversizedOwner.\(assistantName)"
  }

  private static func storedPromptIsShippedDefaultKey(_ assistantName: String) -> String {
    "assistantPrompt.storedIsShippedDefault.\(assistantName)"
  }
}
