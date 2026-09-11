import Foundation
import XCTest

@testable import Omi_Computer

final class ScreenEmbeddingPolicyTests: XCTestCase {
  func testEntitlementAndEngineMatrix() {
    let plans: [SubscriptionPlanType?] = [
      nil, .unknown("future"), .basic, .plus, .unlimited, .unlimitedV2, .pro, .operator, .architect,
    ]
    let statuses: [SubscriptionStatusType?] = [nil, .inactive, .active]
    let selections: [LocalEmbeddingRuntime.Selection] = [.none, .disabled, .engine(HashEmbeddingEngine())]
    for plan in plans {
      for status in statuses {
        for selection in selections {
          for enabled in [false, true] {
            for hardKill in [false, true] {
              let flags = LocalEmbeddingKillSwitches(
                isDisabled: hardKill, isEnabled: enabled, forcedEngineRaw: nil)
              let policy = ScreenEmbeddingPolicy(
                plan: plan, status: status, localRoute: selection, killSwitches: flags)
              let paid = plan?.hasPaidCapability == true && status == .active
              let available: Bool
              if case .engine = selection { available = enabled && !hardKill } else { available = false }
              XCTAssertEqual(policy.shouldEmbedWithGemini, hardKill || paid)
              XCTAssertEqual(policy.shouldIndexLocally, available)
              XCTAssertEqual(policy.searchRoute, hardKill ? .gemini : available ? .local : paid ? .gemini : .ftsOnly)
              if plan == nil || plan == .unknown("future") {
                XCTAssertEqual(policy.planClass, .unknown)
              } else {
                XCTAssertEqual(policy.planClass, paid ? .paid : .free)
              }
            }
          }
        }
      }
    }
  }

  func testCachedEntitlementAndDefaultLadder() throws {
    let name = "screen-embedding-policy-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
    defer { defaults.removePersistentDomain(forName: name) }
    for raw in [nil, "basic", "future", "operator"] as [String?] {
      if let raw {
        defaults.set(raw, forKey: .floatingBarCachedPlan)
      } else {
        defaults.removeObject(forKey: .floatingBarCachedPlan)
      }
      for nonProduction in [false, true] {
        let flags = LocalEmbeddingKillSwitches.resolve(
          environment: [:], defaults: defaults, isNonProduction: nonProduction)
        XCTAssertEqual(flags.isEnabled, nonProduction || raw != "operator")
        let policy = ScreenEmbeddingPolicy.cached(killSwitches: flags, defaults: defaults)
        XCTAssertEqual(policy.shouldEmbedWithGemini, raw == "operator")
        for optOut in ["0", "false", "off"] {
          let disabled = LocalEmbeddingKillSwitches.resolve(
            environment: ["OMI_LOCAL_EMBEDDINGS": optOut], defaults: defaults, isNonProduction: nonProduction)
          XCTAssertFalse(disabled.isEnabled)
        }
      }
    }
    defaults.set(true, forKey: .localEmbeddingsEnabled)
    XCTAssertTrue(
      LocalEmbeddingKillSwitches.resolve(environment: [:], defaults: defaults, isNonProduction: false).isEnabled)
    defaults.set(false, forKey: .localEmbeddingsEnabled)
    XCTAssertFalse(
      LocalEmbeddingKillSwitches.resolve(environment: [:], defaults: defaults, isNonProduction: true).isEnabled)
    XCTAssertTrue(
      LocalEmbeddingKillSwitches.resolve(
        environment: ["OMI_LOCAL_EMBEDDINGS": "1"], defaults: defaults, isNonProduction: false
      ).isEnabled)
  }
}
