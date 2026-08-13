import XCTest

@testable import Omi_Computer

final class APIClientAssistantSettingsTests: XCTestCase {

  @MainActor
  func testShippedTaskPromptFitsBackendSyncContract() {
    XCTAssertLessThanOrEqual(
      TaskAssistantSettings.defaultAnalysisPrompt.count,
      TaskAssistantSettings.maximumSyncedAnalysisPromptLength)
  }

  @MainActor
  func testOversizedCustomPromptIsOmittedWithoutTruncation() {
    let customPrompt = String(
      repeating: "x", count: TaskAssistantSettings.maximumSyncedAnalysisPromptLength + 1)

    XCTAssertNil(
      SettingsSyncManager.promptForSync(
        customPrompt,
        assistantName: "task",
        maximumLength: TaskAssistantSettings.maximumSyncedAnalysisPromptLength))
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
        prompt, assistantName: "insight", maximumLength: 10_000))
  }

  @MainActor
  func testEachAssistantPromptUsesItsBackendBound() {
    let legacyMaximum = 10_000
    let prompt = String(repeating: "x", count: legacyMaximum + 1)

    XCTAssertNotNil(
      SettingsSyncManager.promptForSync(
        prompt,
        assistantName: "task",
        maximumLength: TaskAssistantSettings.maximumSyncedAnalysisPromptLength))
    XCTAssertNil(
      SettingsSyncManager.promptForSync(
        prompt, assistantName: "insight", maximumLength: legacyMaximum))
    XCTAssertNil(
      SettingsSyncManager.promptForSync(
        prompt, assistantName: "memory", maximumLength: legacyMaximum))
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
