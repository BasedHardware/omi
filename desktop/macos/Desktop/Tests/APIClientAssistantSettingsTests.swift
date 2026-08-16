import XCTest

@testable import Omi_Computer

final class APIClientAssistantSettingsTests: XCTestCase {

  @MainActor
  func testShippedTaskPromptExceedsBackendBoundAndIsOmittedFromSync() {
    // The shipped default task prompt has been over the backend's 10k-code-point
    // bound since at least June 2026, so it is deliberately omitted from sync
    // (partial PATCH semantics) rather than truncated or sent to be 422-rejected.
    // Raising the bound needs the backend limit deployed first: issue #11481.
    XCTAssertGreaterThan(
      TaskAssistantSettings.defaultAnalysisPrompt.unicodeScalars.count,
      TaskAssistantSettings.maximumSyncedAnalysisPromptLength)
    XCTAssertNil(
      SettingsSyncManager.promptForSync(
        TaskAssistantSettings.defaultAnalysisPrompt,
        assistantName: "task",
        maximumLength: TaskAssistantSettings.maximumSyncedAnalysisPromptLength,
        shippedDefault: TaskAssistantSettings.defaultAnalysisPrompt))
  }

  @MainActor
  func testOversizedCustomPromptIsOmittedWithoutTruncation() {
    let customPrompt = String(
      repeating: "x", count: TaskAssistantSettings.maximumSyncedAnalysisPromptLength + 1)

    XCTAssertNil(
      SettingsSyncManager.promptForSync(
        customPrompt,
        assistantName: "task",
        maximumLength: TaskAssistantSettings.maximumSyncedAnalysisPromptLength,
        shippedDefault: TaskAssistantSettings.defaultAnalysisPrompt))
    XCTAssertEqual(
      customPrompt.count, TaskAssistantSettings.maximumSyncedAnalysisPromptLength + 1)
  }

  @MainActor
  func testPromptSyncUsesBackendUnicodeCodePointLength() {
    let flag = "🇺🇸"  // One Swift Character, two Unicode scalars/code points.
    let prompt = String(repeating: flag, count: 5_001)

    XCTAssertEqual(prompt.count, 5_001)
    XCTAssertEqual(prompt.unicodeScalars.count, 10_002)
    XCTAssertNil(
      SettingsSyncManager.promptForSync(
        prompt, assistantName: "insight", maximumLength: 10_000,
        shippedDefault: InsightAssistantSettings.defaultAnalysisPrompt))
  }

  @MainActor
  func testEachAssistantPromptUsesItsBackendBound() {
    // All three assistants share the backend's 10k bound today; task has no raised
    // bound until the backend limit ships first (issue #11481).
    let backendMaximum = 10_000
    XCTAssertEqual(TaskAssistantSettings.maximumSyncedAnalysisPromptLength, backendMaximum)
    let prompt = String(repeating: "x", count: backendMaximum + 1)
    let assistants: [(name: String, shippedDefault: String)] = [
      ("task", TaskAssistantSettings.defaultAnalysisPrompt),
      ("insight", InsightAssistantSettings.defaultAnalysisPrompt),
      ("memory", MemoryAssistantSettings.defaultAnalysisPrompt),
    ]

    for assistant in assistants {
      XCTAssertNil(
        SettingsSyncManager.promptForSync(
          prompt, assistantName: assistant.name, maximumLength: backendMaximum,
          shippedDefault: assistant.shippedDefault),
        "an oversized \(assistant.name) prompt must be omitted, not truncated or sent")
    }
  }

  @MainActor
  func testRemoteHydrationPreservesOversizedUnsyncedLocalTaskPrompt() {
    let originalPrompt = TaskAssistantSettings.shared.analysisPrompt
    let originalOwner = UserDefaults.standard.string(forKey: .authUserId)
    defer {
      TaskAssistantSettings.shared.analysisPrompt = originalPrompt
      UserDefaults.standard.set(originalOwner, forKey: .authUserId)
    }
    UserDefaults.standard.set("owner-a", forKey: .authUserId)
    let localPrompt = String(
      repeating: "x", count: TaskAssistantSettings.maximumSyncedAnalysisPromptLength + 1)
    TaskAssistantSettings.shared.analysisPrompt = localPrompt

    SettingsSyncManager.shared.applyRemoteSettings(
      AssistantSettingsResponse(task: TaskSettingsResponse(analysisPrompt: "remote prompt")))

    XCTAssertEqual(TaskAssistantSettings.shared.analysisPrompt, localPrompt)
  }

  // MARK: - The shipped default is not unsynced user data (#11481)
  //
  // The oversized-prompt protection defends text the user wrote that the server never
  // accepted. The shipped task default is not that: it is over the 10k bound, but every
  // install already has it, so there is nothing unsynced to lose. Treating it as owned
  // made `applyRemotePrompt` refuse every remote prompt, so a prompt customised on one
  // Mac could never reach a Mac still sitting on the default.
  //
  // Ownership is asserted through its observable consequence — whether a later pull is
  // allowed to hydrate — rather than by reading the bookkeeping key.

  @MainActor
  private func withTaskPromptState(owner: String, _ body: () -> Void) {
    let originalPrompt = TaskAssistantSettings.shared.analysisPrompt
    let originalOwner = UserDefaults.standard.string(forKey: .authUserId)
    defer {
      TaskAssistantSettings.shared.analysisPrompt = originalPrompt
      UserDefaults.standard.set(originalOwner, forKey: .authUserId)
    }
    UserDefaults.standard.set(owner, forKey: .authUserId)
    body()
  }

  @MainActor
  private func hydrateTaskPrompt(_ remotePrompt: String) {
    SettingsSyncManager.shared.applyRemoteSettings(
      AssistantSettingsResponse(task: TaskSettingsResponse(analysisPrompt: remotePrompt)))
  }

  /// Fresh install: nothing stored, so the getter serves the shipped default. The push
  /// still omits it — it is over the bound — but must not claim it as unsynced user data,
  /// or the account's own prompt can never arrive.
  @MainActor
  func testShippedDefaultIsOmittedFromSyncWithoutBlockingLaterHydration() {
    withTaskPromptState(owner: "owner-fresh-install") {
      TaskAssistantSettings.shared.resetPromptToDefault()

      XCTAssertNil(
        SettingsSyncManager.promptForSync(
          TaskAssistantSettings.shared.analysisPrompt,
          assistantName: "task",
          maximumLength: TaskAssistantSettings.maximumSyncedAnalysisPromptLength,
          shippedDefault: TaskAssistantSettings.defaultAnalysisPrompt),
        "the shipped default is over the bound, so it still cannot be sent")

      hydrateTaskPrompt("prompt from another mac")

      XCTAssertEqual(
        TaskAssistantSettings.shared.analysisPrompt,
        "prompt from another mac",
        "omitting the default must not also claim it as unsynced user data")
    }
  }

  /// Reset means this device has no custom local opinion, so account state may hydrate
  /// again — even though the prompt the user is resetting away from did own the stamp.
  @MainActor
  func testRemoteHydrationAppliesAfterResetToDefault() {
    withTaskPromptState(owner: "owner-reset") {
      TaskAssistantSettings.shared.analysisPrompt = String(
        repeating: "x", count: TaskAssistantSettings.maximumSyncedAnalysisPromptLength + 1)
      TaskAssistantSettings.shared.resetPromptToDefault()

      hydrateTaskPrompt("account prompt")

      XCTAssertEqual(
        TaskAssistantSettings.shared.analysisPrompt,
        "account prompt",
        "a reset leaves no local opinion, so a stale stamp must not veto the account")
    }
  }

  /// The reset the UI actually performs. `TaskPromptEditorView.resetToDefault()` clears the
  /// stored prompt, then assigns the editor's `@State`, which fires `.onChange` and writes
  /// the default straight back through the setter — re-storing it *and* re-stamping
  /// ownership. Key presence therefore cannot tell "user authored this" from "user reset
  /// to default"; the prompt text can.
  @MainActor
  func testRemoteHydrationAppliesAfterTheResetPathTheEditorPerforms() {
    withTaskPromptState(owner: "owner-editor-reset") {
      TaskAssistantSettings.shared.analysisPrompt = String(
        repeating: "x", count: TaskAssistantSettings.maximumSyncedAnalysisPromptLength + 1)
      TaskAssistantSettings.shared.resetPromptToDefault()
      // What the editor's .onChange does immediately afterwards.
      TaskAssistantSettings.shared.analysisPrompt = TaskAssistantSettings.defaultAnalysisPrompt

      hydrateTaskPrompt("account prompt")

      XCTAssertEqual(
        TaskAssistantSettings.shared.analysisPrompt,
        "account prompt",
        "a re-stamped shipped default must still not veto the account's prompt")
    }
  }

  @MainActor
  func testRemoteHydrationReplacesOversizedPromptOwnedByAnotherAccount() {
    let originalPrompt = TaskAssistantSettings.shared.analysisPrompt
    let originalOwner = UserDefaults.standard.string(forKey: .authUserId)
    defer {
      TaskAssistantSettings.shared.analysisPrompt = originalPrompt
      UserDefaults.standard.set(originalOwner, forKey: .authUserId)
    }
    let localPrompt = String(
      repeating: "x", count: TaskAssistantSettings.maximumSyncedAnalysisPromptLength + 1)
    UserDefaults.standard.set("owner-a", forKey: .authUserId)
    TaskAssistantSettings.shared.analysisPrompt = localPrompt
    UserDefaults.standard.set("owner-b", forKey: .authUserId)

    SettingsSyncManager.shared.applyRemoteSettings(
      AssistantSettingsResponse(task: TaskSettingsResponse(analysisPrompt: "owner b prompt")))

    XCTAssertEqual(TaskAssistantSettings.shared.analysisPrompt, "owner b prompt")
  }

  @MainActor
  func testRemoteHydrationRemainsServerAuthoritativeForSyncableTaskPrompt() {
    let originalPrompt = TaskAssistantSettings.shared.analysisPrompt
    defer { TaskAssistantSettings.shared.analysisPrompt = originalPrompt }
    TaskAssistantSettings.shared.analysisPrompt = "local prompt"

    SettingsSyncManager.shared.applyRemoteSettings(
      AssistantSettingsResponse(task: TaskSettingsResponse(analysisPrompt: "remote prompt")))

    XCTAssertEqual(TaskAssistantSettings.shared.analysisPrompt, "remote prompt")
  }

  @MainActor
  func testScreenAnalysisMigrationPayloadExcludesUnrelatedAssistantSettings() throws {
    let update = SettingsSyncManager.screenAnalysisEnabledUpdate(true)
    let encoded = try JSONEncoder().encode(update)
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
    let shared = try XCTUnwrap(object["shared"] as? [String: Any])

    XCTAssertEqual(Set(object.keys), ["shared"])
    XCTAssertEqual(Set(shared.keys), ["screen_analysis_enabled"])
    XCTAssertEqual(shared["screen_analysis_enabled"] as? Bool, true)
  }

  func testAssistantSettingsDecodesValidSiblingsWhenOneKnownSectionIsMalformed() throws {
    let data = """
      {
        "focus": "not-yet-a-focus-object",
        "task": {
          "enabled": true,
          "min_confidence": 0.72
        },
        "floating_bar": {
          "voice_answers_enabled": true,
          "elevenlabs_voice_id": "voice-123"
        },
        "update_channel": "beta"
      }
      """.data(using: .utf8)!

    let response = try JSONDecoder().decode(AssistantSettingsResponse.self, from: data)

    XCTAssertEqual(response.task?.enabled, true)
    XCTAssertEqual(response.task?.minConfidence, 0.72)
    XCTAssertEqual(response.floatingBar?.voiceAnswersEnabled, true)
    XCTAssertEqual(response.floatingBar?.elevenlabsVoiceId, "voice-123")
    XCTAssertEqual(response.updateChannel, "beta")
  }

  func testAssistantSettingsPreservesUnknownFutureSectionsWhenReEncoding() throws {
    let data = """
      {
        "focus": {
          "enabled": false
        },
        "future_section": {
          "enabled": true,
          "threshold": 3,
          "labels": ["alpha", "beta"]
        }
      }
      """.data(using: .utf8)!

    let response = try JSONDecoder().decode(AssistantSettingsResponse.self, from: data)
    XCTAssertEqual(
      response.unknownSections["future_section"],
      .object([
        "enabled": .bool(true),
        "threshold": .int(3),
        "labels": .array([.string("alpha"), .string("beta")]),
      ])
    )

    let encoded = try JSONEncoder().encode(response)
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
    let futureSection = try XCTUnwrap(object["future_section"] as? [String: Any])

    XCTAssertEqual(futureSection["enabled"] as? Bool, true)
    XCTAssertEqual(futureSection["threshold"] as? Int, 3)
    XCTAssertEqual(futureSection["labels"] as? [String], ["alpha", "beta"])
  }
}
