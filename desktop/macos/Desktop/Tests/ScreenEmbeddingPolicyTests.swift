import Foundation
import XCTest

@testable import Omi_Computer

final class ScreenEmbeddingPolicyTests: XCTestCase {
  override func setUp() {
    super.setUp()
    ScreenEmbeddingRouteRecorder.shared.resetForTesting()
  }

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

  func testRouteTelemetrySurvivesTheSharedDiagnosticsEnvelope() throws {
    let decisions = [
      ScreenEmbeddingPolicy(
        plan: .basic, status: .active, localRoute: .engine(HashEmbeddingEngine()), killSwitches: .enabled),
      ScreenEmbeddingPolicy(plan: nil, status: nil, localRoute: .none, killSwitches: .enabled),
      ScreenEmbeddingPolicy(plan: .operator, status: .active, localRoute: .none, killSwitches: .enabled),
      ScreenEmbeddingPolicy(
        plan: .unknown("synthetic-unknown-plan"), status: nil, localRoute: .none,
        killSwitches: LocalEmbeddingKillSwitches(isDisabled: true, forcedEngineRaw: nil)),
    ]
    let diagnostics = DesktopDiagnosticsManager.shared
    for decision in decisions {
      let before = diagnostics.currentSnapshotsForSentry().filter {
        $0["route_event"] as? String == "screen_embedding_route"
      }.count
      decision.recordRoute()
      let events = diagnostics.currentSnapshotsForSentry().filter {
        $0["route_event"] as? String == "screen_embedding_route"
      }
      XCTAssertEqual(events.count, before + 1)
      let event = try XCTUnwrap(events.last)
      XCTAssertEqual(event["event"] as? String, "fallback_triggered")
      XCTAssertEqual(event["plan_class"] as? String, decision.planClass.rawValue)
      XCTAssertEqual(
        event["route"] as? String, decision.reason == .hardKill ? "disabled" : decision.searchRoute.rawValue)
      XCTAssertEqual(event["route_reason"] as? String, decision.reason.rawValue)
      XCTAssertEqual(event["reason"] as? String, decision.reason == .hardKill ? "dispatch_disabled" : "policy")
      XCTAssertFalse(event.values.contains { ($0 as? String) == "synthetic-unknown-plan" })
      XCTAssertNil(event["ocr_text"])
      XCTAssertNil(event["query"])
    }
  }

  func testRouteTelemetryEmitsOncePerDecisionThenAgainOnPlanChange() {
    let diagnostics = DesktopDiagnosticsManager.shared
    diagnostics.resetForTests()
    let free = ScreenEmbeddingPolicy(
      plan: .basic, status: .active, localRoute: .engine(HashEmbeddingEngine()), killSwitches: .enabled)
    for _ in 0..<100 { free.recordRoute() }
    let freeEvents = diagnostics.currentSnapshotsForSentry().filter {
      $0["route_event"] as? String == "screen_embedding_route"
    }
    XCTAssertEqual(freeEvents.count, 1)
    let paid = ScreenEmbeddingPolicy(
      plan: .operator, status: .active, localRoute: .engine(HashEmbeddingEngine()), killSwitches: .enabled)
    paid.recordRoute()
    let events = diagnostics.currentSnapshotsForSentry().filter {
      $0["route_event"] as? String == "screen_embedding_route"
    }
    XCTAssertEqual(events.count, 2)
    XCTAssertEqual(events.last?["plan_class"] as? String, "paid")
  }

  func testRouteTelemetryHeartbeatReemitsTheSameDecisionAfterAnHour() {
    let diagnostics = DesktopDiagnosticsManager.shared
    diagnostics.resetForTests()
    let box = DateBox(Date(timeIntervalSince1970: 1_800_000_000))
    ScreenEmbeddingRouteRecorder.shared.resetForTesting { box.now }
    let decision = ScreenEmbeddingPolicy(
      plan: .basic, status: .active, localRoute: .engine(HashEmbeddingEngine()), killSwitches: .enabled)
    decision.recordRoute()
    decision.recordRoute()
    XCTAssertEqual(
      diagnostics.currentSnapshotsForSentry().filter { $0["route_event"] as? String == "screen_embedding_route" }
        .count, 1)
    box.now.addTimeInterval(ScreenEmbeddingRouteRecorder.heartbeat)
    decision.recordRoute()
    XCTAssertEqual(
      diagnostics.currentSnapshotsForSentry().filter { $0["route_event"] as? String == "screen_embedding_route" }
        .count, 2)
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

private final class DateBox: @unchecked Sendable {
  var now: Date
  init(_ now: Date) { self.now = now }
}
