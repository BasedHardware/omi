import Foundation
import XCTest

@testable import Omi_Computer

private final class ProbeCallCounter: @unchecked Sendable {
  var count = 0
  var thermal = ProcessInfo.ThermalState.nominal
  func increment() { count += 1 }
}

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
    await runtime.probeCache.invalidate()
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
      await runtime.probeCache.invalidate()
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
    defaults.set(true, forKey: .disableLocalEmbeddings)
    defaults.set("defaults-engine", forKey: .forceLocalEmbeddingEngine)
    let flags = LocalEmbeddingKillSwitches.resolve(
      environment: ["OMI_DISABLE_LOCAL_EMBEDDINGS": "0", "OMI_FORCE_LOCAL_EMBEDDING_ENGINE": " test_hash "],
      defaults: defaults)
    XCTAssertTrue(flags.isDisabled)
    XCTAssertEqual(flags.forcedEngineRaw, "test_hash")
    XCTAssertEqual(
      LocalEmbeddingKillSwitches.resolve(environment: [:], defaults: defaults).forcedEngineRaw, "defaults-engine")
  }

  func testCachedProbeFailureIsReprobedAfterInvalidation() async {
    let engine = HashEmbeddingEngine()
    let cache = LocalEmbeddingProbeCache()
    let probes = ProbeCallCounter()
    var runtime = LocalEmbeddingRuntime(
      engines: [engine], defaultEngineID: engine.engineID, probeCache: cache, record: { _, _ in })
    runtime.probe = { _ in
      probes.increment()
      return LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: false, fixtureSucceeded: false, elapsed: .zero, dimension: 0,
        reason: "assets_unavailable")
    }
    guard case .none = await runtime.selectEngine() else { return XCTFail("failed probe selected") }
    XCTAssertEqual(probes.count, 1)
    guard case .none = await runtime.selectEngine() else { return XCTFail("cached failure selected") }
    XCTAssertEqual(probes.count, 1, "cached failure must not re-probe")
    await cache.invalidate()
    guard case .none = await runtime.selectEngine() else { return XCTFail("invalidated cache skipped probe") }
    XCTAssertEqual(probes.count, 2)
  }

  func testThermalStateChangeBypassesCachedProbe() async {
    let engine = HashEmbeddingEngine()
    let probes = ProbeCallCounter()
    var runtime = LocalEmbeddingRuntime(
      engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    runtime.thermalState = { probes.thermal }
    runtime.probe = { _ in
      probes.increment()
      return LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: false, fixtureSucceeded: false, elapsed: .zero, dimension: 0,
        reason: "assets_unavailable")
    }
    _ = await runtime.selectEngine()
    probes.thermal = .serious
    _ = await runtime.selectEngine()
    XCTAssertEqual(probes.count, 2)
  }

  func testProbeReportsAssetsUnavailableWithoutFailing() async {
    let engine = UnavailableAssetsEmbeddingEngine()
    let probe = await LocalEmbeddingProbe.run(engine)
    XCTAssertEqual(probe.reason, LocalEmbeddingAssetStatus.assetsUnavailable.rawValue)
    XCTAssertFalse(probe.assetsAvailable)
    XCTAssertFalse(probe.permits(engine, budget: .seconds(2)))
  }
}

@MainActor
final class LocalEmbeddingOptInTests: XCTestCase {
  override func tearDown() async throws {
    await LocalEmbeddingIndexer.shared.setRuntimeForTesting(.makeDefault())
    try await super.tearDown()
  }

  func testProductionFamilyDefaultDisablesEngineAndIndexer() async throws {
    let (defaults, cleanup) = try emptyDefaults()
    defer { cleanup() }
    let flags = LocalEmbeddingKillSwitches.resolve(
      environment: [:], defaults: defaults, isNonProduction: false)
    XCTAssertFalse(flags.isEnabled)
    XCTAssertFalse(flags.isDisabled)

    let engine = FailOnCallEmbeddingEngine()
    var runtime = LocalEmbeddingRuntime(
      engines: [engine], killSwitches: flags, defaultEngineID: engine.engineID, record: { _, _ in })
    runtime.probe = { _ in
      XCTFail("opted-out runtime must not probe")
      return LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 8)
    }
    guard case .disabled = await runtime.selectEngine() else {
      return XCTFail("production-family default must keep the Gemini route")
    }

    await LocalEmbeddingIndexer.shared.setRuntimeForTesting(runtime)
    await LocalEmbeddingIndexer.shared.indexFinalizedSession(sessionId: 1)
    await LocalEmbeddingIndexer.shared.indexMemory(id: 1, content: "synthetic opted-out memory")
    await LocalEmbeddingIndexer.shared.backfillIfNeeded()
  }

  func testNonProductionDefaultSelectsEngine() async throws {
    let (defaults, cleanup) = try emptyDefaults()
    defer { cleanup() }
    let engine = HashEmbeddingEngine()
    let flags = LocalEmbeddingKillSwitches.resolve(
      environment: [:], defaults: defaults, isNonProduction: true)
    XCTAssertTrue(flags.isEnabled)
    var runtime = LocalEmbeddingRuntime(
      engines: [engine], killSwitches: flags, defaultEngineID: engine.engineID, record: { _, _ in })
    runtime.probe = { _ in
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 8)
    }
    guard case .engine = await runtime.selectEngine() else {
      return XCTFail("non-production default must select the local engine")
    }
  }

  func testDefaultsKeyEnablesProductionFamily() async throws {
    let (defaults, cleanup) = try emptyDefaults()
    defer { cleanup() }
    defaults.set(true, forKey: .localEmbeddingsEnabled)
    let flags = LocalEmbeddingKillSwitches.resolve(
      environment: [:], defaults: defaults, isNonProduction: false)
    XCTAssertTrue(flags.isEnabled)
    let engine = HashEmbeddingEngine()
    var runtime = LocalEmbeddingRuntime(
      engines: [engine], killSwitches: flags, defaultEngineID: engine.engineID, record: { _, _ in })
    runtime.probe = { _ in
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 8)
    }
    guard case .engine = await runtime.selectEngine() else {
      return XCTFail("localEmbeddingsEnabled must opt production-family bundles in")
    }
  }

  func testEnvironmentFlagTurnsLocalEmbeddingsOff() async throws {
    let (defaults, cleanup) = try emptyDefaults()
    defer { cleanup() }
    defaults.set(true, forKey: .localEmbeddingsEnabled)
    let flags = LocalEmbeddingKillSwitches.resolve(
      environment: ["OMI_LOCAL_EMBEDDINGS": "0"], defaults: defaults, isNonProduction: true)
    XCTAssertFalse(flags.isEnabled)
    let engine = FailOnCallEmbeddingEngine()
    var runtime = LocalEmbeddingRuntime(
      engines: [engine], killSwitches: flags, defaultEngineID: engine.engineID, record: { _, _ in })
    runtime.probe = { _ in
      XCTFail("env-disabled runtime must not probe")
      return LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 8)
    }
    guard case .disabled = await runtime.selectEngine() else {
      return XCTFail("OMI_LOCAL_EMBEDDINGS=0 must keep the Gemini route")
    }
  }

  private func emptyDefaults() throws -> (UserDefaults, () -> Void) {
    let name = "LocalEmbeddingOptInTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
    defaults.removePersistentDomain(forName: name)
    return (defaults, { defaults.removePersistentDomain(forName: name) })
  }
}
