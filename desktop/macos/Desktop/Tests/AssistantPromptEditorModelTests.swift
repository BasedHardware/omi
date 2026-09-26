import XCTest

@testable import Omi_Computer

/// The three proactive-assistant prompt editors share one draft model: edits stay local until Save,
/// Cancel discards them, and Reset clears the stored prompt rather than re-storing the default.
@MainActor
final class AssistantPromptEditorModelTests: XCTestCase {
  /// A store the test owns, recording what the editor wrote.
  private final class FakeStore {
    var stored: String?
    var saves: [String] = []
    var resets = 0
    let defaultPrompt = "default prompt"

    var current: String { stored ?? defaultPrompt }

    @MainActor
    var store: AssistantPromptStore {
      AssistantPromptStore(
        title: "Test Prompt", subtitle: "", noun: "test", defaultPrompt: defaultPrompt,
        load: { self.current },
        save: { value in
          self.saves.append(value)
          self.stored = value
        },
        reset: {
          self.resets += 1
          self.stored = nil
        })
    }
  }

  func testTypingDoesNotWriteUntilSave() {
    let fake = FakeStore()
    fake.stored = "custom"
    let model = AssistantPromptEditorModel(store: fake.store)

    model.draft = "custom, edited"

    XCTAssertTrue(model.hasChanges)
    XCTAssertEqual(fake.saves, [], "a keystroke must not commit the prompt")
    XCTAssertEqual(fake.current, "custom")

    XCTAssertTrue(model.save())
    XCTAssertEqual(fake.saves, ["custom, edited"])
    XCTAssertFalse(model.hasChanges)
  }

  func testCancellingLeavesTheStoredPromptUntouched() {
    let fake = FakeStore()
    fake.stored = "custom"
    let model = AssistantPromptEditorModel(store: fake.store)

    model.draft = "discard me"
    // Cancel closes the window without calling save; a new editor reads the store afresh.
    let reopened = AssistantPromptEditorModel(store: fake.store)

    XCTAssertEqual(reopened.draft, "custom")
    XCTAssertFalse(reopened.hasChanges)
    XCTAssertEqual(fake.saves, [])
  }

  func testSaveWithNoChangesWritesNothing() {
    let fake = FakeStore()
    let model = AssistantPromptEditorModel(store: fake.store)

    XCTAssertFalse(model.save())
    XCTAssertEqual(fake.saves, [])
  }

  func testResetClearsTheStoreAndDiscardsTheDraft() {
    let fake = FakeStore()
    fake.stored = "custom"
    let model = AssistantPromptEditorModel(store: fake.store)
    model.draft = "unsaved edit"

    model.resetToDefault()

    XCTAssertEqual(fake.resets, 1)
    XCTAssertNil(fake.stored, "reset clears the stored prompt")
    XCTAssertEqual(fake.saves, [], "reset must not re-store the default as the user's own prompt")
    XCTAssertEqual(model.draft, fake.defaultPrompt)
    XCTAssertFalse(model.hasChanges)
  }

  func testTheRealStoresRouteToTheirOwnAssistant() {
    XCTAssertEqual(AssistantPromptStore.insight.defaultPrompt, InsightAssistantSettings.defaultAnalysisPrompt)
    XCTAssertEqual(AssistantPromptStore.task.defaultPrompt, TaskAssistantSettings.defaultAnalysisPrompt)
    XCTAssertEqual(AssistantPromptStore.memory.defaultPrompt, MemoryAssistantSettings.defaultAnalysisPrompt)
    XCTAssertEqual(
      Set([AssistantPromptStore.insight.title, AssistantPromptStore.task.title, AssistantPromptStore.memory.title])
        .count, 3)
  }
}
