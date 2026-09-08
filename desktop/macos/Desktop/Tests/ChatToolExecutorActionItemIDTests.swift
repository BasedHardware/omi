import XCTest

@testable import Omi_Computer

/// Regression coverage for `ChatToolExecutor.resolveActionItemID`. Realtime-voice
/// advertises the `update_action_item` id param as `id` (schemaOverride in
/// omi-tool-manifest.ts), while chat/pi-mono/stdio advertise `action_item_id`.
/// The executor previously read only `action_item_id`, so every voice update
/// hard-failed with "action_item_id is required". The resolver accepts either.
final class ChatToolExecutorActionItemIDTests: XCTestCase {

  func testResolvesCanonicalActionItemID() {
    XCTAssertEqual(ChatToolExecutor.resolveActionItemID(["action_item_id": "abc"]), "abc")
  }

  func testResolvesRealtimeVoiceIDKey() {
    // The exact defect: voice sends `id`, not `action_item_id`.
    XCTAssertEqual(ChatToolExecutor.resolveActionItemID(["id": "voice-123"]), "voice-123")
  }

  func testCanonicalKeyWinsWhenBothPresent() {
    XCTAssertEqual(
      ChatToolExecutor.resolveActionItemID(["action_item_id": "canon", "id": "other"]), "canon")
  }

  func testReturnsNilForMissingEmptyOrNonString() {
    XCTAssertNil(ChatToolExecutor.resolveActionItemID([:]))
    XCTAssertNil(ChatToolExecutor.resolveActionItemID(["action_item_id": ""]))
    XCTAssertNil(ChatToolExecutor.resolveActionItemID(["id": ""]))
    XCTAssertNil(ChatToolExecutor.resolveActionItemID(["action_item_id": 42]))
  }
}
