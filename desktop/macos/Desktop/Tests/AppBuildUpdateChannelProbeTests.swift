import XCTest

@testable import Omi_Computer

/// Launch-time update-channel probe (#9192).
///
/// The probe runs on the main thread inside `AppState.init()`, before the first frame,
/// because backend routing needs the channel. It must therefore never hold the main
/// thread past the 3s "App Hanging" watchdog, and it must not permanently pin an
/// install to the channel it guessed when the network was too slow to answer.
final class AppBuildUpdateChannelProbeTests: XCTestCase {

  private static let betaAppcast = """
    <rss><channel>
      <item><sparkle:version>11000</sparkle:version></item>
      <item><sparkle:channel>beta</sparkle:channel><sparkle:version>11200</sparkle:version></item>
    </channel></rss>
    """

  // MARK: - Fast path: the appcast answers within the budget

  func testAppcastAnsweringWithinBudgetResolvesBetaForABuildAheadOfStable() {
    let resolved = AppBuild.probeFreshInstallUpdateChannel(
      fallback: "stable",
      currentBuild: 11200,
      mainThreadBudget: 1.5,
      fetchAppcast: { completion in completion(Self.betaAppcast) },
      persistLateCorrection: { _ in XCTFail("answered in time; nothing to correct") }
    )

    XCTAssertEqual(resolved, "beta")
  }

  func testAppcastAnsweringWithinBudgetKeepsStableForABuildAtLatestStable() {
    let resolved = AppBuild.probeFreshInstallUpdateChannel(
      fallback: "stable",
      currentBuild: 11000,
      mainThreadBudget: 1.5,
      fetchAppcast: { completion in completion(Self.betaAppcast) },
      persistLateCorrection: { _ in XCTFail("answered in time; nothing to correct") }
    )

    XCTAssertEqual(resolved, "stable")
  }

  // MARK: - Regression: a silent network must not hold the main thread

  /// The bug: the probe waited on the appcast for 3.5s inline, and `prepareUpdateChannelForBackendRouting`
  /// ran it twice on a fresh install — up to 7s of main-thread stall before the first frame.
  /// A fetch that never answers must return the inferred channel immediately instead.
  func testSilentNetworkReturnsTheInferredChannelWithoutBlocking() {
    var pendingCompletion: ((String?) -> Void)?

    let started = Date()
    let resolved = AppBuild.probeFreshInstallUpdateChannel(
      fallback: "stable",
      currentBuild: 11200,
      mainThreadBudget: 0,
      fetchAppcast: { completion in pendingCompletion = completion },
      persistLateCorrection: { _ in }
    )

    XCTAssertEqual(resolved, "stable", "launch must proceed on the inferred channel")
    XCTAssertLessThan(
      Date().timeIntervalSince(started), 1.0,
      "an unanswered appcast must not stall the launch path")
    XCTAssertNotNil(pendingCompletion, "the request is left in flight, not cancelled")
  }

  /// A beta install whose first launch had a slow network used to be pinned to stable
  /// forever (the timed-out guess was written to UserDefaults and never re-resolved).
  /// The late answer now corrects the stored channel for the next launch.
  func testAppcastAnsweringAfterTheBudgetCorrectsTheStoredChannel() {
    var pendingCompletion: ((String?) -> Void)?
    let corrected = expectation(description: "late appcast corrects the stored channel")
    var correctedTo: String?

    let resolved = AppBuild.probeFreshInstallUpdateChannel(
      fallback: "stable",
      currentBuild: 11200,
      mainThreadBudget: 0,
      fetchAppcast: { completion in pendingCompletion = completion },
      persistLateCorrection: { channel in
        correctedTo = channel
        corrected.fulfill()
      }
    )

    XCTAssertEqual(resolved, "stable", "this launch keeps the channel it already routed on")

    pendingCompletion?(Self.betaAppcast)

    wait(for: [corrected], timeout: 5)
    XCTAssertEqual(correctedTo, "beta")
  }

  func testLateAppcastAgreeingWithTheInferredChannelWritesNothing() {
    var pendingCompletion: ((String?) -> Void)?
    let settled = expectation(description: "late appcast processed")
    settled.isInverted = true

    let resolved = AppBuild.probeFreshInstallUpdateChannel(
      fallback: "stable",
      currentBuild: 11000,
      mainThreadBudget: 0,
      fetchAppcast: { completion in pendingCompletion = completion },
      persistLateCorrection: { _ in settled.fulfill() }
    )

    XCTAssertEqual(resolved, "stable")

    pendingCompletion?(Self.betaAppcast)

    wait(for: [settled], timeout: 1)
  }

  // MARK: - The probe is skipped entirely when the bundle already answers

  func testBetaBundleResolvesWithoutTouchingTheNetwork() {
    let resolved = AppBuild.probeFreshInstallUpdateChannel(
      fallback: "beta",
      currentBuild: 11200,
      mainThreadBudget: 1.5,
      fetchAppcast: { _ in XCTFail("a beta bundle needs no appcast round trip") },
      persistLateCorrection: { _ in XCTFail("nothing to correct") }
    )

    XCTAssertEqual(resolved, "beta")
  }

  func testMissingBuildNumberResolvesWithoutTouchingTheNetwork() {
    let resolved = AppBuild.probeFreshInstallUpdateChannel(
      fallback: "stable",
      currentBuild: nil,
      mainThreadBudget: 1.5,
      fetchAppcast: { _ in XCTFail("no build number to compare against") },
      persistLateCorrection: { _ in XCTFail("nothing to correct") }
    )

    XCTAssertEqual(resolved, "stable")
  }

  // MARK: - The beta-overwrite migration must not probe on a fresh install

  /// `prepareUpdateChannelForBackendRouting()` runs the migration and then the first-launch
  /// sync. On a fresh install there is no overwritten preference to restore, so the migration
  /// probing the appcast only doubled the launch-blocking round trips.
  func testBetaOverwriteMigrationDoesNotProbeOnAFreshInstall() {
    withCleanChannelDefaults {
      AppBuild.migrateBetaChannelOverwrite(probeAppcast: {
        XCTFail("a fresh install has no overwritten channel to restore")
        return "stable"
      })

      XCTAssertNil(
        UserDefaults.standard.string(forKey: "update_channel"),
        "the first-launch sync owns the initial channel")
      XCTAssertTrue(UserDefaults.standard.bool(forKey: "didMigrateBetaOverwrite_v1"))
    }
  }

  func testBetaOverwriteMigrationStillRestoresBetaForAnExistingStableUser() {
    withCleanChannelDefaults {
      UserDefaults.standard.set("stable", forKey: "update_channel")

      AppBuild.migrateBetaChannelOverwrite(probeAppcast: { "beta" })

      XCTAssertEqual(UserDefaults.standard.string(forKey: "update_channel"), "beta")
    }
  }

  private func withCleanChannelDefaults(_ body: () -> Void) {
    let defaults = UserDefaults.standard
    let previousChannel = defaults.string(forKey: "update_channel")
    let previousMigration = defaults.bool(forKey: "didMigrateBetaOverwrite_v1")
    defer {
      defaults.set(previousMigration, forKey: "didMigrateBetaOverwrite_v1")
      if let previousChannel {
        defaults.set(previousChannel, forKey: "update_channel")
      } else {
        defaults.removeObject(forKey: "update_channel")
      }
    }

    defaults.removeObject(forKey: "update_channel")
    defaults.removeObject(forKey: "didMigrateBetaOverwrite_v1")
    body()
  }
}
