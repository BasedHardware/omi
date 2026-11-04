import XCTest

@testable import Omi_Computer

final class OmiFlagStoreTests: XCTestCase {
  func testUnlistedKeysFallBackToPostHog() {
    let store = OmiFlagStore()
    store.apply([OmiFlag(key: "screen_task_jev_gate", enabled: false)], generation: 0)
    XCTAssertNil(store.value("desktop-plan-storefront"))
    XCTAssertEqual(store.value("screen_task_jev_gate") as? Bool, false)
  }

  func testVariantAndPayloadOnlyWhenEnabled() {
    let store = OmiFlagStore()
    store.apply(
      [
        OmiFlag(key: "on", enabled: true, variant: "b", payloadJson: "{\"a\":1}"),
        OmiFlag(key: "off", enabled: false, variant: "b", payloadJson: "{\"a\":1}"),
      ], generation: 0)
    XCTAssertEqual(store.value("on") as? String, "b")
    XCTAssertEqual((store.payload("on") as? [String: Int])?["a"], 1)
    XCTAssertEqual(store.value("off") as? Bool, false)
    XCTAssertNil(store.payload("off"))
  }

  func testAccountResetDropsAnswersAndRejectsAStaleFetch() {
    let store = OmiFlagStore()
    let before = store.currentGeneration
    store.apply([OmiFlag(key: "k", enabled: true)], generation: before)
    store.reset()
    XCTAssertNil(store.flag("k"))
    XCTAssertFalse(store.apply([OmiFlag(key: "k", enabled: true)], generation: before))
    XCTAssertNil(store.flag("k"))
  }

  func testApplyReportsChangesOnly() {
    let store = OmiFlagStore()
    let flags = [OmiFlag(key: "k", enabled: true)]
    XCTAssertTrue(store.apply(flags, generation: 0))
    XCTAssertFalse(store.apply(flags, generation: 0))
  }
}
