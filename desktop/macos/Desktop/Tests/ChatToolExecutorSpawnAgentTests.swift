import XCTest

@testable import Omi_Computer

final class ChatToolExecutorSpawnAgentTests: XCTestCase {
  func testDirectPermissionToolsRemainCanonicalPhysicalExecutors() {
    XCTAssertEqual(
      GeneratedToolExecutors.chatDispatch(for: "check_permission_status"),
      .checkPermissionStatus)
    XCTAssertEqual(
      GeneratedToolExecutors.chatDispatch(for: "request_permission"),
      .requestPermission)
  }

  func testSpawnAgentHasNoDormantSwiftExecutionPath() {
    XCTAssertNil(GeneratedToolExecutors.resolve("spawn_agent"))
    XCTAssertEqual(GeneratedToolExecutors.chatDispatch(for: "spawn_agent"), .unhandled)
  }
}
