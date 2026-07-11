import XCTest

@testable import Omi_Computer

@MainActor
final class AssistantSettingsVocabularyTests: XCTestCase {
  func testVocabularyHydrationGuardRejectsResponseStartedBeforeLocalMutation() {
    let settings = AssistantSettings.shared
    let original = settings.transcriptionVocabulary
    defer { settings.transcriptionVocabulary = original }

    let revisionAtLoadStart = settings.transcriptionVocabularyRevision
    XCTAssertTrue(
      settings.shouldApplyTranscriptionVocabularyHydration(
        startedAtRevision: revisionAtLoadStart
      )
    )

    settings.transcriptionVocabulary = ["[[MARKER:vocabulary-race]]"]

    XCTAssertFalse(
      settings.shouldApplyTranscriptionVocabularyHydration(
        startedAtRevision: revisionAtLoadStart
      )
    )
  }
}
