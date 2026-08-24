import XCTest

@testable import Omi_Computer

final class JITProactivityRuntimeTests: XCTestCase {
  private func snapshot() throws -> RuntimeOwnerAuthorizationSnapshot {
    let authority = RuntimeOwnerAuthorizationAuthority()
    authority.endTransition(ownerID: "owner")
    return try XCTUnwrap(authority.capture(ownerID: "owner", expectedOwnerID: "owner"))
  }

  func testUnknownAuthorityPreservesLegacyLane() async throws {
    let runtime = JITProactivityRuntime { _ in
      JITProactivityFlags(rollout: .unknown, killSwitch: .unknown)
    }

    let decision = await runtime.admission(authorizationSnapshot: try snapshot())

    XCTAssertEqual(decision, .legacyContextBucketFallback(reason: "rollout_unknown"))
  }

  func testRolloutWireStatesFailClosed() {
    XCTAssertEqual(ProactiveLaneClient.jitState("on"), .enabled)
    XCTAssertEqual(ProactiveLaneClient.jitState("off"), .disabled)
    XCTAssertEqual(ProactiveLaneClient.jitState("future"), .unknown)
    XCTAssertEqual(ProactiveLaneClient.jitState(nil), .unknown)
  }

  func testEnabledAuthorityStillPreservesLegacyUntilDurableActionContractExists() async throws {
    let runtime = JITProactivityRuntime { _ in
      JITProactivityFlags(rollout: .enabled, killSwitch: .disabled)
    }

    let decision = await runtime.admission(authorizationSnapshot: try snapshot())

    XCTAssertEqual(
      decision,
      .legacyContextBucketFallback(reason: "authoritative_trigger_action_unavailable"))
  }
}
