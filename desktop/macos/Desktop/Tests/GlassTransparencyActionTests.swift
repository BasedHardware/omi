import OmiTheme
import XCTest

@testable import Omi_Computer

/// The bridge actions a harness uses to drive the Settings → General transparency slider without
/// cursor input. They run through the real registry and write the same published value the slider
/// binds to, so a pass here means the live path a drag takes is reachable in-process.
@MainActor
final class GlassTransparencyActionTests: XCTestCase {

  private var registry: DesktopAutomationActionRegistry { .shared }

  /// Registers the builtins and hands back a restore for the shared value the actions mutate, so a
  /// test leaves the process's own preference exactly as it found it.
  private func prepare() -> () -> Void {
    registry.registerBuiltins()
    let original = InkGlassTransparencySettings.shared.transparency
    return { InkGlassTransparencySettings.shared.transparency = original }
  }

  func testActionsAreDiscoverable() {
    let restore = prepare()
    defer { restore() }
    let names = Set(registry.descriptors().map(\.name))
    XCTAssertTrue(names.contains("glass_transparency_snapshot"))
    XCTAssertTrue(names.contains("set_glass_transparency"))
  }

  func testSetWritesTheSlidersValueAndSnapshotReadsItBack() async throws {
    let restore = prepare()
    defer { restore() }
    let set = try await registry.perform("set_glass_transparency", params: ["value": "0.3"])
    XCTAssertEqual(set?["transparency"], "0.3000")
    XCTAssertEqual(set?["is_default"], "false")
    XCTAssertEqual(InkGlassTransparencySettings.shared.transparency, 0.3, accuracy: 0.0001)

    let snapshot = try await registry.perform("glass_transparency_snapshot", params: [:])
    XCTAssertEqual(snapshot?["transparency"], "0.3000")
    let alpha = try XCTUnwrap(snapshot?["ground_alpha"].flatMap(Double.init))
    if snapshot?["reduce_transparency"] == "true" {
      XCTAssertEqual(alpha, 1, accuracy: 0.0001, "Reduce Transparency wins over the slider")
    } else {
      XCTAssertEqual(alpha, 0.7, accuracy: 0.0001, "ground alpha is 1 − transparency")
    }
  }

  func testSetClampsAndRejectsNonNumbers() async throws {
    let restore = prepare()
    defer { restore() }
    let high = try await registry.perform("set_glass_transparency", params: ["value": "7"])
    XCTAssertEqual(high?["transparency"], "1.0000")

    do {
      _ = try await registry.perform("set_glass_transparency", params: ["value": "clear"])
      XCTFail("a non-numeric value must be rejected, not silently ignored")
    } catch DesktopAutomationActionError.invalidParams {
      // expected
    }
  }
}
