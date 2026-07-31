import XCTest

@testable import Omi_Computer

final class ExternalPreviewBuildTests: XCTestCase {
  private let previewBundleIdentifier = "com.omi.preview.p8b1f42a9"

  func testConfiguredPreviewDisablesLocalAutomationAndSparkle() {
    let configuration = AppBuild.configuration(
      bundleIdentifier: previewBundleIdentifier,
      infoDictionary: [
        AppBuild.externalPreviewMarkerInfoKey: true,
        AppBuild.externalPreviewBackendInfoKey: "development",
      ]
    )

    XCTAssertTrue(configuration.isExternalPreview)
    XCTAssertTrue(configuration.hasExternalPreviewMarker)
    XCTAssertEqual(configuration.externalPreviewBackend, .development)
    XCTAssertTrue(configuration.hasValidExternalPreviewConfiguration)
    XCTAssertFalse(configuration.allowsLocalAutomation)
    XCTAssertFalse(configuration.allowsSparkleUpdates)
  }

  func testPreviewIdentityFailsClosedWhenPackagingMetadataIsMissing() {
    let configuration = AppBuild.configuration(
      bundleIdentifier: previewBundleIdentifier,
      infoDictionary: [:]
    )

    XCTAssertTrue(configuration.isExternalPreview)
    XCTAssertFalse(configuration.hasValidExternalPreviewConfiguration)
    XCTAssertFalse(configuration.allowsLocalAutomation)
    XCTAssertFalse(configuration.allowsSparkleUpdates)

    XCTAssertFalse(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: previewBundleIdentifier,
        updateChannel: "stable",
        externalPreviewBackend: nil
      ),
      "a malformed preview must not inherit local-development routing"
    )
  }

  func testPreviewBackendSelectionIsExplicit() {
    XCTAssertTrue(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: previewBundleIdentifier,
        updateChannel: "stable",
        externalPreviewBackend: .development
      )
    )
    XCTAssertFalse(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: previewBundleIdentifier,
        updateChannel: "stable",
        externalPreviewBackend: .production
      ),
      "a preview's signed backend selection must select its only permitted plane"
    )
  }

  func testNamedDevelopmentBundlesKeepAutomationButDisableSharedSparkle() {
    let configuration = AppBuild.configuration(
      bundleIdentifier: "com.omi.omi-local-preview",
      infoDictionary: [
        AppBuild.externalPreviewMarkerInfoKey: true,
        AppBuild.externalPreviewBackendInfoKey: "production",
      ]
    )

    XCTAssertTrue(configuration.isNonProduction)
    XCTAssertFalse(configuration.isExternalPreview)
    XCTAssertTrue(configuration.allowsLocalAutomation)
    XCTAssertTrue(configuration.isNamedDevelopmentBundle)
    XCTAssertFalse(configuration.allowsSparkleUpdates)
  }

  func testAutomationBridgeCannotBeForcedOnForAnExternalPreview() {
    let contaminatedEnvironment = ["OMI_ENABLE_LOCAL_AUTOMATION": "1"]

    XCTAssertFalse(
      DesktopAutomationLaunchOptions.isEnabled(
        allowsLocalAutomation: false,
        arguments: ["omi", DesktopAutomationLaunchOptions.enableFlag],
        environment: contaminatedEnvironment
      )
    )
    XCTAssertTrue(
      DesktopAutomationLaunchOptions.isEnabled(
        allowsLocalAutomation: true,
        arguments: ["omi"],
        environment: contaminatedEnvironment
      )
    )
  }
}
