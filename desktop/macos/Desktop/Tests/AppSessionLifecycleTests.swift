import XCTest

@testable import Omi_Computer

final class AppSessionLifecycleTests: XCTestCase {
  func testColdLaunchEmitsExactlyOneSession() {
    let lifecycle = AppSessionLifecycle(makeID: { "cold-session" })

    XCTAssertEqual(
      lifecycle.appLaunched(),
      AppSessionStart(id: "cold-session", kind: .coldStart)
    )
    XCTAssertNil(lifecycle.appLaunched())
    XCTAssertNil(lifecycle.appBecameActive())
  }

  func testForegroundResumeRequiresAnInactiveTransition() {
    var ids = ["cold-session", "resume-session"].makeIterator()
    let lifecycle = AppSessionLifecycle(makeID: {
      guard let id = ids.next() else {
        XCTFail("session ID generator exhausted")
        return "unexpected-session"
      }
      return id
    })

    _ = lifecycle.appLaunched()
    lifecycle.appResignedActive()

    XCTAssertEqual(
      lifecycle.appBecameActive(),
      AppSessionStart(id: "resume-session", kind: .foregroundResume)
    )
    XCTAssertNil(lifecycle.appBecameActive())
  }
}
