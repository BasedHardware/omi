import XCTest

@testable import Omi_Computer

final class UpdateFailureDiagnosticsTests: XCTestCase {
  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: "update_channel")
    super.tearDown()
  }

  func testManualDownloadURLUsesConcreteStableEndpointByDefault() {
    UserDefaults.standard.removeObject(forKey: "update_channel")

    XCTAssertEqual(
      AppBuild.manualDownloadURL.absoluteString,
      "https://api.omi.me/v2/desktop/download/latest?channel=stable"
    )
  }

  func testManualDownloadURLPreservesBetaChannel() {
    UserDefaults.standard.set("beta", forKey: "update_channel")

    XCTAssertEqual(
      AppBuild.manualDownloadURL.absoluteString,
      "https://api.omi.me/v2/desktop/download/latest?channel=beta"
    )
  }

  func testLaunchLocationBucketsDownloadsFolder() {
    XCTAssertEqual(
      UpdateFailureDiagnostics.launchLocationBucket(
        for: "/Users/alex/Downloads/Omi.app"
      ),
      "downloads_folder"
    )
  }

  func testLaunchLocationBucketsMountedVolume() {
    XCTAssertEqual(
      UpdateFailureDiagnostics.launchLocationBucket(
        for: "/Volumes/Omi/Omi.app"
      ),
      "dmg_mounted"
    )
  }

  func testClassifiesReadOnlyLocation() {
    let error = NSError(
      domain: "SUSparkleErrorDomain",
      code: 4005,
      userInfo: [
        NSLocalizedDescriptionKey:
          "omi can't be updated because it was opened from a read-only or a temporary location."
      ]
    )

    let diagnostics = UpdateFailureDiagnostics.classify(
      error: error,
      updateChannel: "stable",
      bundlePath: "/Volumes/Omi/Omi.app"
    )

    XCTAssertEqual(diagnostics.reason, .readOnlyLocation)
    XCTAssertEqual(diagnostics.launchLocationBucket, "dmg_mounted")
    XCTAssertTrue(diagnostics.isRecoverableLaunchLocation)
  }

  func testClassifiesDownloadFailure() {
    let error = NSError(
      domain: "SUSparkleErrorDomain",
      code: 3002,
      userInfo: [
        NSLocalizedDescriptionKey:
          "An error occurred while downloading the update. Please try again later."
      ]
    )

    let diagnostics = UpdateFailureDiagnostics.classify(
      error: error,
      updateChannel: "beta",
      bundlePath: "/Applications/Omi.app"
    )

    XCTAssertEqual(diagnostics.reason, .download)
    XCTAssertEqual(diagnostics.updateChannel, "beta")
    XCTAssertEqual(diagnostics.launchLocationBucket, "applications_system")
  }

  func testClassifiesUnderlyingNetworkFailure() {
    let underlying = NSError(domain: NSURLErrorDomain, code: NSURLErrorTimedOut)
    let error = NSError(
      domain: "SUSparkleErrorDomain",
      code: 2001,
      userInfo: [
        NSLocalizedDescriptionKey: "The update check failed.",
        NSUnderlyingErrorKey: underlying,
      ]
    )

    let diagnostics = UpdateFailureDiagnostics.classify(
      error: error,
      updateChannel: "stable",
      bundlePath: "/Applications/Omi.app"
    )

    XCTAssertEqual(diagnostics.reason, .network)
    XCTAssertEqual(diagnostics.underlyingDomain, NSURLErrorDomain)
    XCTAssertEqual(diagnostics.underlyingCode, NSURLErrorTimedOut)
  }

  func testClassifiesDeeplyWrappedSparkleDownloadFailureAsNetwork() {
    let url = URL(string: "https://api.omi.me/v2/desktop/appcast.xml")!
    let network = NSError(
      domain: NSURLErrorDomain,
      code: NSURLErrorTimedOut,
      userInfo: [
        NSURLErrorFailingURLErrorKey: url
      ]
    )
    let innerSparkle = NSError(
      domain: "SUSparkleErrorDomain",
      code: 2001,
      userInfo: [
        NSLocalizedDescriptionKey: "An error occurred in retrieving update information.",
        NSUnderlyingErrorKey: network,
      ]
    )
    let outerSparkle = NSError(
      domain: "SUSparkleErrorDomain",
      code: 2001,
      userInfo: [
        NSLocalizedDescriptionKey: "An error occurred in retrieving update information.",
        NSUnderlyingErrorKey: innerSparkle,
      ]
    )

    let diagnostics = UpdateFailureDiagnostics.classify(
      error: outerSparkle,
      updateChannel: "stable",
      bundlePath: "/Applications/Omi.app",
      sourceAppVersion: "0.12.0",
      sourceAppBuild: "12000",
      appcastURL: url
    )

    XCTAssertEqual(diagnostics.reason, .network)
    XCTAssertEqual(diagnostics.nsurlErrorCode, NSURLErrorTimedOut)
    XCTAssertEqual(
      diagnostics.errorChainDomains,
      ["SUSparkleErrorDomain", "SUSparkleErrorDomain", NSURLErrorDomain]
    )
    XCTAssertEqual(diagnostics.errorChainCodes, [2001, 2001, NSURLErrorTimedOut])

    let properties = diagnostics.analyticsProperties
    XCTAssertEqual(properties["phase"] as? String, "network")
    XCTAssertEqual(properties["update_failure_phase"] as? String, "network")
    XCTAssertEqual(properties["update_failure_reason"] as? String, "network")
    XCTAssertEqual(properties["nsurl_error_code"] as? Int, NSURLErrorTimedOut)
    XCTAssertEqual(properties["failing_url_host"] as? String, "api.omi.me")
    XCTAssertEqual(properties["failing_url_path"] as? String, "/v2/desktop/appcast.xml")
    XCTAssertEqual(properties["source_app_version"] as? String, "0.12.0")
    XCTAssertEqual(properties["source_app_build"] as? String, "12000")
    XCTAssertEqual(properties["appcast_url_host"] as? String, "api.omi.me")
    // Regression: Update Check Failed must carry a non-empty error message so the
    // daily report's error_or_message column is populated (was blank on 0.12.0).
    XCTAssertEqual(
      properties["error"] as? String, "An error occurred in retrieving update information.")
    XCTAssertEqual(
      properties["update_failure_message"] as? String,
      "An error occurred in retrieving update information.")
  }

  func testAnalyticsPropertiesOmitRawPath() {
    let error = NSError(
      domain: "SUSparkleErrorDomain",
      code: 3002,
      userInfo: [
        NSLocalizedDescriptionKey:
          "An error occurred while downloading the update. Please try again later."
      ]
    )

    let diagnostics = UpdateFailureDiagnostics.classify(
      error: error,
      updateChannel: "stable",
      bundlePath: "/Users/alex/Downloads/Omi.app"
    )

    let properties = diagnostics.analyticsProperties
    XCTAssertEqual(properties["update_failure_reason"] as? String, "downloads_location")
    XCTAssertEqual(properties["launch_location_bucket"] as? String, "downloads_folder")
    XCTAssertNil(properties["bundle_path"])
  }

  func testAnalyticsPropertiesFallbackMessageIsNonEmpty() {
    let diagnostics = UpdateFailureDiagnostics(
      reason: .unknown,
      message: "",
      domain: "SUSparkleErrorDomain",
      code: 2001,
      underlyingDomain: nil,
      underlyingCode: nil,
      errorChainDomains: ["SUSparkleErrorDomain"],
      errorChainCodes: [2001],
      nsurlErrorCode: nil,
      failingURLHost: nil,
      failingURLPath: nil,
      updateChannel: "stable",
      launchLocationBucket: "applications_system",
      sourceAppVersion: "0.12.0",
      sourceAppBuild: "12000",
      appcastURLHost: "api.omi.me",
      appcastURLPath: "/v2/desktop/appcast.xml"
    )

    let properties = diagnostics.analyticsProperties
    XCTAssertEqual(properties["error"] as? String, "SUSparkleErrorDomain 2001")
    XCTAssertEqual(properties["phase"] as? String, "unknown")
    XCTAssertEqual(properties["update_failure_message"] as? String, "SUSparkleErrorDomain 2001")
    XCTAssertEqual(properties["update_failure_phase"] as? String, "unknown")
  }
}
