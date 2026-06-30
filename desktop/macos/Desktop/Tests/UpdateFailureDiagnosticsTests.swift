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
}
