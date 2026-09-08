import CoreGraphics
import XCTest

@testable import Omi_Computer

final class ScreenCaptureResolverCacheTests: XCTestCase {
  override func setUp() {
    super.setUp()
    ScreenCaptureService._resetActiveWindowCacheForTests()
    ScreenCaptureService._resolverOverrideForTests = nil
  }

  override func tearDown() {
    ScreenCaptureService._resetActiveWindowCacheForTests()
    ScreenCaptureService._resolverOverrideForTests = nil
    super.tearDown()
  }

  func testSuccessfulResolutionOverwritesCache() async {
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "Safari", windowTitle: "GitHub", windowID: CGWindowID(42))
    }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertEqual(result.appName, "Safari")
    XCTAssertEqual(result.windowTitle, "GitHub")
    XCTAssertEqual(result.windowID, CGWindowID(42))
    XCTAssertEqual(ScreenCaptureService._peekActiveWindowCacheForTests()?.windowID, CGWindowID(42))
  }

  func testNoWindowResolutionUsesFreshCaptureableCacheWithoutPoisoningIt() async {
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date()
    )
    let seededSnapshot = ScreenCaptureService._peekActiveWindowCacheForTests()
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "Secure Surface", windowTitle: nil, windowID: nil)
    }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertEqual(result.appName, "Safari")
    XCTAssertEqual(result.windowTitle, "GitHub")
    XCTAssertEqual(result.windowID, CGWindowID(42))
    XCTAssertEqual(ScreenCaptureService._peekActiveWindowCacheForTests(), seededSnapshot)
  }

  func testSystemNoWindowResolutionSkipsFreshCaptureableCache() async {
    for systemApp in ["loginwindow", "ScreenSaverEngine"] {
      ScreenCaptureService._resetActiveWindowCacheForTests()
      ScreenCaptureService._seedActiveWindowCacheForTests(
        appName: "Safari",
        windowTitle: "GitHub",
        windowID: CGWindowID(42),
        resolvedAt: Date()
      )
      ScreenCaptureService._resolverOverrideForTests = {
        (appName: systemApp, windowTitle: nil, windowID: nil)
      }

      let result = await ScreenCaptureService.getActiveWindowInfoAsync()

      XCTAssertEqual(result.appName, systemApp)
      XCTAssertNil(result.windowID)
      XCTAssertEqual(ScreenCaptureService._peekActiveWindowCacheForTests()?.windowID, CGWindowID(42))
    }
  }

  func testNoWindowResolutionWithoutCacheDoesNotCreatePoisonedSnapshot() async {
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "Secure Surface", windowTitle: nil, windowID: nil)
    }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertEqual(result.appName, "Secure Surface")
    XCTAssertNil(result.windowID)
    XCTAssertNil(ScreenCaptureService._peekActiveWindowCacheForTests())
  }

  func testTimeoutUsesFreshCaptureableCache() async {
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date()
    )
    ScreenCaptureService._resolverOverrideForTests = { nil }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertEqual(result.appName, "Safari")
    XCTAssertEqual(result.windowID, CGWindowID(42))
  }

  func testExpiredCacheIsNotUsedForNoWindowResolution() async {
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date().addingTimeInterval(-10)
    )
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "Secure Surface", windowTitle: nil, windowID: nil)
    }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertEqual(result.appName, "Secure Surface")
    XCTAssertNil(result.windowID)
  }

  func testSuccessfulResolutionAfterNoWindowFallbackReplacesCache() async {
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date()
    )
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "Secure Surface", windowTitle: nil, windowID: nil)
    }
    _ = await ScreenCaptureService.getActiveWindowInfoAsync()

    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "Xcode", windowTitle: "Package.swift", windowID: CGWindowID(99))
    }
    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertEqual(result.appName, "Xcode")
    XCTAssertEqual(result.windowID, CGWindowID(99))
    XCTAssertEqual(ScreenCaptureService._peekActiveWindowCacheForTests()?.windowID, CGWindowID(99))
  }
}
