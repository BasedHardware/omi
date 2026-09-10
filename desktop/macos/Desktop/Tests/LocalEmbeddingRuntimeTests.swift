import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class LocalEmbeddingRuntimeTests: XCTestCase {
  func testRuntimeFailClosedProbeAndDisabledState() async throws {
    let engine = HashEmbeddingEngine()
    var runtime = LocalEmbeddingRuntime(engines: [], record: { _, _ in })
    guard case .none = await runtime.selectEngine() else { return XCTFail("empty registry must fail closed") }
    runtime = LocalEmbeddingRuntime(engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    guard case .engine = await runtime.selectEngine() else { return XCTFail("fixture engine must pass probe") }
    let fixtureCount = LocalEmbeddingProbe.fixture.split(separator: " ").count
    XCTAssertEqual(fixtureCount, 32)
    runtime.probe = { _ in
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .seconds(3), dimension: 8)
    }
    guard case .none = await runtime.selectEngine() else { return XCTFail("over-budget probe accepted") }
    for result in [
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: false, fixtureSucceeded: true, elapsed: .zero, dimension: 8),
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 7),
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: false, elapsed: .zero, dimension: 8),
    ] {
      runtime.probe = { _ in result }
      guard case .none = await runtime.selectEngine() else { return XCTFail("failed readiness gate accepted") }
    }
    runtime.killSwitches = LocalEmbeddingKillSwitches(isDisabled: true, forcedEngineRaw: nil)
    runtime.probe = { _ in
      XCTFail("disabled runtime probed engine")
      return LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 8)
    }
    guard case .disabled = await runtime.selectEngine() else { return XCTFail("kill switch ignored") }
  }

  func testDisabledAndUnknownEngineNeverReachInjectedHTTPClient() async {
    let engine = HTTPTrapEmbeddingEngine(client: ForbiddenEmbeddingHTTPClient())
    let disabled = LocalEmbeddingRuntime(
      engines: [engine],
      killSwitches: LocalEmbeddingKillSwitches(isDisabled: true, forcedEngineRaw: engine.engineID), record: { _, _ in })
    guard case .disabled = await disabled.selectEngine() else { return XCTFail("disabled engine selected") }
    let missing = LocalEmbeddingRuntime(engines: [engine], defaultEngineID: "absent", record: { _, _ in })
    guard case .none = await missing.selectEngine() else { return XCTFail("unknown engine selected another adapter") }
  }

  func testKillSwitchEnvironmentAndDefaultsResolution() throws {
    let name = "LocalEmbeddingTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
    defer { defaults.removePersistentDomain(forName: name) }
    defaults.set(true, forKey: "disableLocalEmbeddings")
    defaults.set("defaults-engine", forKey: "forceLocalEmbeddingEngine")
    let flags = LocalEmbeddingKillSwitches.resolve(
      environment: ["OMI_DISABLE_LOCAL_EMBEDDINGS": "0", "OMI_FORCE_LOCAL_EMBEDDING_ENGINE": " test_hash "],
      defaults: defaults)
    XCTAssertTrue(flags.isDisabled)
    XCTAssertEqual(flags.forcedEngineRaw, "test_hash")
    XCTAssertEqual(
      LocalEmbeddingKillSwitches.resolve(environment: [:], defaults: defaults).forcedEngineRaw, "defaults-engine")
  }
}
