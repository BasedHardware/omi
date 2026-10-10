import CoreGraphics
import XCTest

@testable import Omi_Computer

/// Every refusal the floor makes, and the target resolution before it.
final class UIAutomationTargetPolicyTests: XCTestCase {
  private let ownPID: pid_t = 100

  private func app(
    _ bundleID: String, pid: pid_t = 812, name: String? = "TextEdit", active: Bool = false
  ) -> UIAutomationRunningApp {
    UIAutomationRunningApp(
      pid: pid, bundleID: bundleID, localizedName: name,
      bundleURL: URL(fileURLWithPath: "/Applications/\(name ?? "Unnamed").app"), isActive: active)
  }

  private func refusal(
    _ app: UIAutomationRunningApp, excluded: Set<String> = [], secureInput: Bool = false
  ) -> String? {
    UIAutomationTargetPolicy.refusal(
      for: app, ownPID: ownPID, isExcludedFromCapture: { excluded.contains($0) }, isSecureInputActive: secureInput
    )?.reason
  }

  func testBundleIDsAreTrimmedLowercasedAndShapeChecked() {
    XCTAssertEqual(UIAutomationTargetPolicy.normalizedBundleID("  com.apple.TextEdit "), "com.apple.textedit")
    XCTAssertEqual(UIAutomationTargetPolicy.normalizedBundleID("dev.warp.Warp-Stable"), "dev.warp.warp-stable")
    for bad: Any? in [nil, 42, "", "TextEdit", "com..apple", "com.apple.Text Edit", "com.apple.textedit;rm", ".com.x"] {
      XCTAssertNil(UIAutomationTargetPolicy.normalizedBundleID(bad), "\(String(describing: bad))")
    }
    XCTAssertNil(UIAutomationTargetPolicy.normalizedBundleID("a." + String(repeating: "b", count: 260)))
  }

  func testTheTargetIsTheOneRunningCopyMatchedWithoutCase() {
    let running = [app("com.apple.TextEdit", pid: 812), app("com.apple.Notes", pid: 900, name: "Notes")]

    XCTAssertEqual(
      try UIAutomationTargetPolicy.resolve(bundleID: "com.apple.textedit", pid: nil, running: running).get().pid, 812)
    XCTAssertEqual(
      failureReason(UIAutomationTargetPolicy.resolve(bundleID: "com.apple.mail", pid: nil, running: running)),
      "app_not_running")
    XCTAssertEqual(
      failureReason(UIAutomationTargetPolicy.resolve(bundleID: "com.apple.textedit", pid: 900, running: running)),
      "target_mismatch", "a pid must belong to the approved bundle")

    let twoCopies = running + [app("com.apple.TextEdit", pid: 813)]
    let ambiguous = UIAutomationTargetPolicy.resolve(bundleID: "com.apple.textedit", pid: nil, running: twoCopies)
    XCTAssertEqual(failureReason(ambiguous), "ambiguous_app")
    if case .failure(let failure) = ambiguous { XCTAssertEqual(failure.candidatePIDs, [812, 813]) }
    XCTAssertEqual(
      try UIAutomationTargetPolicy.resolve(bundleID: "com.apple.textedit", pid: 813, running: twoCopies).get().pid, 813)
  }

  func testOmiItselfIsRefusedByProcessAndByEveryOmiBundle() {
    XCTAssertEqual(refusal(app("com.apple.TextEdit", pid: ownPID)), "refused_own_app")
    XCTAssertEqual(refusal(app("com.omi.computer-macos.beta")), "refused_own_app")
    XCTAssertEqual(refusal(app("com.omi.omi-sauransh-test")), "refused_own_app")
  }

  func testEachRefusedCategoryIsRefusedBeforeAnythingIsRead() {
    for bundleID in [
      "com.apple.SecurityAgent", "com.apple.loginwindow", "com.apple.keychainaccess", "com.apple.Passwords",
      "com.apple.Terminal", "com.googlecode.iterm2", "dev.warp.Warp-Stable", "com.1password.1password",
      "com.bitwarden.desktop", "com.apple.Passwords.MenuBarExtra", "com.apple.AutoFillPanelService",
      "com.apple.notificationcenterui", "com.apple.UserNotificationCenter", "com.apple.Users-Groups-Settings.extension",
      "com.apple.SafariPlatformSupport.Helper", "com.apple.AuthenticationServices.Helper",
    ] {
      XCTAssertEqual(refusal(app(bundleID, name: "App")), "refused_app", bundleID)
    }
  }

  func testTheGeneratedFloorMatchesTheKernelsList() {
    // The kernel's list is the source; this pins that the generated copy is
    // lowercased and carries each refused category.
    let refused = GeneratedUIAutomationSafetyFloor.refusedBundleIDs
    XCTAssertTrue(refused.allSatisfy { $0 == $0.lowercased() })
    XCTAssertTrue(refused.isSuperset(of: ["com.apple.terminal", "com.apple.securityagent", "com.1password.1password"]))
    XCTAssertFalse(refused.contains(GeneratedUIAutomationSafetyFloor.paneCheckedBundleID))
    XCTAssertEqual(GeneratedUIAutomationSafetyFloor.refusedBundleIDPrefixes, ["com.omi."])
  }

  func testAnAppExtensionOrAnAppWithNoNameIsRefused() {
    let appex = UIAutomationRunningApp(
      pid: 900, bundleID: "com.apple.settings.example.extension", localizedName: "Example",
      bundleURL: URL(fileURLWithPath: "/System/Library/ExtensionKit/Extensions/Example.appex"), isActive: false)
    XCTAssertEqual(refusal(appex), "refused_not_an_app")
    for path in [
      "/System/Library/Frameworks/AuthenticationServices.framework/XPCServices/AuthenticationServicesHelper.xpc",
      "/usr/libexec/someagent",
    ] {
      let service = UIAutomationRunningApp(
        pid: 901, bundleID: "com.apple.example.helper", localizedName: "Helper", bundleURL: URL(fileURLWithPath: path),
        isActive: false)
      XCTAssertEqual(refusal(service), "refused_not_an_app", path)
    }
    let noBundle = UIAutomationRunningApp(
      pid: 902, bundleID: "com.example.tool", localizedName: "Tool", bundleURL: nil, isActive: false)
    XCTAssertEqual(refusal(noBundle), "refused_not_an_app")
    XCTAssertEqual(refusal(app("com.apple.Settings.PrivacySecurity.extension", name: "Privacy")), "refused_app")
    XCTAssertEqual(refusal(app("com.example.nameless", name: nil)), "refused_unnamed_app")
    XCTAssertEqual(refusal(app("com.example.nameless", name: "  ")), "refused_unnamed_app")
  }

  func testAppsExcludedFromCaptureAreRefusedByTheirName() {
    XCTAssertEqual(refusal(app("com.apple.TextEdit"), excluded: ["TextEdit"]), "refused_excluded_app")
    XCTAssertNil(refusal(app("com.apple.TextEdit"), excluded: ["Notes"]))
  }

  func testSecureInputRefusesOnlyTheFrontmostApp() {
    XCTAssertEqual(refusal(app("com.apple.Safari", active: true), secureInput: true), "refused_secure_input")
    XCTAssertNil(refusal(app("com.apple.Safari", active: false), secureInput: true))
    XCTAssertNil(refusal(app("com.apple.Safari", active: true), secureInput: false))
  }

  func testSystemSettingsIsNotRefusedOutrightButHasItsPaneChecked() {
    XCTAssertNil(refusal(app("com.apple.systempreferences", name: "System Settings")))
    XCTAssertTrue(UIAutomationTargetPolicy.isPaneChecked("com.apple.systempreferences"))
    XCTAssertFalse(UIAutomationTargetPolicy.isPaneChecked("com.apple.textedit"))
  }

  func testTheAssistiveTreeModeComesFromTheAppsOwnBundleLayout() {
    let url = URL(fileURLWithPath: "/Applications/Example.app")
    let electron = UIAutomationTargetPolicy.assistiveTreeMode(
      bundleURL: url, fileExists: { $0.hasSuffix("Electron Framework.framework") }, frameworks: { _ in [] })
    let chromium = UIAutomationTargetPolicy.assistiveTreeMode(
      bundleURL: url,
      fileExists: { $0.hasSuffix("Example Framework.framework/Versions/Current/Resources/chrome_100_percent.pak") },
      frameworks: { _ in ["Sparkle.framework", "Example Framework.framework"] })
    let native = UIAutomationTargetPolicy.assistiveTreeMode(
      bundleURL: url, fileExists: { _ in false }, frameworks: { _ in ["Sparkle.framework"] })

    XCTAssertEqual(electron, .electron)
    XCTAssertEqual(chromium, .chromium)
    XCTAssertEqual(native, .none)
    XCTAssertEqual(UIAutomationTargetPolicy.assistiveTreeMode(bundleURL: nil), .none)
  }

  private func failureReason(_ result: Result<UIAutomationRunningApp, UIAutomationTargetFailure>) -> String? {
    if case .failure(let failure) = result { return failure.reason }
    return nil
  }
}
