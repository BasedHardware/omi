import XCTest

@testable import Omi_Computer

/// Recognition is the half of this feature that can be *wrong* rather than
/// merely absent. A false positive interrupts a user about an app they are not
/// using, so each heuristic gets a test for what it must not match.
final class IntegrationNudgeMatcherTests: XCTestCase {
  private func match(bundle: String?, title: String? = nil) -> IntegrationNudgeMatcher.Match? {
    IntegrationNudgeMatcher.match(
      IntegrationNudgeMatcher.Window(bundleIdentifier: bundle, windowTitle: title)
    )
  }

  func testNativeAppMatchesByBundleIdentifier() {
    let result = match(bundle: "com.apple.Notes")
    XCTAssertEqual(result?.entry.route, .importConnector("apple-notes"))
    XCTAssertEqual(result?.trigger.kind, .nativeApp)
  }

  func testBrowserTitleMatchesASite() {
    let result = match(bundle: "com.google.Chrome", title: "Inbox (42) - me@example.com - Gmail")
    XCTAssertEqual(result?.entry.route, .importConnector("email"))
    XCTAssertEqual(result?.trigger.kind, .browserSite)
  }

  func testBrowserTitleMatchIsCaseInsensitive() {
    XCTAssertEqual(
      match(bundle: "com.apple.Safari", title: "Swift concurrency - CHATGPT")?.entry.route,
      .exportDestination("chatgpt")
    )
  }

  /// A title is only a site signal inside a browser. A text editor with
  /// "Gmail integration notes" open is not the user reading their mail.
  func testTitleIsIgnoredOutsideABrowser() {
    XCTAssertNil(match(bundle: "com.apple.TextEdit", title: "Gmail integration notes.txt"))
  }

  /// Without Screen Recording there is no window title, so browser triggers
  /// degrade to nothing rather than to a guess.
  func testBrowserWithoutATitleDoesNotMatch() {
    XCTAssertNil(match(bundle: "com.google.Chrome"))
    XCTAssertNil(match(bundle: "com.google.Chrome", title: ""))
  }

  /// ChatGPT.app's own window title also contains "ChatGPT". The bundle
  /// identifier is a fact and the title is a guess, so the fact must win —
  /// otherwise the same open app is reported under two different trigger kinds
  /// depending on which one the loop happened to reach first.
  func testNativeAppTriggersOutrankBrowserTitleTriggers() {
    let result = match(bundle: "com.openai.chat", title: "ChatGPT")
    XCTAssertEqual(result?.trigger.kind, .nativeApp)
    XCTAssertEqual(result?.trigger.id, "chatgpt_app")
  }

  func testUnknownAppDoesNotMatch() {
    XCTAssertNil(match(bundle: "com.example.SomeRandomApp"))
    XCTAssertNil(match(bundle: nil))
  }

  /// The site's own name lives at the end of a real title, so anchoring there
  /// is what separates "Home / X" from "Why I quit Twitter — Substack".
  func testMatchingIsAnchoredToTheEndOfTheTitle() {
    XCTAssertEqual(
      match(bundle: "com.google.Chrome", title: "(3) Home / X")?.entry.route,
      .importConnector("x")
    )
    XCTAssertNil(match(bundle: "com.google.Chrome", title: "X marks the spot — Blog"))
    XCTAssertNil(match(bundle: "com.google.Chrome", title: "ChatGPT vs Claude — a comparison"))
  }

  /// Browsers append their own product name to the window title; the site name
  /// is still the end of the page's title.
  func testBrowserChromeSuffixIsStripped() {
    XCTAssertEqual(
      match(bundle: "com.google.Chrome", title: "ChatGPT - Google Chrome")?.entry.route,
      .exportDestination("chatgpt")
    )
    XCTAssertEqual(
      IntegrationNudgeMatcher.normalizedTitle("Home / X - Google Chrome"), "home / x")
  }

  func testBrowserVariantsAreRecognized() {
    for identifier in [
      "com.microsoft.edgemac.Beta", "com.brave.Browser.nightly",
      "com.operasoftware.OperaGX", "com.openai.atlas",
    ] {
      XCTAssertTrue(
        IntegrationNudgeMatcher.isBrowser(bundleIdentifier: identifier),
        "\(identifier) should be treated as a browser"
      )
    }
  }

  func testBrowserDetection() {
    XCTAssertTrue(IntegrationNudgeMatcher.isBrowser(bundleIdentifier: "com.apple.Safari"))
    XCTAssertTrue(IntegrationNudgeMatcher.isBrowser(bundleIdentifier: "company.thebrowser.Browser"))
    XCTAssertFalse(IntegrationNudgeMatcher.isBrowser(bundleIdentifier: "com.apple.Notes"))
    XCTAssertFalse(IntegrationNudgeMatcher.isBrowser(bundleIdentifier: nil))
  }

  /// Entries with no trigger carry onboarding copy only; they must never be
  /// reachable from the recognition path.
  func testEntriesWithoutTriggersAreNeverMatched() {
    let untriggered = IntegrationNudgeCatalog.all.filter { $0.triggers.isEmpty }
    XCTAssertFalse(untriggered.isEmpty, "test is vacuous if every entry has a trigger")
    for entry in untriggered {
      XCTAssertFalse(
        IntegrationNudgeCatalog.nudgeable.contains(where: { $0.telemetryID == entry.telemetryID })
      )
    }
  }

  /// The card's identity must round-trip through the notification action, which
  /// carries only the telemetry id.
  func testEveryNudgeableEntryIsRecoverableFromItsTelemetryID() {
    for entry in IntegrationNudgeCatalog.nudgeable {
      let recovered = IntegrationNudgeCatalog.all.first { $0.telemetryID == entry.telemetryID }
      XCTAssertEqual(recovered?.route, entry.route)
    }
  }
}
