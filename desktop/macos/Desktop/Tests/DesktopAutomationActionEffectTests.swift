import XCTest

@testable import Omi_Computer

@MainActor
final class DesktopAutomationActionEffectTests: XCTestCase {
  func testDiscoveryUsesEffectsEvenWhenTheNameLooksReadOnly() throws {
    let descriptor = DesktopAutomationActionDescriptor(
      name: "memory_import_state_probe",
      effects: [.remoteWrite, .networkOrModel, .localState],
      summary: "Exercise a writer",
      sideEffects: ["Custom detail supplements the mandatory descriptions"]
    )
    let json = try XCTUnwrap(
      JSONSerialization.jsonObject(with: JSONEncoder().encode(descriptor)) as? [String: Any])
    XCTAssertEqual(json["safety"] as? String, "remote_write")
    XCTAssertEqual(json["category"] as? String, "write")
    XCTAssertEqual(
      json["effects"] as? [String], ["local_ui_state", "network_or_model", "remote_write"])
    XCTAssertEqual(
      descriptor.sideEffects,
      descriptor.effects.map(\.description) + ["Custom detail supplements the mandatory descriptions"])
  }

  func testReadOnlyDispatchRejectsEveryDeclaredEffectBeforeCallingHandler() async throws {
    let registry = DesktopAutomationActionRegistry()
    var mutations = 0
    for effect in DesktopAutomationActionEffect.allCases {
      registry.register(
        name: "harmless_state_probe", effects: [effect], summary: "A deliberately misleading name"
      ) { _ in
        mutations += 1
        return nil
      }
      do {
        _ = try await registry.perform("harmless_state_probe", params: [:], readOnly: true)
        XCTFail("Read-only dispatch must reject \(effect)")
      } catch DesktopAutomationActionError.requiresEffects(let name) {
        XCTAssertEqual(name, "harmless_state_probe")
      }
      XCTAssertEqual(mutations, 0)
    }
    // Ordinary action execution still reaches the handler.
    _ = try await registry.perform("harmless_state_probe", params: [:])
    XCTAssertEqual(mutations, 1)
  }

  func testReadOnlyDispatchPreservesReadResultAndUnknownActionError() async throws {
    let registry = DesktopAutomationActionRegistry()
    registry.register(name: "snapshot", effects: [], summary: "Read injected state") { params in
      ["value": params["value"] ?? ""]
    }
    let result = try await registry.perform("snapshot", params: ["value": "stable"], readOnly: true)
    XCTAssertEqual(result, ["value": "stable"])
    do {
      _ = try await registry.perform("missing", params: [:], readOnly: true)
      XCTFail("Unknown actions must fail")
    } catch DesktopAutomationActionError.unknownAction(let name) {
      XCTAssertEqual(name, "missing")
    }
  }

  func testHistoricalWritersAndLoadingSnapshotsCannotRunAsReadOnly() async throws {
    let registry = DesktopAutomationActionRegistry()
    registry.registerBuiltins()
    for action in [
      "memory_log_import_probe", "clear_owner_surface_state", "memories_snapshot",
      "conversation_list_snapshot", "screen_frame_quick_look_probe",
      "permissions_snapshot", "coordinator_awareness_snapshot", "coordinator_inspect_run",
      "coordinator_action_queue", "coordinator_open_loops", "agent_lifecycle_convergence_snapshot",
      "recent_screen_frames_snapshot", "kernel_turn_tail", "integration_nudge_evaluate", "rating_prompt_state",
    ] {
      do {
        // No params: a wrongly admitted handler would run or fail parameter validation.
        _ = try await registry.perform(action, params: [:], readOnly: true)
        XCTFail("\(action) must require its declared effects")
      } catch DesktopAutomationActionError.requiresEffects(let name) {
        XCTAssertEqual(name, action)
      }
    }
  }
}
