import XCTest

@testable import Omi_Computer

final class AgentVMWarmupAdoptionTests: XCTestCase {
  func testWarmupAdoptsAReadyVMWithAnIP() {
    XCTAssertEqual(
      AgentVMService.warmupAction(status: "ready", ip: "203.0.113.10"),
      .adoptReady)
  }

  func testWarmupPollsAReadyVMUntilItHasAnIP() {
    XCTAssertEqual(
      AgentVMService.warmupAction(status: "ready", ip: nil),
      .pollUntilReady)
  }

  func testWarmupPollsProvisioningAndStoppedVMs() {
    XCTAssertEqual(
      AgentVMService.warmupAction(status: "provisioning", ip: nil),
      .pollUntilReady)
    XCTAssertEqual(
      AgentVMService.warmupAction(status: "stopped", ip: "203.0.113.10"),
      .pollUntilReady)
  }

  func testWarmupDoesNotCreateWhenStatusIsMissing() {
    XCTAssertEqual(
      AgentVMService.warmupAction(status: nil, ip: nil),
      .skip)
  }

  func testWarmupDoesNotCreateWhenStatusCheckFails() {
    XCTAssertEqual(
      AgentVMService.warmupAction(status: "ready", ip: "203.0.113.10", statusCheckFailed: true),
      .skip)
  }

  func testWarmupDoesNotCreateForUnrecognizedOrErrorStatus() {
    XCTAssertEqual(
      AgentVMService.warmupAction(status: "error", ip: nil),
      .skip)
    XCTAssertEqual(
      AgentVMService.warmupAction(status: "terminated", ip: nil),
      .skip)
  }

  func testStartPipelineStillCreatesWhileWarmupOnlyAdopts() {
    XCTAssertEqual(
      AgentVMService.warmupAction(status: nil, ip: nil),
      .skip,
      "launch warmup must not treat a missing VM as a create")
    XCTAssertNotEqual(
      AgentVMService.warmupAction(status: "ready", ip: "203.0.113.10"),
      .skip)
  }

  func testLaunchWarmupNeverCallsTheCreatePipeline() throws {
    let service = try sourceFile("AgentVMService.swift")
    let adoptBody = try XCTUnwrap(
      swiftFunctionBody(in: service, named: "ensureExistingOrProvision"),
      "ensureExistingOrProvision must remain the launch-warmup adopt path")
    XCTAssertFalse(
      adoptBody.contains("runPipeline"),
      "launch warmup must not fall through to runPipeline")
    XCTAssertFalse(
      adoptBody.contains("provisionAgentVM"),
      "launch warmup must not call provisionAgentVM")
    XCTAssertTrue(
      adoptBody.contains("warmupAction("),
      "launch warmup must decide adopt/skip through warmupAction")

    let ensureBody = try XCTUnwrap(swiftFunctionBody(in: service, named: "ensureProvisioned"))
    XCTAssertTrue(ensureBody.contains("checkExisting: true"))
    XCTAssertFalse(ensureBody.contains("checkExisting: false"))

    let startBody = try XCTUnwrap(swiftFunctionBody(in: service, named: "startPipeline"))
    XCTAssertTrue(
      startBody.contains("checkExisting: false"),
      "startPipeline must still create via the full pipeline")

    let ownerBound = try XCTUnwrap(swiftFunctionBody(in: service, named: "startOwnerBoundPipeline"))
    XCTAssertTrue(ownerBound.contains("await runPipeline("))
    XCTAssertTrue(ownerBound.contains("await ensureExistingOrProvision("))

    let home = try sourceFile("MainWindow/DesktopHomeView.swift")
    XCTAssertTrue(home.contains("AgentVMService.shared.ensureProvisioned()"))
    XCTAssertFalse(home.contains("AgentVMService.shared.startPipeline()"))

    let onboarding = try sourceFile("Onboarding/SecondBrain/SBOnboardingModel.swift")
    XCTAssertTrue(
      onboarding.contains("AgentVMService.shared.startPipeline()"),
      "onboarding must remain the explicit create path")
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    // omi-test-quality: source-inspection -- static contract: launch warmup must only adopt an existing VM; create stays on startPipeline
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func swiftFunctionBody(in source: String, named name: String) -> String? {
    let signature = "func \(name)("
    guard let start = source.range(of: signature),
      let openBrace = source[start.upperBound...].firstIndex(of: "{")
    else { return nil }
    var depth = 0
    var index = openBrace
    while index < source.endIndex {
      let character = source[index]
      if character == "{" { depth += 1 }
      if character == "}" {
        depth -= 1
        if depth == 0 {
          return String(source[openBrace...index])
        }
      }
      index = source.index(after: index)
    }
    return nil
  }
}
