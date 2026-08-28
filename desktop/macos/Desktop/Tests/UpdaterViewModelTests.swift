import XCTest

@testable import Omi_Computer

final class UpdaterViewModelTests: XCTestCase {
  private func analyticsContext(channel: String = "stable") -> UpdateAnalyticsContext {
    UpdateAnalyticsContext(
      sourceAppVersion: "0.12.0",
      sourceAppBuild: "12000",
      updateChannel: channel,
      appcastURLHost: "api.omi.me",
      appcastURLPath: "/v2/desktop/appcast.xml"
    )
  }

  func testAdmittedChecksKeepTriggerIdentityAndCloseMissingPriorCallback() {
    var now = Date(timeIntervalSince1970: 1_000)
    var nextID = 0
    let tracker = UpdateCheckAttemptTracker(
      now: { now },
      makeID: {
        nextID += 1
        return "check-\(nextID)"
      }
    )

    let automatic = tracker.begin(trigger: .automatic, context: analyticsContext())
    XCTAssertNil(automatic.abandoned)
    XCTAssertEqual(automatic.attempt.id, "check-1")
    XCTAssertEqual(automatic.attempt.trigger, .automatic)

    // Sparkle serializes this admitted-start boundary. Seeing another start
    // therefore closes the previous instrumentation gap instead of reusing it.
    now = now.addingTimeInterval(2.5)
    let manual = tracker.begin(trigger: .manual, context: analyticsContext(channel: "beta"))
    XCTAssertEqual(manual.attempt.id, "check-2")
    XCTAssertEqual(manual.attempt.trigger, .manual)
    XCTAssertEqual(manual.attempt.updateChannel, "beta")
    XCTAssertEqual(manual.abandoned?.attempt.id, automatic.attempt.id)
    XCTAssertEqual(manual.abandoned?.result, .callbackMissing)
    XCTAssertEqual(manual.abandoned?.durationSeconds, 2.5)
  }

  func testNoUpdateHasExactlyOneTerminalOutcomeAndIsNotFailure() {
    let tracker = UpdateCheckAttemptTracker(
      now: { Date(timeIntervalSince1970: 1_005) },
      makeID: { "check-no-update" }
    )
    _ = tracker.begin(trigger: .automatic, context: analyticsContext())

    let terminal = tracker.finish(result: .noUpdate)
    XCTAssertEqual(terminal?.result, .noUpdate)
    XCTAssertNil(terminal?.diagnostics)
    XCTAssertEqual(terminal?.analyticsProperties["result"] as? String, "no_update")
    XCTAssertNil(terminal?.analyticsProperties["update_failure_reason"])

    // Sparkle may send didAbortWithError("already up to date") after this.
    XCTAssertNil(tracker.finish(result: .failed))
  }

  func testMissingTerminalCallbackRemainsUnknown() {
    let tracker = UpdateCheckAttemptTracker(makeID: { "check-missing-terminal" })
    _ = tracker.begin(trigger: .automatic, context: analyticsContext())

    let terminal = tracker.finish(result: .callbackMissing)
    XCTAssertEqual(terminal?.result, .callbackMissing)
  }

  func testFailedOutcomeCarriesBoundedFailureDiagnostics() {
    let error = NSError(
      domain: "SUSparkleErrorDomain",
      code: 2001,
      userInfo: [
        NSLocalizedDescriptionKey: "The update check failed.",
        NSUnderlyingErrorKey: NSError(domain: NSURLErrorDomain, code: NSURLErrorTimedOut),
      ]
    )
    let diagnostics = UpdateFailureDiagnostics.classify(
      error: error,
      updateChannel: "stable",
      bundlePath: "/Applications/Omi.app"
    )
    let tracker = UpdateCheckAttemptTracker(
      now: { Date(timeIntervalSince1970: 1_005) },
      makeID: { "check-failed" }
    )
    _ = tracker.begin(trigger: .manual, context: analyticsContext())

    let terminal = tracker.finish(result: .failed, diagnostics: diagnostics)
    XCTAssertEqual(terminal?.result, .failed)
    XCTAssertEqual(terminal?.diagnostics, diagnostics)
    XCTAssertEqual(
      terminal?.analyticsProperties["update_failure_reason"] as? String,
      "network"
    )
    XCTAssertEqual(
      terminal?.analyticsProperties["nsurl_error_code"] as? Int,
      NSURLErrorTimedOut
    )
    XCTAssertNil(terminal?.analyticsProperties["error"])
    XCTAssertNil(terminal?.analyticsProperties["update_failure_message"])
    XCTAssertNil(terminal?.analyticsProperties["failing_url_path"])
    XCTAssertNil(terminal?.analyticsProperties["error_chain_domains"])
    XCTAssertNil(terminal?.analyticsProperties["error_chain_codes"])
    XCTAssertNil(terminal?.analyticsProperties["update_failure_domain"])
    XCTAssertNil(terminal?.analyticsProperties["underlying_domain"])
    XCTAssertNil(terminal?.analyticsProperties["appcast_url_host"])
    XCTAssertNil(terminal?.analyticsProperties["appcast_url_path"])
  }

  func testAutomaticOfflineCheckIsExpectedButManualOfflineStillFails() {
    let offline = UpdateFailureDiagnostics.classify(
      error: NSError(
        domain: "SUSparkleErrorDomain",
        code: 2001,
        userInfo: [
          NSUnderlyingErrorKey: NSError(
            domain: NSURLErrorDomain,
            code: NSURLErrorNotConnectedToInternet
          )
        ]
      ),
      updateChannel: "stable",
      bundlePath: "/Applications/Omi.app"
    )

    let automatic = UpdateCheckAttemptTracker(makeID: { "automatic-offline" })
    _ = automatic.begin(trigger: .automatic, context: analyticsContext())
    XCTAssertEqual(automatic.finishFailure(diagnostics: offline)?.result, .networkUnavailable)

    let manual = UpdateCheckAttemptTracker(makeID: { "manual-offline" })
    _ = manual.begin(trigger: .manual, context: analyticsContext())
    XCTAssertEqual(manual.finishFailure(diagnostics: offline)?.result, .failed)
  }

  func testDuplicateAutomaticOfflineTerminalRetainsExpectedClassification() {
    let offline = UpdateFailureDiagnostics.classify(
      error: NSError(
        domain: "SUSparkleErrorDomain",
        code: 2001,
        userInfo: [
          NSUnderlyingErrorKey: NSError(
            domain: NSURLErrorDomain,
            code: NSURLErrorNotConnectedToInternet
          )
        ]
      ),
      updateChannel: "stable",
      bundlePath: "/Applications/Omi.app"
    )
    let tracker = UpdateCheckAttemptTracker(makeID: { "automatic-offline-duplicate" })
    _ = tracker.begin(trigger: .automatic, context: analyticsContext())

    XCTAssertEqual(tracker.finishFailure(diagnostics: offline)?.result, .networkUnavailable)
    XCTAssertNil(tracker.finishFailure(diagnostics: offline), "A duplicate callback must not emit a second terminal")
    XCTAssertTrue(tracker.lastCompletedWasExpectedAutomaticOffline(for: offline))
  }

  private func sparkleFailure(
    code: Int,
    nsurlCode: Int?,
    bundlePath: String = "/Applications/Omi.app"
  ) -> UpdateFailureDiagnostics {
    var userInfo: [String: Any] = [NSLocalizedDescriptionKey: "The update check failed."]
    if let nsurlCode {
      userInfo[NSUnderlyingErrorKey] = NSError(domain: NSURLErrorDomain, code: nsurlCode)
    }
    return UpdateFailureDiagnostics.classify(
      error: NSError(domain: "SUSparkleErrorDomain", code: code, userInfo: userInfo),
      updateChannel: "stable",
      bundlePath: bundlePath
    )
  }

  /// Sparkle re-delivers `didAbortWithError` for a single check. `Update Check
  /// Completed` is protected by consuming the attempt identity, but the legacy
  /// `Update Check Failed` event fires straight from the delegate and had no
  /// such guard, so one failed check was counted once per callback — 3x to 47x
  /// inflation on shipped builds, which is why it dominated macOS reliability
  /// reporting in the 2026-08 churn cohort.
  func testRepeatedAbortForOneCheckIsRecognizedAsADuplicate() {
    let failure = sparkleFailure(code: 2001, nsurlCode: NSURLErrorNetworkConnectionLost)
    let tracker = UpdateCheckAttemptTracker(makeID: { "check-duplicate-failure" })
    _ = tracker.begin(trigger: .automatic, context: analyticsContext())

    XCTAssertEqual(tracker.finishFailure(diagnostics: failure)?.result, .failed)
    XCTAssertTrue(
      tracker.isDuplicateOfLastTerminal(failure),
      "the second abort for the same closed check must not be reported again")
  }

  /// The guard keys on the closed terminal, not on "no active attempt", so a
  /// genuinely different failure and a first-ever abort are both still reported.
  func testDistinctAndUntrackedFailuresAreStillReported() {
    let network = sparkleFailure(code: 2001, nsurlCode: NSURLErrorTimedOut)
    let installer = sparkleFailure(code: 4005, nsurlCode: nil)

    let tracker = UpdateCheckAttemptTracker(makeID: { "check-distinct-failure" })
    _ = tracker.begin(trigger: .automatic, context: analyticsContext())
    XCTAssertEqual(tracker.finishFailure(diagnostics: network)?.result, .failed)
    XCTAssertFalse(
      tracker.isDuplicateOfLastTerminal(installer),
      "a different failure after a closed check is a new occurrence")

    let untracked = UpdateCheckAttemptTracker(makeID: { "check-never-started" })
    XCTAssertFalse(
      untracked.isDuplicateOfLastTerminal(network),
      "an abort with nothing closed yet must still be reported, not swallowed")
  }

  /// The guard must never suppress a live check's first terminal.
  func testActiveCheckIsNeverTreatedAsADuplicate() {
    let failure = sparkleFailure(code: 3000, nsurlCode: nil)
    let tracker = UpdateCheckAttemptTracker(makeID: { "check-active" })
    _ = tracker.begin(trigger: .automatic, context: analyticsContext())
    XCTAssertEqual(tracker.finishFailure(diagnostics: failure)?.result, .failed)

    _ = tracker.begin(trigger: .automatic, context: analyticsContext())
    XCTAssertFalse(
      tracker.isDuplicateOfLastTerminal(failure),
      "a new admitted check owns its own terminal even when the failure repeats")
  }

  func testManualCheckIsUnavailableWhileBackgroundUpdateSessionIsInProgress() {
    XCTAssertFalse(
      UpdaterViewModel.allowsManualCheck(
        canCheckForUpdates: true,
        updateSessionInProgress: true
      )
    )
  }

  func testManualCheckRequiresSparkleToAllowChecking() {
    XCTAssertFalse(
      UpdaterViewModel.allowsManualCheck(
        canCheckForUpdates: false,
        updateSessionInProgress: false
      )
    )
  }

  func testManualCheckIsAvailableWhenNoSessionIsInProgress() {
    XCTAssertTrue(
      UpdaterViewModel.allowsManualCheck(
        canCheckForUpdates: true,
        updateSessionInProgress: false
      )
    )
  }
}
