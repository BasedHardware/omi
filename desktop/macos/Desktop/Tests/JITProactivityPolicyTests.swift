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

  /// The backend computes admission itself (`effective`); the client must not
  /// re-derive a stricter verdict from the raw flags it also happens to carry.
  func testEffectiveEnabledAdmitsEvenWhenRawFlagsAreNotAKnownGoodPair() {
    let candidates = [ambient(id: "ambient", key: "ambient")]
    for flags in [
      JITProactivityFlags(
        rollout: .unknown, killSwitch: .unknown, effective: .enabled),
      JITProactivityFlags(
        rollout: .enabled, killSwitch: .unknown, effective: .enabled),
      // Older servers omit `kill_switch` entirely; absence is not unknown-off.
      JITProactivityFlags(
        rollout: .unknown, killSwitch: .unknown, effective: .enabled, killSwitchPresent: false),
      JITProactivityFlags(
        rollout: .enabled, killSwitch: .unknown, effective: .enabled, killSwitchPresent: false),
      // The legacy pair still admits when `effective` is absent.
      JITProactivityFlags(
        rollout: .enabled, killSwitch: .disabled, effective: .unknown, killSwitchPresent: false),
    ] {
      XCTAssertEqual(
        JITProactivityPolicy.decide(flags: flags, planned: [], ambient: candidates),
        .deliver(lane: .ambient, id: "ambient", continuityKey: "ambient"),
        "effective authority must admit: \(flags)")
    }
  }

  func testEffectiveDisabledBlocksEvenWhenTheRawPairWouldAdmit() {
    let flags = JITProactivityFlags(
      rollout: .enabled, killSwitch: .disabled, effective: .disabled)

    guard
      case .legacyContextBucketFallback(let reason) = JITProactivityPolicy.decide(
        flags: flags, planned: [], ambient: [ambient(id: "ambient", key: "ambient")])
    else {
      return XCTFail("server-disabled effective must fail closed")
    }
    XCTAssertEqual(reason, "rollout_disabled")
  }

  /// A `kill_switch` the server actually sent as `unknown` still fails closed;
  /// only a missing field stops being an unknown-off veto.
  func testPresentUnknownKillSwitchStillFailsClosedWithoutEffective() {
    let flags = JITProactivityFlags(
      rollout: .enabled, killSwitch: .unknown, effective: .unknown, killSwitchPresent: true)

    XCTAssertFalse(flags.permitsNewLane)
    guard
      case .legacyContextBucketFallback(let reason) = JITProactivityPolicy.decide(
        flags: flags, planned: [], ambient: [])
    else {
      return XCTFail("present unknown must fail closed")
    }
    XCTAssertEqual(reason, "rollout_unknown")
  }

  func testAbsentKillSwitchWithEnabledRolloutAdmitsViaLegacyFallback() {
    let flags = JITProactivityFlags(
      rollout: .enabled, killSwitch: .unknown, effective: .unknown, killSwitchPresent: false)

    XCTAssertTrue(flags.permitsNewLane)
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
