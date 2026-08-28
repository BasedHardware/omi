import XCTest

@testable import Omi_Computer

final class JITProactivityPolicyTests: XCTestCase {
  private let enabledFlags = JITProactivityFlags(rollout: .enabled, killSwitch: .disabled)

  func testPlannedStandingTriggerWinsOverAmbientCandidate() {
    let decision = JITProactivityPolicy.decide(
      flags: enabledFlags,
      planned: [
        JITPlannedTriggerCandidate(
          id: "trigger-1",
          continuityKey: "task:1",
          matched: true,
          standingIntent: true,
          wakeupsRemaining: 1
        )
      ],
      ambient: [ambient(id: "ambient-1", key: "ambient:1")]
    )

    XCTAssertEqual(decision, .deliver(lane: .planned, id: "trigger-1", continuityKey: "task:1"))
  }

  func testAmbientRequiresMaterialChangeNoveltyRelevanceNanoApprovalAndOneTurn() {
    let base = ambient(id: "ambient", key: "ambient")
    let failures = [
      JITAmbientContextCandidate(
        id: base.id,
        continuityKey: base.continuityKey,
        materialChange: false,
        locallyNovel: true,
        locallyRelevant: true,
        nanoTriage: .approved,
        fullAgentTurnsRemaining: 1
      ),
      JITAmbientContextCandidate(
        id: base.id,
        continuityKey: base.continuityKey,
        materialChange: true,
        locallyNovel: false,
        locallyRelevant: true,
        nanoTriage: .approved,
        fullAgentTurnsRemaining: 1
      ),
      JITAmbientContextCandidate(
        id: base.id,
        continuityKey: base.continuityKey,
        materialChange: true,
        locallyNovel: true,
        locallyRelevant: false,
        nanoTriage: .approved,
        fullAgentTurnsRemaining: 1
      ),
      JITAmbientContextCandidate(
        id: base.id,
        continuityKey: base.continuityKey,
        materialChange: true,
        locallyNovel: true,
        locallyRelevant: true,
        nanoTriage: .unknown,
        fullAgentTurnsRemaining: 1
      ),
      JITAmbientContextCandidate(
        id: base.id,
        continuityKey: base.continuityKey,
        materialChange: true,
        locallyNovel: true,
        locallyRelevant: true,
        nanoTriage: .approved,
        fullAgentTurnsRemaining: 0
      ),
    ]

    XCTAssertEqual(
      JITProactivityPolicy.decide(flags: enabledFlags, planned: [], ambient: failures),
      .suppressed(reason: "no_eligible_candidate")
    )

    XCTAssertEqual(
      JITProactivityPolicy.decide(flags: enabledFlags, planned: [], ambient: [base]),
      .deliver(lane: .ambient, id: "ambient", continuityKey: "ambient")
    )
  }

  func testUnknownOrDisabledFlagsKeepLegacyContextBucketsAndNeverActivateNewLane() {
    let candidates = [ambient(id: "ambient", key: "ambient")]
    for flags in [
      JITProactivityFlags(rollout: .disabled, killSwitch: .disabled),
      JITProactivityFlags(rollout: .unknown, killSwitch: .disabled),
      JITProactivityFlags(rollout: .enabled, killSwitch: .unknown),
      JITProactivityFlags(rollout: .enabled, killSwitch: .enabled),
    ] {
      guard
        case .legacyContextBucketFallback = JITProactivityPolicy.decide(
          flags: flags,
          planned: [],
          ambient: candidates
        )
      else {
        return XCTFail("new lane must fail closed for \(flags)")
      }
    }
  }

  func testPlannedAndAmbientContinuityKeysShareDeliveryDedup() {
    let decision = JITProactivityPolicy.decide(
      flags: enabledFlags,
      planned: [
        JITPlannedTriggerCandidate(
          id: "planned",
          continuityKey: "same-work",
          matched: true,
          standingIntent: true,
          wakeupsRemaining: 1
        )
      ],
      ambient: [ambient(id: "ambient", key: "same-work")],
      deliveredContinuityKeys: ["same-work"]
    )

    XCTAssertEqual(decision, .suppressed(reason: "no_eligible_candidate"))
  }

  func testDeterministicOrderingAndAtMostOneFullTurn() {
    let decision = JITProactivityPolicy.decide(
      flags: enabledFlags,
      planned: [
        JITPlannedTriggerCandidate(
          id: "z-trigger",
          continuityKey: "z-key",
          matched: true,
          standingIntent: true,
          wakeupsRemaining: 1
        ),
        JITPlannedTriggerCandidate(
          id: "a-trigger",
          continuityKey: "a-key",
          matched: true,
          standingIntent: true,
          wakeupsRemaining: 1
        ),
      ],
      ambient: []
    )

    XCTAssertEqual(decision, .deliver(lane: .planned, id: "a-trigger", continuityKey: "a-key"))
  }

  private func ambient(id: String, key: String) -> JITAmbientContextCandidate {
    JITAmbientContextCandidate(
      id: id,
      continuityKey: key,
      materialChange: true,
      locallyNovel: true,
      locallyRelevant: true,
      nanoTriage: .approved,
      fullAgentTurnsRemaining: 1
    )
  }
}
