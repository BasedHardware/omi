#if DEBUG
  import XCTest

  @testable import Omi_Computer

  final class ProactiveCaptureStatusSnapshotTests: XCTestCase {
    @MainActor
    func testIdleBucketUsesOnlyCoarseThresholds() {
      XCTAssertEqual(ProactiveAssistantsPlugin.automationSystemIdleBucket(for: -1), "unknown")
      XCTAssertEqual(ProactiveAssistantsPlugin.automationSystemIdleBucket(for: .nan), "unknown")
      XCTAssertEqual(ProactiveAssistantsPlugin.automationSystemIdleBucket(for: 0), "active")
      XCTAssertEqual(ProactiveAssistantsPlugin.automationSystemIdleBucket(for: 2.99), "active")
      XCTAssertEqual(ProactiveAssistantsPlugin.automationSystemIdleBucket(for: 3), "recent")
      XCTAssertEqual(ProactiveAssistantsPlugin.automationSystemIdleBucket(for: 14.99), "recent")
      XCTAssertEqual(ProactiveAssistantsPlugin.automationSystemIdleBucket(for: 15), "settling")
      XCTAssertEqual(ProactiveAssistantsPlugin.automationSystemIdleBucket(for: 59.99), "settling")
      XCTAssertEqual(ProactiveAssistantsPlugin.automationSystemIdleBucket(for: 60), "idle")
    }

    @MainActor
    func testBridgeActionReturnsPrivacySafeCaptureStatusContract() async throws {
      let registry = DesktopAutomationActionRegistry.shared
      registry.registerBuiltins()

      let descriptor = try XCTUnwrap(
        registry.descriptors().first { $0.name == "proactive_capture_status_snapshot" })
      XCTAssertEqual(descriptor.category, "read")
      XCTAssertEqual(descriptor.safety, "read_only")
      XCTAssertTrue(descriptor.sideEffects.contains { $0.contains("does not capture") })
      XCTAssertTrue(descriptor.sideEffects.contains { $0.contains("app names") })
      XCTAssertEqual(descriptor.params, [])

      let result = try await registry.perform("proactive_capture_status_snapshot", params: [:])
      let detail = try XCTUnwrap(result)
      XCTAssertEqual(
        Set(detail.keys),
        Set([
          "is_monitoring",
          "has_screen_recording_permission",
          "screen_analysis_enabled",
          "context_buckets_enabled",
          "capture_health",
          "capture_gate",
          "system_idle_bucket",
          "current_app_excluded",
        ]))
      XCTAssertTrue(detail["current_app_excluded"].map { ["true", "false", "unknown"].contains($0) } ?? false)
      XCTAssertTrue(detail["context_buckets_enabled"].map { ["true", "false"].contains($0) } ?? false)
      XCTAssertTrue(
        detail["system_idle_bucket"].map {
          ["active", "recent", "settling", "idle", "unknown"].contains($0)
        } ?? false)
      XCTAssertFalse(detail.keys.contains { $0.contains("app") && $0 != "current_app_excluded" })
      XCTAssertFalse(
        detail.keys.contains {
          $0.contains("window") || $0.contains("title") || $0.contains("idle_seconds")
        })
    }
  }
#endif
