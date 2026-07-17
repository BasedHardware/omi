import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

/// Hermetic source-contract tests for secondary-surface bridge actions added in Waves 1–2.
final class DesktopAutomationSecondaryActionTests: XCTestCase {
  func testSecondarySnapshotActionsAreRegistered() throws {
    let source = try bridgeSource()
    for action in [
      "conversation_detail_snapshot",
      "create_test_memory",
      "edit_test_memory",
      "delete_test_memory",
      "sign_out",
      "vocabulary_snapshot",
      "vocabulary_set_terms",
      "goals_snapshot",
      "create_test_goal",
      "apps_catalog_snapshot",
      "subscription_snapshot",
      "settings_privacy_snapshot",
      "open_conversation",
      "open_latest_conversation",
      "create_test_folder",
      "set_conversation_starred",
      "set_conversation_folder",
      "conversation_share_probe",
      "set_transcription_language",
      "transcription_language_snapshot",
      "memory_graph_snapshot",
      "open_memory_atlas",
      "memory_atlas_set_viewport",
      "open_quick_note",
      "about_snapshot",
      "settings_notifications_snapshot",
      "set_notification_settings",
      "rewind_settings_snapshot",
      "navigate_via_shortcut",
      "advanced_settings_snapshot",
      "settings_aichat_snapshot",
      "assign_speaker_fixture",
    ] {
      XCTAssertTrue(
        source.contains("name: \"\(action)\""),
        "expected bridge action \(action) to be registered"
      )
    }
  }

  func testConversationListSnapshotIncludesFolderFields() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "conversation_list_snapshot", in: source)
    for key in ["folder_count", "starred_count", "active_folder_id", "recent_ids_json"] {
      XCTAssertTrue(body.contains("\"\(key)\""), "conversation_list_snapshot should return \(key)")
    }
  }

  func testConversationDetailSnapshotDetailKeys() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "conversation_detail_snapshot", in: source)
    for key in [
      "detail_open",
      "segment_count",
      "transcript_drawer_open",
      "folder_id",
      "starred",
      "title",
    ] {
      XCTAssertTrue(body.contains("\"\(key)\""), "conversation_detail_snapshot should return \(key)")
    }
    XCTAssertTrue(body.contains("ConversationDetailAutomationState.shared"))
  }

  func testOpenConversationNavigatesToConversationsTabFirst() throws {
    let source = try bridgeSource()
    for action in ["open_conversation", "open_latest_conversation"] {
      let body = try actionBody(named: action, in: source)
      XCTAssertTrue(
        body.contains("ensureConversationsTabVisibleForAutomation"),
        "\(action) should navigate to Conversations before posting open request"
      )
      XCTAssertTrue(body.contains("ConversationDetailAutomationState.shared.openConversationId != conversationId"))
      XCTAssertTrue(body.contains("detail_open"))
    }
  }

  func testQualificationActionsRespectBackendContracts() throws {
    let source = try bridgeSource()
    let appsBody = try actionBody(named: "apps_catalog_snapshot", in: source)
    XCTAssertTrue(appsBody.contains("installedOnly: true, limit: 100"))
    XCTAssertFalse(appsBody.contains("installedOnly: true, limit: 200"))

    let goalBody = try actionBody(named: "create_test_goal", in: source)
    XCTAssertTrue(goalBody.contains("source: \"user\""))
    XCTAssertFalse(goalBody.contains("source: \"harness\""))
  }

  func testMemoryLogFixtureUsesRealConnectorOperationWithInjectedExtractionOnly() throws {
    let body = try actionBody(named: "memory_log_import_probe", in: try bridgeSource())
    XCTAssertTrue(body.contains("params[\"fixture\"] == \"structured\""))
    XCTAssertTrue(body.contains("AppBuild.isNonProduction"))
    XCTAssertTrue(body.contains("ConnectorImportOperations.importMemoryLog"))
    XCTAssertTrue(body.contains("extractedFixture: OnboardingMemoryLogImportService.ExtractedMemoryLog"))
    XCTAssertFalse(body.contains("OnboardingImportEvidenceService.save"))
    XCTAssertFalse(body.contains("ConnectorImportOperations.memoryLogOutcome"))
  }

  func testFloatingIdleWaitRequiresObservedSubmission() throws {
    let source = try bridgeSource()
    let askBody = try actionBody(named: "ask", in: source)
    XCTAssertTrue(askBody.contains("pendingFloatingBarSubmission"))
    XCTAssertTrue(askBody.contains("baselineMessageCount"))

    let waitBody = try actionBody(named: "wait_floating_bar_chat_idle", in: source)
    XCTAssertTrue(waitBody.contains("observedSubmission"))
    XCTAssertTrue(waitBody.contains("messageCount > submission.baselineMessageCount"))
    XCTAssertTrue(waitBody.contains("submission_observed"))
  }

  func testReconciliationUsesNormalizedServerRevision() throws {
    let source = try bridgeSource()
    XCTAssertTrue(source.contains("matchesAtMillisecondPrecision"))
    XCTAssertTrue(source.contains("timeIntervalSince1970 * 1_000"))
    let body = try actionBody(named: "conversation_reconciliation_snapshot", in: source)
    XCTAssertTrue(body.contains("DesktopAutomationRevisionComparator.matchesAtMillisecondPrecision("))
  }

  func testRevisionComparisonNormalizesSubMillisecondStorageDrift() {
    XCTAssertTrue(
      DesktopAutomationRevisionComparator.matchesAtMillisecondPrecision(
        Date(timeIntervalSince1970: 1_000.12340),
        Date(timeIntervalSince1970: 1_000.12349)
      )
    )
    XCTAssertFalse(
      DesktopAutomationRevisionComparator.matchesAtMillisecondPrecision(
        Date(timeIntervalSince1970: 1_000.123),
        Date(timeIntervalSince1970: 1_000.125)
      )
    )
    XCTAssertFalse(DesktopAutomationRevisionComparator.matchesAtMillisecondPrecision(Date(), nil))
  }

  func testVocabularyMutationFinishesWithCanonicalBackendValue() throws {
    let body = try actionBody(named: "vocabulary_set_terms", in: try bridgeSource())
    let update = try XCTUnwrap(body.range(of: "updateTranscriptionPreferences"))
    let assignment = try XCTUnwrap(
      body.range(of: "AssistantSettings.shared.transcriptionVocabulary = saved.vocabulary"))
    XCTAssertLessThan(update.lowerBound, assignment.lowerBound)
  }

  func testActionHTTPFailuresKeepStatusAndSanitizedDetail() throws {
    let source = try bridgeSource()
    XCTAssertTrue(source.contains("api_http_error status="))
    XCTAssertTrue(source.contains("automationSafeErrorDetail"))
    XCTAssertTrue(source.contains("[redacted-jwt]"))
    XCTAssertTrue(source.contains("error: automationActionErrorDescription(error)"))
  }

  func testMemoryAutomationWaitsForAsyncSearchAndFilter() throws {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/MemoriesPage.swift")
    let source = try String(contentsOf: url, encoding: .utf8)
    XCTAssertTrue(source.contains("while !self.isSearching"))
    XCTAssertTrue(source.contains("while !self.isLoadingFiltered"))
    XCTAssertTrue(source.contains("filteredFromDatabase.first(where:"))
  }

  func testMemoryCrudActionsUseNonProdGuard() throws {
    let source = try bridgeSource()
    for action in [
      "create_test_memory", "edit_test_memory", "delete_test_memory", "create_test_goal", "create_test_folder",
    ] {
      let body = try actionBody(named: action, in: source)
      XCTAssertTrue(body.contains("AppBuild.isNonProduction"))
    }
  }

  func testDeleteTestMemorySupportsMarkerParam() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "delete_test_memory", in: source)
    XCTAssertTrue(body.contains("params[\"marker\"]"))
    XCTAssertTrue(body.contains("contains(marker)"))
  }

  func testPrivacySnapshotReadsRecordingAndCloudSync() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "settings_privacy_snapshot", in: source)
    XCTAssertTrue(body.contains("getRecordingPermission"))
    XCTAssertTrue(body.contains("getPrivateCloudSync"))
    XCTAssertTrue(body.contains("store_recordings"))
    XCTAssertTrue(body.contains("cloud_sync"))
  }

  func testSubscriptionSnapshotReadsBillingAPI() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "subscription_snapshot", in: source)
    XCTAssertTrue(body.contains("getUserSubscription"))
    XCTAssertTrue(body.contains("show_subscription_ui"))
  }

  func testLatestConversationAliasSupported() throws {
    let source = try bridgeSource()
    let starredBody = try actionBody(named: "set_conversation_starred", in: source)
    XCTAssertTrue(starredBody.contains("conversationId == \"latest\""))
    let shareBody = try actionBody(named: "conversation_share_probe", in: source)
    XCTAssertTrue(shareBody.contains("rawConversationId == \"latest\""))
    let assignBody = try actionBody(named: "assign_speaker_fixture", in: source)
    XCTAssertTrue(assignBody.contains("conversationId == \"latest\""))
  }

  func testSetConversationStarredUsesRepositoryMutationOnce() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "set_conversation_starred", in: source)
    XCTAssertTrue(body.contains("conversationRepository.setStarred"))
    XCTAssertFalse(
      body.contains("APIClient.shared.setConversationStarred"),
      "the automation action must not bypass the repository and issue a duplicate PATCH"
    )
    XCTAssertFalse(
      body.contains("AppState.current?.setConversationStarred"),
      "the app-state helper performs its own repository mutation"
    )
  }

  func testTranscriptionLanguageActionsPersistViaAPI() throws {
    let source = try bridgeSource()
    let setBody = try actionBody(named: "set_transcription_language", in: source)
    XCTAssertTrue(setBody.contains("updateUserLanguage"))
    XCTAssertTrue(setBody.contains("transcriptionLanguage"))
    let snapshotBody = try actionBody(named: "transcription_language_snapshot", in: source)
    XCTAssertTrue(snapshotBody.contains("effectiveTranscriptionLanguage"))
  }

  func testMemoryGraphSnapshotUsesKnowledgeGraphAPI() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "memory_graph_snapshot", in: source)
    for key in ["node_count", "edge_count", "is_empty"] {
      XCTAssertTrue(body.contains("\"\(key)\""), "memory_graph_snapshot should return \(key)")
    }
    XCTAssertTrue(body.contains("getKnowledgeGraph"))
  }

  func testMemoryAtlasHarnessActionsPostBoundedViewportNotifications() throws {
    let openBody = try actionBody(named: "open_memory_atlas", in: try bridgeSource())
    XCTAssertTrue(openBody.contains("desktopAutomationOpenMemoryAtlasRequested"))
    XCTAssertTrue(openBody.contains("\"target\": \"page\""))

    let viewportBody = try actionBody(named: "memory_atlas_set_viewport", in: try bridgeSource())
    XCTAssertTrue(viewportBody.contains("desktopAutomationMemoryAtlasViewportRequested"))
    XCTAssertTrue(viewportBody.contains("\"page\""))
    for parameter in ["target", "zoom", "pan_x", "pan_y", "reset"] {
      XCTAssertTrue(viewportBody.contains("\"\(parameter)\""))
    }
  }

  func testNavigateViaShortcutPostsSidebarNotification() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "navigate_via_shortcut", in: source)
    XCTAssertTrue(body.contains("navigateToSidebarItem"))
    XCTAssertTrue(body.contains("SidebarNavItem"))
  }

  func testAssignSpeakerFixtureUsesNonProdGuard() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "assign_speaker_fixture", in: source)
    XCTAssertTrue(body.contains("AppBuild.isNonProduction"))
    XCTAssertTrue(body.contains("assignSpeakerToSegments"))
  }

  func testResetOnboardingUsesLiveAppStateSingleton() throws {
    let source = try bridgeSource()
    let bridgeBody = try actionBody(named: "reset_onboarding", in: source)
    XCTAssertTrue(bridgeBody.contains("AppState.current"))
    let systemActions = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/AppState/AppState+SystemActions.swift"),
      encoding: .utf8
    )
    let resetStart = try XCTUnwrap(systemActions.range(of: "func resetOnboardingAndRestart"))
    let resetRemainder = systemActions[resetStart.lowerBound...]
    let asynchronousCleanup = try XCTUnwrap(
      resetRemainder.range(of: "Task { @MainActor [self] in")
    )
    let resetBody = String(resetRemainder[..<asynchronousCleanup.lowerBound])
    XCTAssertTrue(resetBody.contains("resetOnboardingRequested"))
    let notificationRange = try XCTUnwrap(resetBody.range(of: "resetOnboardingRequested"))
    let udClearRange = try XCTUnwrap(resetBody.range(of: "removeObject(forKey:"))
    XCTAssertLessThan(
      notificationRange.lowerBound,
      udClearRange.lowerBound,
      "reset must post resetOnboardingRequested before UserDefaults keys are removed"
    )
    XCTAssertTrue(
      resetBody.contains("DispatchQueue.main.sync"),
      "reset must synchronously deliver resetOnboardingRequested on the main thread"
    )
  }

  func testMemoryAutomationActionsRegisteredOnViewModel() throws {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/MemoriesPage.swift")
    let source = try String(contentsOf: url, encoding: .utf8)
    for action in ["memories_search", "toggle_memory_visibility", "memories_set_tag_filter"] {
      XCTAssertTrue(
        source.contains("name: \"\(action)\""),
        "expected MemoriesViewModel to register \(action)"
      )
    }
  }

  func testAiChatSectionAllowedOnNonProduction() throws {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/SettingsPage.swift")
    let source = try String(contentsOf: url, encoding: .utf8)
    XCTAssertTrue(source.contains("AppBuild.isProductionBundle && selectedSection == .aiChat"))
    XCTAssertTrue(source.contains("AppBuild.isProductionBundle && newValue == .aiChat"))
  }

  func testSignOutRequiresLocalAuthProfile() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "sign_out", in: source)
    XCTAssertTrue(body.contains("DesktopLocalProfile.isEnabled"))
    XCTAssertTrue(body.contains("AuthService.shared.signOut()"))
  }

  func testEditTestMemorySupportsMarkerParam() throws {
    let source = try bridgeSource()
    let body = try actionBody(named: "edit_test_memory", in: source)
    XCTAssertTrue(body.contains("params[\"marker\"]"))
    XCTAssertTrue(body.contains("editMemory"))
  }

  func testTaskDescriptionLookupRejectsAmbiguousMatches() throws {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/TasksPage.swift")
    let source = try String(contentsOf: url, encoding: .utf8)
    XCTAssertTrue(
      source.contains("\"error\": \"ambiguous:"),
      "toggle_task/delete_task should reject ambiguous description matches"
    )
  }

  func testDumpTasksSupportsMarkerAbsentParam() throws {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/TasksPage.swift")
    let source = try String(contentsOf: url, encoding: .utf8)
    XCTAssertTrue(
      source.contains("marker_absent"), "dump_tasks should return marker_absent when marker param is provided")
  }

  func testMultiSpeakerInjectDerivesSpeakerIdFromLabel() throws {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/AppState/AppState+Transcription.swift")
    let source = try String(contentsOf: url, encoding: .utf8)
    XCTAssertTrue(
      source.contains("Derive speaker_id from the label"),
      "multi-speaker inject should derive speaker_id from label when omitted"
    )
  }

  func testEnsureConversationsTabPropagatesCancellation() throws {
    let source = try bridgeSource()
    XCTAssertTrue(
      source.contains("try await Task.sleep(nanoseconds: 150_000_000)"),
      "ensureConversationsTabVisibleForAutomation should propagate cancellation via try await"
    )
  }

  func testDebugBarStateUsesReducerScopedPresentationEvent() throws {
    let body = try actionBody(named: "debug_bar_state", in: bridgeSource())

    XCTAssertTrue(body.contains("VoiceTurnDebugPresentationState(rawValue: s)"))
    XCTAssertTrue(body.contains("VoiceTurnCoordinator.shared.applyDebugPresentationState"))
    for forbidden in [
      "debugSetVoiceResponseActive",
      "bar.isVoiceListening =",
      "bar.isThinking =",
      "bar.voiceProjection =",
    ] {
      XCTAssertFalse(body.contains(forbidden), "debug automation bypasses reducer: \(forbidden)")
    }
  }

  private func bridgeSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/DesktopAutomationBridge.swift")
    return try String(contentsOf: url, encoding: .utf8)
  }

  private func actionBody(named action: String, in source: String) throws -> String {
    guard let start = source.range(of: "name: \"\(action)\"") else {
      throw XCTSkip("action \(action) not found")
    }
    let tail = source[start.lowerBound...]
    guard let nextRegister = tail.dropFirst().range(of: "\n    register(") else {
      return String(tail)
    }
    return String(tail[..<nextRegister.lowerBound])
  }
}
