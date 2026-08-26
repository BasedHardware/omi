import AppKit
import XCTest

@testable import Omi_Computer

final class ScreenRecordingPermissionPolicyTests: XCTestCase {
  private func sourceFile(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
  }

  /// PERM-02 / BL-050: register the screen-recording TCC row while Omi is
  /// frontmost, then open Settings. The guided-grant helper must call
  /// requestAllScreenCapturePermissions() BEFORE openScreenRecordingPreferences(),
  /// and requestAll must activate before CGRequestScreenCaptureAccess(). A
  /// backgrounded request never creates the row (the Wave-11 failure).
  func testGuidedGrantRegistersBeforeOpeningSettings() throws {
    let src = try sourceFile("Sources/ScreenCaptureService.swift")
    guard let fn = src.range(of: "static func requestScreenRecordingAccessAndOpenSettings() {"),
      let end = src.range(of: "\n  }", range: fn.upperBound..<src.endIndex)?.lowerBound
    else { return XCTFail("requestScreenRecordingAccessAndOpenSettings must exist") }
    let body = String(src[fn.upperBound..<end])
    guard let reg = body.range(of: "requestAllScreenCapturePermissions()")?.lowerBound,
      let open = body.range(of: "openScreenRecordingPreferences()")?.lowerBound
    else { return XCTFail("helper must both register and open Settings") }
    XCTAssertLessThan(reg, open, "must register the TCC row before opening System Settings")

    guard let rfn = src.range(of: "static func requestAllScreenCapturePermissions() {"),
      let rend = src.range(of: "\n  }", range: rfn.upperBound..<src.endIndex)?.lowerBound
    else { return XCTFail("requestAllScreenCapturePermissions must exist") }
    let rbody = String(src[rfn.upperBound..<rend])
    guard let act = rbody.range(of: "NSApp.activate()")?.lowerBound,
      let cg = rbody.range(of: "CGRequestScreenCaptureAccess()")?.lowerBound
    else { return XCTFail("requestAll must activate and request") }
    XCTAssertLessThan(act, cg, "NSApp.activate() must precede CGRequestScreenCaptureAccess()")
  }

  /// The permission buttons must use the register-first helper, not the old
  /// open-Settings-then-asyncAfter-register anti-pattern that backgrounded the
  /// app before registering.
  func testPermissionButtonsUseRegisterFirstHelper() throws {
    // Positive guard: every screen-recording grant surface routes through the
    // register-first helper (each of these files had an open-then-register path).
    for path in [
      "Sources/MainWindow/Pages/PermissionsPage.swift",
      "Sources/MainWindow/SidebarView.swift",
      "Sources/Rewind/UI/RewindPage.swift",
      // DashboardPage's capture toggle now delegates to CaptureListeningLogic,
      // which owns the register-first screen-recording grant.
      "Sources/MainWindow/CaptureListeningLogic.swift",
      // OmiApp's menu-bar toggle now delegates to SystemCaptureControls, which owns the
      // register-first screen-recording grant for both the menu bar and the notch cluster.
      "Sources/FloatingControlBar/SystemCaptureControls.swift",
      "Sources/MainWindow/Pages/Settings/Components/SettingsContentView+BillingHelpers.swift",
      "Sources/MainWindow/RewindOnlyView.swift",
    ] {
      XCTAssertTrue(
        try sourceFile(path).contains("requestScreenRecordingAccessAndOpenSettings()"),
        "\(path) must route its screen-recording grant through the register-first helper")
    }
    // Negative guard: the register-after-open-Settings anti-pattern is gone.
    for path in [
      "Sources/MainWindow/Pages/PermissionsPage.swift",
      "Sources/MainWindow/SidebarView.swift",
      "Sources/Rewind/UI/RewindPage.swift",
      "Sources/MainWindow/Pages/DashboardPage.swift",
      "Sources/MainWindow/CaptureListeningLogic.swift",
    ] {
      let src = try sourceFile(path)
      XCTAssertNil(
        src.range(
          of:
            "openScreenRecordingPreferences\\([\\s\\S]{0,240}(requestAllScreenCapturePermissions|triggerScreenRecordingPermission)",
          options: .regularExpression),
        "\(path) still opens Settings before requesting screen-recording access")
    }
  }

  func testUiPermissionFollowsTccGrant() {
    XCTAssertTrue(ScreenRecordingPermissionPolicy.uiPermissionGranted(tccGranted: true))
    XCTAssertFalse(ScreenRecordingPermissionPolicy.uiPermissionGranted(tccGranted: false))
  }

  func testDeniedScreenRecordingAlwaysRoutesToSettings() {
    XCTAssertEqual(
      ScreenCaptureService.screenRecordingRequestDestination(hasPermissionNow: true),
      .alreadyGranted)
    XCTAssertEqual(
      ScreenCaptureService.screenRecordingRequestDestination(hasPermissionNow: false),
      .systemSettings)
  }

  @MainActor
  func testDragPayloadIsAFileURL() {
    let appURL = URL(fileURLWithPath: "/Applications/omi-screen-drag-test.app")
    let pasteboard = NSPasteboard(name: .init("omi-screen-recording-drag-test"))
    pasteboard.clearContents()

    XCTAssertTrue(
      pasteboard.writeObjects([AppBundleDragSourceNSView.pasteboardWriter(for: appURL)]))
    XCTAssertEqual(pasteboard.string(forType: .fileURL), appURL.absoluteString)
  }

  @MainActor
  func testDragSourceRendersIconBeforeInteraction() {
    let icon = NSImage(size: NSSize(width: 8, height: 8), flipped: false) { rect in
      NSColor.red.setFill()
      rect.fill()
      return true
    }
    let view = AppBundleDragSourceNSView(frame: NSRect(x: 0, y: 0, width: 32, height: 32))
    view.image = icon
    let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds)!
    view.cacheDisplay(in: view.bounds, to: bitmap)

    XCTAssertGreaterThan(bitmap.colorAt(x: 16, y: 16)?.alphaComponent ?? 0, 0.5)
  }

  @MainActor
  func testDragIconShrinksAsItEntersSystemSettings() {
    let settingsFrame = CGRect(x: 100, y: 100, width: 600, height: 500)

    XCTAssertEqual(
      AppBundleDragSourceNSView.dragIconSize(
        pointer: CGPoint(x: 80, y: 300), targetFrame: settingsFrame),
      AppBundleDragSourceNSView.fullDragIconSize)
    XCTAssertEqual(
      AppBundleDragSourceNSView.dragIconSize(
        pointer: CGPoint(x: 100, y: 300), targetFrame: settingsFrame),
      AppBundleDragSourceNSView.fullDragIconSize)
    XCTAssertEqual(
      AppBundleDragSourceNSView.dragIconSize(
        pointer: CGPoint(x: 140, y: 300), targetFrame: settingsFrame),
      AppBundleDragSourceNSView.compactDragIconSize)
  }

  @MainActor
  func testDragHelperSkipsFadeForReducedMotion() {
    XCTAssertEqual(CloudConnectorGuidanceOverlay.dragCardInitialAlpha(reduceMotion: false), 0)
    XCTAssertEqual(CloudConnectorGuidanceOverlay.dragCardInitialAlpha(reduceMotion: true), 1)
  }

  /// Regression for the reported detached icon: the draggable source must begin
  /// immediately beside the in-window permission list, not below the entire
  /// System Settings window.
  @MainActor
  func testDragCardStartsAdjacentToHighlightedPermissionList() {
    let visible = CGRect(x: 0, y: 0, width: 1_600, height: 1_000)
    let settings = CGRect(x: 600, y: 160, width: 800, height: 640)
    let card = CloudConnectorGuidanceOverlay.dragCardSize(appName: "Omi Dev")
    let target = CloudConnectorGuidanceOverlay.permissionListTargetFrame(in: settings)

    let frame = CloudConnectorGuidanceOverlay.dragCardFrame(
      target: target, cardSize: card, visibleFrame: visible)
    XCTAssertGreaterThan(target.midX, settings.midX, "target belongs in the Settings content pane")
    XCTAssertEqual(frame.maxX, target.minX - 16, accuracy: 0.001)
    XCTAssertEqual(frame.midY, target.midY, accuracy: 0.001)
    XCTAssertTrue(frame.intersection(target).isEmpty, "source must never cover the drop list")
    XCTAssertEqual(
      CloudConnectorGuidanceOverlay.dragCardDirection(cardFrame: frame, targetFrame: target),
      .right)
  }

  /// System Settings renders the Screen Recording list in the upper content
  /// pane, beneath its toolbar/header. The target must not fall into the lower
  /// pane merely because AppKit's Y axis starts at the bottom.
  @MainActor
  func testPermissionListTargetSitsInUpperContentPane() {
    let settings = CGRect(x: 600, y: 160, width: 800, height: 640)
    let target = CloudConnectorGuidanceOverlay.permissionListTargetFrame(in: settings)

    XCTAssertGreaterThan(target.midY, settings.midY)
    XCTAssertLessThan(settings.maxY - target.maxY, settings.height * 0.25)
    XCTAssertGreaterThanOrEqual(target.minY, settings.minY + settings.height * 0.5)
    XCTAssertGreaterThan(target.midX, settings.midX, "target belongs in the content pane")
  }

  /// Target and source geometry must follow a resized/moved System Settings
  /// window instead of drifting to a screen-relative fallback position.
  @MainActor
  func testPermissionListTargetAndSourceFollowSettingsResize() {
    let visible = CGRect(x: 0, y: 0, width: 1_800, height: 1_100)
    let initialSettings = CGRect(x: 200, y: 140, width: 760, height: 620)
    let movedSettings = CGRect(x: 680, y: 280, width: 920, height: 700)
    let card = CloudConnectorGuidanceOverlay.dragCardSize(appName: "Omi Dev")
    let initialTarget = CloudConnectorGuidanceOverlay.permissionListTargetFrame(in: initialSettings)
    let movedTarget = CloudConnectorGuidanceOverlay.permissionListTargetFrame(in: movedSettings)
    let movedCard = CloudConnectorGuidanceOverlay.dragCardFrame(
      target: movedTarget, cardSize: card, visibleFrame: visible)

    XCTAssertGreaterThan(movedTarget.width, initialTarget.width)
    XCTAssertGreaterThan(movedTarget.minX, initialTarget.minX)
    XCTAssertEqual(movedCard.maxX, movedTarget.minX - 16, accuracy: 0.001)
    XCTAssertEqual(movedCard.midY, movedTarget.midY, accuracy: 0.001)
  }

  @MainActor
  func testSettingsWindowFrameUsesWindowServerMetadataWithoutAccessibility() {
    let settingsPID: pid_t = 42
    let windows: [[String: Any]] = [
      [
        kCGWindowOwnerPID as String: settingsPID,
        kCGWindowLayer as String: 0,
        kCGWindowBounds as String: [
          "X": CGFloat(200), "Y": CGFloat(100), "Width": CGFloat(700), "Height": CGFloat(600),
        ],
      ],
      [
        kCGWindowOwnerPID as String: settingsPID,
        kCGWindowLayer as String: 0,
        kCGWindowBounds as String: [
          "X": CGFloat(250), "Y": CGFloat(150), "Width": CGFloat(300), "Height": CGFloat(200),
        ],
      ],
      [
        kCGWindowOwnerPID as String: pid_t(99),
        kCGWindowLayer as String: 0,
        kCGWindowBounds as String: ["X": CGFloat(0), "Y": CGFloat(0), "Width": CGFloat(1200), "Height": CGFloat(900)],
      ],
    ]

    let frame = CloudConnectorFormAutomation.appKitWindowFrame(pid: settingsPID, windows: windows)
    XCTAssertEqual(frame?.minX, 200)
    XCTAssertEqual(frame?.width, 700)
    XCTAssertEqual(frame?.height, 600)
  }

  @MainActor
  func testDragCardExpandsForLongBundleDisplayNames() {
    XCTAssertEqual(
      CloudConnectorGuidanceOverlay.dragCardSize(appName: "Omi Dev"),
      CGSize(width: 220, height: 190))
    XCTAssertEqual(
      CloudConnectorGuidanceOverlay.dragCardSize(appName: "omi-tool-stall-reliability"),
      CGSize(width: 260, height: 200))
  }

  func testCaptureKitFailureDoesNotOverrideGrantedTccPermission() {
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.shouldMarkCaptureKitBroken(tccGranted: true),
      "If System Settings/TCC says Screen Recording is granted, capture failures must not make the permission badge red"
    )
  }

  func testCaptureKitFailureDoesNotCreatePermissionFailureWhenTccIsDenied() {
    XCTAssertFalse(ScreenRecordingPermissionPolicy.shouldMarkCaptureKitBroken(tccGranted: false))
  }

  /// Regression: the onboarding request tool reopened System Settings (and the
  /// FDA drag card) even when the permission was already granted. Opening must
  /// stay behind a granted check, like the notifications/automation cases.
  func testRequestToolOpensSettingsOnlyWhenDenied() throws {
    // omi-test-quality: source-inspection -- static contract: the tool's
    // NSWorkspace/System Settings side effects cannot be exercised hermetically.
    let src = try sourceFile("Sources/Providers/ChatToolExecutor.swift")
    for (caseStart, caseEnd, grantedGuard, pane) in [
      ("case \"screen_recording\":", "case \"microphone\":", "if !screenRecordingGranted {", "Privacy_ScreenCapture"),
      ("case \"full_disk_access\":", "default:", "if !checkFullDiskAccessDirectly() {", "Privacy_AllFiles"),
    ] {
      guard let start = src.range(of: caseStart)?.upperBound,
        let end = src.range(of: caseEnd, range: start..<src.endIndex)?.lowerBound
      else { return XCTFail("request tool must handle \(caseStart)") }
      let body = String(src[start..<end])
      guard let guardPos = body.range(of: grantedGuard)?.lowerBound,
        let openPos = body.range(of: pane)?.lowerBound
      else { return XCTFail("\(caseStart) must guard its \(pane) open behind \(grantedGuard)") }
      XCTAssertLessThan(
        guardPos, openPos,
        "\(caseStart): opening \(pane) must sit inside the not-granted branch")
    }
  }

  /// Regression: the onboarding "Reopen Omi" prompt looped forever because the
  /// offer was static step config with no memory of restarts. The offer must
  /// fire only for a grant that arrived during this process's lifetime.
  func testRelaunchOfferedOnlyForGrantsArrivingWhileRunning() {
    XCTAssertTrue(
      ScreenRecordingPermissionPolicy.needsRelaunchToApply(
        grantedNow: true, grantedAtLaunch: false),
      "granted while running → capture is dead until relaunch, offer the reopen")
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.needsRelaunchToApply(
        grantedNow: true, grantedAtLaunch: true),
      "already granted at launch (incl. right after a reopen) → never re-offer")
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.needsRelaunchToApply(
        grantedNow: false, grantedAtLaunch: false),
      "not granted → nothing to apply")
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.needsRelaunchToApply(
        grantedNow: false, grantedAtLaunch: true),
      "revoked while running → a relaunch can't help; the grant flow handles it")
  }

  func testScreenCaptureKitInvokedOnlyWhenGrantWasLiveAtLaunch() {
    XCTAssertTrue(
      ScreenRecordingPermissionPolicy.shouldInvokeScreenCaptureKit(grantedAtLaunch: true),
      "SCK is usable when this process launched with Screen Recording already granted")
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.shouldInvokeScreenCaptureKit(grantedAtLaunch: false),
      "an in-session first grant is not live on this window-server connection")
  }

  func testFirstGrantPathsDoNotCallScreenCaptureKitUntilRelaunch() throws {
    // omi-test-quality: source-inspection -- static contract: SCK abort after an
    // in-session first grant is not reproducible in XCTest without a WindowServer
    // connection that predates TCC; every SCK entry must consult the policy gate.
    let src = try sourceFile("Sources/ScreenCaptureService.swift")
    XCTAssertTrue(src.contains("requestScreenCaptureKitPermissionIfUsableInThisProcess()"))
    XCTAssertTrue(
      src.contains("ScreenRecordingPermissionPolicy.shouldInvokeScreenCaptureKit("),
      "ScreenCaptureService must consult the launch-time SCK gate")

    guard let rfn = src.range(of: "static func requestAllScreenCapturePermissions() {"),
      let rend = src.range(of: "\n  }", range: rfn.upperBound..<src.endIndex)?.lowerBound
    else { return XCTFail("requestAllScreenCapturePermissions must exist") }
    let rbody = String(src[rfn.upperBound..<rend])
    XCTAssertTrue(
      rbody.contains("requestScreenCaptureKitPermissionIfUsableInThisProcess()"),
      "requestAll must not call SCK until the grant is live in this process")
    XCTAssertFalse(
      rbody.contains("await requestScreenCaptureKitPermission()"),
      "requestAll must not call raw SCK after the first TCC dialog")

    guard
      let pfn = src.range(of: "static func primeCaptureConsent() async {"),
      let pend = src.range(of: "\n  }", range: pfn.upperBound..<src.endIndex)?.lowerBound
    else { return XCTFail("primeCaptureConsent must exist") }
    let pbody = String(src[pfn.upperBound..<pend])
    XCTAssertTrue(
      pbody.contains("shouldInvokeScreenCaptureKit"),
      "primeCaptureConsent must skip SCK when the grant arrived after launch")

    let onboarding = try sourceFile("Sources/Onboarding/SecondBrain/SBOnboardingModel+Steps.swift")
    guard let ofn = onboarding.range(of: "func primeScreenCaptureConsentIfNeeded() {"),
      let oend = onboarding.range(of: "\n  }", range: ofn.upperBound..<onboarding.endIndex)?
        .lowerBound
    else { return XCTFail("primeScreenCaptureConsentIfNeeded must exist") }
    let obody = String(onboarding[ofn.upperBound..<oend])
    XCTAssertTrue(
      obody.contains("shouldInvokeScreenCaptureKit"),
      "onboarding must not prime SCK until a relaunch makes the grant live")
    XCTAssertTrue(
      obody.contains("screenRecordingGrantedAtLaunch"),
      "onboarding must use AppState's launch-time snapshot, not a post-grant preflight")
  }

  func testScreenCaptureRestartsUseSharedRelaunchCommand() throws {
    let src = try sourceFile("Sources/ScreenCaptureService.swift")
    XCTAssertTrue(src.contains("static func screenCaptureRelaunchCommand(appPath: String) -> String"))
    XCTAssertTrue(src.contains("AppState.relaunchCommand("))

    guard let softRange = src.range(of: "static func softRecoveryAndRestart()"),
      let resetRange = src.range(of: "static func resetScreenCapturePermissionAndRestart()")
    else { return XCTFail("screen-capture restart helpers must exist") }
    let softSnippet = String(src[softRange.lowerBound...]).prefix(4200)
    let resetSnippet = String(src[resetRange.lowerBound...]).prefix(3000)

    XCTAssertTrue(softSnippet.contains("screenCaptureRelaunchCommand(appPath: bundleURL.path)"))
    XCTAssertTrue(resetSnippet.contains("screenCaptureRelaunchCommand(appPath: bundleURL.path)"))
    XCTAssertFalse(softSnippet.contains("sleep 0.5 && open"))
    XCTAssertFalse(resetSnippet.contains("sleep 0.5 && open"))
  }

  /// Regression: first run on a new Mac restarted the app three times in 45 seconds, mid
  /// onboarding, on permission pages that have nothing to do with screen recording
  /// (0.12.187, macOS 15.1). Capture legitimately fails before the grant exists, the failure
  /// tracker read that as a broken install, and the recovery path terminates and relaunches
  /// the process. The "already recovered once" flag lives in the process it just killed, so
  /// the fresh process did it again.
  func testCaptureRecoveryNeverRestartsDuringOnboardingOrBeforeTheGrantIsLive() {
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.mayRestartToRecoverCapture(
        grantedAtLaunch: false, onboardingComplete: false),
      "a new Mac mid-onboarding must never be restarted by capture recovery")
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.mayRestartToRecoverCapture(
        grantedAtLaunch: true, onboardingComplete: false),
      "still onboarding: the reopen prompt owns relaunch, not the recovery path")
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.mayRestartToRecoverCapture(
        grantedAtLaunch: false, onboardingComplete: true),
      "a grant that is not live in this process cannot be repaired by restarting again")
    XCTAssertTrue(
      ScreenRecordingPermissionPolicy.mayRestartToRecoverCapture(
        grantedAtLaunch: true, onboardingComplete: true),
      "a granted, finished install may still restart to clear stale capture state")
  }

  /// The loop itself: every restart begins a process that would decide the same way again.
  func testTheRecoveryDecisionCannotLoopAcrossRestartsWhileOnboarding() {
    var restarts = 0
    for _ in 0..<5 {
      // Each iteration models a fresh process: per-session flags are back to their defaults
      // and the grant is still not live, which is exactly the state that repeated before.
      if ScreenRecordingPermissionPolicy.mayRestartToRecoverCapture(
        grantedAtLaunch: false, onboardingComplete: false)
      {
        restarts += 1
      }
    }
    XCTAssertEqual(restarts, 0, "the fix must hold on every relaunch, not just the first")
  }
}
