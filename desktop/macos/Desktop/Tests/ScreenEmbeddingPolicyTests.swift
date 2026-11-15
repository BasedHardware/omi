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
              let cloud =
                status == .active && (plan == .operator || plan == .pro || plan == .architect || plan == .unlimitedV2)
              let available: Bool
              if case .engine = selection { available = enabled && !hardKill } else { available = false }
              XCTAssertEqual(policy.shouldEmbedWithGemini, cloud)
              XCTAssertEqual(policy.shouldIndexLocally, available)
              XCTAssertEqual(policy.searchRoute, available ? .local : cloud ? .gemini : .ftsOnly)
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

  func testNeoGrandfatherExpiryIsCheckedOnEveryRead() {
    let now = Date()
    for deadline in [now.timeIntervalSince1970 - 1, now.timeIntervalSince1970 + 1] {
      let policy = ScreenEmbeddingPolicy(
        plan: .unlimited, status: .active, localRoute: .none,
        killSwitches: .enabled, desktopGrandfatherUntil: deadline, now: now)
      XCTAssertEqual(policy.shouldEmbedWithGemini, deadline > now.timeIntervalSince1970)
    }
  }

  func testRouteTelemetryOnlyEmitsDecisionChanges() {
    let recorder = ScreenEmbeddingRouteRecorder()
    let free = ScreenEmbeddingPolicy(plan: .basic, status: .active, localRoute: .none, killSwitches: .enabled)
    let paid = ScreenEmbeddingPolicy(plan: .operator, status: .active, localRoute: .none, killSwitches: .enabled)
    XCTAssertTrue(recorder.shouldRecord(free))
    for _ in 0..<10_000 { XCTAssertFalse(recorder.shouldRecord(free)) }
    XCTAssertTrue(recorder.shouldRecord(paid))
    XCTAssertFalse(recorder.shouldRecord(paid))
  }

  func testCachedEntitlementAndDefaultLadder() throws {
    let name = "screen-embedding-policy-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
    defer { defaults.removePersistentDomain(forName: name) }
    let service = ScreenCloudEntitlementService(
      authority: EmbeddingOwnerAuthority(capture: { nil }, isCurrent: { _ in false }), observeAuthChanges: false,
      fetch: { _ in throw CancellationError() })
    for raw in [nil, "basic", "future", "operator"] as [String?] {
      if let raw {
        defaults.set(raw, forKey: .floatingBarCachedPlan)
      } else {
        defaults.removeObject(forKey: .floatingBarCachedPlan)
      }
      for nonProduction in [false, true] {
        let flags = LocalEmbeddingKillSwitches.resolve(
          environment: [:], defaults: defaults, isNonProduction: nonProduction)
        XCTAssertTrue(flags.isEnabled)
        let policy = ScreenEmbeddingPolicy.cached(killSwitches: flags, defaults: defaults, entitlementService: service)
        XCTAssertFalse(policy.shouldEmbedWithGemini, "persisted UI hint is never spend authority")
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

  func testProxyCapabilityAcrossLanesAndHardKill() {
    for lane in GeminiLane.allCases {
      for kill in [false, true] {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:1/v1/proxy/gemini")!)
        request.setValue("stale", forHTTPHeaderField: "X-Omi-Local-Embeddings")
        request.applyGeminiProxyHeaders(
          lane: lane, workload: .maintenance, authorization: "Bearer synthetic",
          localEmbeddings: LocalEmbeddingKillSwitches(isDisabled: kill, forcedEngineRaw: nil))
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Omi-Local-Embeddings"), kill ? nil : "1")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer synthetic")
      }
    }
  }
}
