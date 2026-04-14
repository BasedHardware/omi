import CoreGraphics
import XCTest

@testable import Omi_Computer

/// Tests for the "last known good captureable window" fallback policy in
/// `ScreenCaptureService.getActiveWindowInfoAsync()`. Issue #6640: a helper app
/// without a captureable window (LogiPluginService, Dock, UserNotificationCenter)
/// used to poison the cache with a nil-windowID snapshot, silently breaking
/// screen capture for up to `activeWindowCacheTTL` seconds per transition.
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

  // MARK: - Happy path

  func testSuccessfulResolutionOverwritesCache() async {
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "Safari", windowTitle: "GitHub", windowID: CGWindowID(42))
    }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertEqual(result.appName, "Safari")
    XCTAssertEqual(result.windowTitle, "GitHub")
    XCTAssertEqual(result.windowID, CGWindowID(42))

    let cached = ScreenCaptureService._peekActiveWindowCacheForTests()
    XCTAssertEqual(cached?.appName, "Safari")
    XCTAssertEqual(cached?.windowID, CGWindowID(42))
  }

  // MARK: - The bug: nil-window poisoning

  func testNilWindowIDResolutionDoesNotPoisonFreshCache() async {
    // Seed a fresh good snapshot (as if capture was working moments ago).
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date()
    )
    let seededSnapshot = ScreenCaptureService._peekActiveWindowCacheForTests()

    // Simulate frontmost switching to a helper app with no captureable window.
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "LogiPluginService", windowTitle: nil, windowID: nil)
    }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    // Caller sees the last known good window, not nil.
    XCTAssertEqual(result.windowID, CGWindowID(42))
    XCTAssertEqual(result.appName, "Safari")
    XCTAssertEqual(result.windowTitle, "GitHub")

    // Cache is unchanged: still the Safari snapshot, same timestamp.
    let cached = ScreenCaptureService._peekActiveWindowCacheForTests()
    XCTAssertEqual(cached, seededSnapshot)
  }

  func testNilWindowIDResolutionWithNoCacheReturnsResolvedAsIs() async {
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "LogiPluginService", windowTitle: nil, windowID: nil)
    }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertEqual(result.appName, "LogiPluginService")
    XCTAssertNil(result.windowID)
    XCTAssertNil(result.windowTitle)
    XCTAssertNil(
      ScreenCaptureService._peekActiveWindowCacheForTests(),
      "nil-windowID result must not be written to the cache"
    )
  }

  func testExpiredCacheIsNotReusedForNilWindowResolution() async {
    // Seed an expired snapshot (>activeWindowCacheTTL in the past). The service
    // uses 2s TTL, so 10s ago is safely expired.
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date().addingTimeInterval(-10)
    )

    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "LogiPluginService", windowTitle: nil, windowID: nil)
    }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    // Expired cache must not be used; resolver's raw nil-window result is returned.
    XCTAssertEqual(result.appName, "LogiPluginService")
    XCTAssertNil(result.windowID)
  }

  // MARK: - Timeout path

  func testTimeoutPathWithFreshCacheStillFallsBack() async {
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date()
    )

    // Simulate the resolver hitting the timeout race (returning nil).
    ScreenCaptureService._resolverOverrideForTests = { nil }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertEqual(result.windowID, CGWindowID(42))
    XCTAssertEqual(result.appName, "Safari")
  }

  func testTimeoutPathWithNoCacheReturnsAllNil() async {
    ScreenCaptureService._resolverOverrideForTests = { nil }

    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertNil(result.appName)
    XCTAssertNil(result.windowTitle)
    XCTAssertNil(result.windowID)
  }

  // MARK: - Recovery

  func testSuccessfulResolutionAfterFallbackOverwritesCache() async {
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date()
    )

    // First: helper app transition -> fallback to Safari.
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "LogiPluginService", windowTitle: nil, windowID: nil)
    }
    _ = await ScreenCaptureService.getActiveWindowInfoAsync()

    // Then: user refocuses a real window.
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "Xcode", windowTitle: "Project.swift", windowID: CGWindowID(99))
    }
    let result = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertEqual(result.windowID, CGWindowID(99))
    XCTAssertEqual(result.appName, "Xcode")

    let cached = ScreenCaptureService._peekActiveWindowCacheForTests()
    XCTAssertEqual(cached?.windowID, CGWindowID(99))
    XCTAssertEqual(cached?.appName, "Xcode")
  }

  // MARK: - Fallback streak flag (P7)

  func testNilWindowFallbackStreakIsSetOnFirstFallbackAndIdempotent() async {
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date()
    )
    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "LogiPluginService", windowTitle: nil, windowID: nil)
    }

    XCTAssertFalse(ScreenCaptureService._peekNilWindowFallbackStreakForTests())

    _ = await ScreenCaptureService.getActiveWindowInfoAsync()
    XCTAssertTrue(
      ScreenCaptureService._peekNilWindowFallbackStreakForTests(),
      "first nil-window fallback should enter the streak"
    )

    _ = await ScreenCaptureService.getActiveWindowInfoAsync()
    _ = await ScreenCaptureService.getActiveWindowInfoAsync()
    XCTAssertTrue(
      ScreenCaptureService._peekNilWindowFallbackStreakForTests(),
      "consecutive nil-window fallbacks should stay in the streak (idempotent)"
    )
  }

  func testSuccessfulResolutionClearsNilWindowFallbackStreak() async {
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date()
    )
    ScreenCaptureService._forceNilWindowFallbackStreakForTests(true)

    ScreenCaptureService._resolverOverrideForTests = {
      (appName: "Xcode", windowTitle: "Project.swift", windowID: CGWindowID(99))
    }
    _ = await ScreenCaptureService.getActiveWindowInfoAsync()

    XCTAssertFalse(
      ScreenCaptureService._peekNilWindowFallbackStreakForTests(),
      "successful non-nil resolution must clear the streak"
    )
  }

  // MARK: - Test-only reset (P8)

  func testResetActiveWindowCacheClearsAllState() {
    ScreenCaptureService._seedActiveWindowCacheForTests(
      appName: "Safari",
      windowTitle: "GitHub",
      windowID: CGWindowID(42),
      resolvedAt: Date()
    )
    ScreenCaptureService._forceResolutionInFlightForTests(true)
    ScreenCaptureService._forceNilWindowFallbackStreakForTests(true)

    XCTAssertNotNil(ScreenCaptureService._peekActiveWindowCacheForTests())
    XCTAssertTrue(ScreenCaptureService._peekIsResolutionInFlightForTests())
    XCTAssertTrue(ScreenCaptureService._peekNilWindowFallbackStreakForTests())

    ScreenCaptureService._resetActiveWindowCacheForTests()

    XCTAssertNil(ScreenCaptureService._peekActiveWindowCacheForTests())
    XCTAssertFalse(ScreenCaptureService._peekIsResolutionInFlightForTests())
    XCTAssertFalse(ScreenCaptureService._peekNilWindowFallbackStreakForTests())
  }
}
