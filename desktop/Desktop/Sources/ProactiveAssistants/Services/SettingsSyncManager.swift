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

    // MARK: - Apply Remote → Local

    private func applyRemoteSettings(_ remote: AssistantSettingsResponse) {
        // Shared settings
        if let shared = remote.shared {
            if let v = shared.cooldownInterval { AssistantSettings.shared.cooldownInterval = v }
            if let v = shared.glowOverlayEnabled { AssistantSettings.shared.glowOverlayEnabled = v }
            if let v = shared.analysisDelay { AssistantSettings.shared.analysisDelay = v }
            if let v = shared.screenAnalysisEnabled { AssistantSettings.shared.screenAnalysisEnabled = v }
        }

        // Focus settings
        if let focus = remote.focus {
            if let v = focus.enabled { FocusAssistantSettings.shared.isEnabled = v }
            if let v = focus.analysisPrompt { FocusAssistantSettings.shared.analysisPrompt = v }
            if let v = focus.cooldownInterval { FocusAssistantSettings.shared.cooldownInterval = v }
            if let v = focus.notificationsEnabled { FocusAssistantSettings.shared.notificationsEnabled = v }
            if let v = focus.excludedApps { FocusAssistantSettings.shared.excludedApps = Set(v) }
        }

        // Task settings
        if let task = remote.task {
            if let v = task.enabled { TaskAssistantSettings.shared.isEnabled = v }
            if let v = task.analysisPrompt { TaskAssistantSettings.shared.analysisPrompt = v }
            if let v = task.extractionInterval { TaskAssistantSettings.shared.extractionInterval = v }
            if let v = task.minConfidence { TaskAssistantSettings.shared.minConfidence = v }
            if let v = task.notificationsEnabled { TaskAssistantSettings.shared.notificationsEnabled = v }
            if let v = task.allowedApps { TaskAssistantSettings.shared.allowedApps = Set(v) }
            if let v = task.browserKeywords { TaskAssistantSettings.shared.browserKeywords = v }
        }

        // Advice settings
        if let advice = remote.advice {
            if let v = advice.enabled { AdviceAssistantSettings.shared.isEnabled = v }
            if let v = advice.analysisPrompt { AdviceAssistantSettings.shared.analysisPrompt = v }
            if let v = advice.extractionInterval { AdviceAssistantSettings.shared.extractionInterval = v }
            if let v = advice.minConfidence { AdviceAssistantSettings.shared.minConfidence = v }
            if let v = advice.notificationsEnabled { AdviceAssistantSettings.shared.notificationsEnabled = v }
            if let v = advice.excludedApps { AdviceAssistantSettings.shared.excludedApps = Set(v) }
        }

        // Memory settings
        if let memory = remote.memory {
            if let v = memory.enabled { MemoryAssistantSettings.shared.isEnabled = v }
            if let v = memory.analysisPrompt { MemoryAssistantSettings.shared.analysisPrompt = v }
            if let v = memory.extractionInterval { MemoryAssistantSettings.shared.extractionInterval = v }
            if let v = memory.minConfidence { MemoryAssistantSettings.shared.minConfidence = v }
            if let v = memory.notificationsEnabled { MemoryAssistantSettings.shared.notificationsEnabled = v }
            if let v = memory.excludedApps { MemoryAssistantSettings.shared.excludedApps = Set(v) }
        }
    }

    // MARK: - Build Local → Response

    private func buildFromLocal() -> AssistantSettingsResponse {
        let shared = SharedAssistantSettingsResponse(
            cooldownInterval: AssistantSettings.shared.cooldownInterval,
            glowOverlayEnabled: AssistantSettings.shared.glowOverlayEnabled,
            analysisDelay: AssistantSettings.shared.analysisDelay,
            screenAnalysisEnabled: AssistantSettings.shared.screenAnalysisEnabled
        )

        let focus = FocusSettingsResponse(
            enabled: FocusAssistantSettings.shared.isEnabled,
            analysisPrompt: FocusAssistantSettings.shared.analysisPrompt,
            cooldownInterval: FocusAssistantSettings.shared.cooldownInterval,
            notificationsEnabled: FocusAssistantSettings.shared.notificationsEnabled,
            excludedApps: Array(FocusAssistantSettings.shared.excludedApps)
        )

        let task = TaskSettingsResponse(
            enabled: TaskAssistantSettings.shared.isEnabled,
            analysisPrompt: TaskAssistantSettings.shared.analysisPrompt,
            extractionInterval: TaskAssistantSettings.shared.extractionInterval,
            minConfidence: TaskAssistantSettings.shared.minConfidence,
            notificationsEnabled: TaskAssistantSettings.shared.notificationsEnabled,
            allowedApps: Array(TaskAssistantSettings.shared.allowedApps),
            browserKeywords: TaskAssistantSettings.shared.browserKeywords
        )

        let advice = AdviceSettingsResponse(
            enabled: AdviceAssistantSettings.shared.isEnabled,
            analysisPrompt: AdviceAssistantSettings.shared.analysisPrompt,
            extractionInterval: AdviceAssistantSettings.shared.extractionInterval,
            minConfidence: AdviceAssistantSettings.shared.minConfidence,
            notificationsEnabled: AdviceAssistantSettings.shared.notificationsEnabled,
            excludedApps: Array(AdviceAssistantSettings.shared.excludedApps)
        )

        let memory = MemorySettingsResponse(
            enabled: MemoryAssistantSettings.shared.isEnabled,
            analysisPrompt: MemoryAssistantSettings.shared.analysisPrompt,
            extractionInterval: MemoryAssistantSettings.shared.extractionInterval,
            minConfidence: MemoryAssistantSettings.shared.minConfidence,
            notificationsEnabled: MemoryAssistantSettings.shared.notificationsEnabled,
            excludedApps: Array(MemoryAssistantSettings.shared.excludedApps)
        )

        return AssistantSettingsResponse(
            shared: shared,
            focus: focus,
            task: task,
            advice: advice,
            memory: memory
        )
    }
}
