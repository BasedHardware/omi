import Foundation

/// Product-service startup for the signed-in home shell, gated on cutover admission.
///
/// LIFECYCLE: permanent
@MainActor
enum DesktopHomeSignedInStartup {
  static func runProductServicesIfAdmitted(
    appState: AppState,
    chatProvider: ChatProvider,
    scheduleInitialFileIndexing: () -> Void,
    restorePersistedCaptureServices: (_ reason: String) -> Void
  ) async {
    await AccountCutoverControlManager.shared.prepareSignedInShell()
    guard AccountCutoverControlManager.shared.isProductShellAdmitted else {
      log("DesktopHomeSignedInStartup: product services deferred until cutover admits traffic")
      return
    }

    if !AppBuild.usesLazyDevPermissions
      && !UserDefaults.standard.bool(forKey: .hasCompletedFileIndexing)
    {
      scheduleInitialFileIndexing()
    }

    if !UserDefaults.standard.bool(forKey: .screenAnalysisAutoStartFixedV2) {
      let enabled = SettingsSyncManager.shared.restoreScreenAnalysisDefaultForMigration()
      UserDefaults.standard.set(true, forKey: .screenAnalysisAutoStartFixedV2)
      log("DesktopHomeView: Applied screenAnalysisAutoStart v2 migration preserving local off")
      SettingsSyncManager.shared.pushPartialUpdate(
        SettingsSyncManager.screenAnalysisEnabledUpdate(enabled))
    }

    if RewindCaptureState.shouldRepairQuietBundleCaptureDefault(
      usesLazyDevPermissions: AppBuild.usesLazyDevPermissions,
      migrationApplied: UserDefaults.standard.bool(forKey: .screenAnalysisAutoStartFixedV3)
    ) {
      SettingsSyncManager.shared.restoreScreenAnalysisDefaultForMigration()
      UserDefaults.standard.set(true, forKey: .screenAnalysisAutoStartFixedV3)
      log("DesktopHomeView: Restored screen capture default for quiet named bundle")
    }

    restorePersistedCaptureServices("launch")

    FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
    FloatingControlBarManager.shared.presentForLaunch(context: .normalSignedInDesktop)

    if let barState = FloatingControlBarManager.shared.barState {
      PushToTalkManager.shared.setup(barState: barState)
    }

    DesktopUsageDailyReporter.shared.start(
      isWatching: { ProactiveAssistantsPlugin.shared.isMonitoring },
      isListening: { [weak appState] in
        appState?.isLiveCapturing == true
          || VoiceTurnCoordinator.shared.activeTurn?.phase.isRecording == true
      })
  }

  static func loadDataIfAdmitted(
    loadAllData: () async -> Void,
    scheduleConversationWarmup: () -> Void,
    scheduleAgentVMProvisioning: () -> Void
  ) async {
    await AccountCutoverControlManager.shared.prepareSignedInShell()
    guard AccountCutoverControlManager.shared.isProductShellAdmitted else { return }
    await loadAllData()
    scheduleConversationWarmup()
    scheduleAgentVMProvisioning()
  }
}
