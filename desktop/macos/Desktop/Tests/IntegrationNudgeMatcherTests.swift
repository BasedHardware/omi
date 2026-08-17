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

  /// A bare product name fires on any page that merely mentions the tool, so
  /// browser keywords are domains wherever the real title carries one.
  func testAPageAboutAToolIsNotThatTool() {
    XCTAssertNil(match(bundle: "com.google.Chrome", title: "ChatGPT vs Claude — a comparison"))
    XCTAssertNil(match(bundle: "com.google.Chrome", title: "anthropics/claude-code: the CLI"))
    XCTAssertNil(match(bundle: "com.google.Chrome", title: "Notion alternatives in 2026 — Blog"))
  }

  func testTheRealSiteTitlesStillMatch() {
    XCTAssertEqual(
      match(bundle: "com.google.Chrome", title: "Omi — chatgpt.com")?.entry.route,
      .exportDestination("chatgpt")
    )
    XCTAssertEqual(
      match(bundle: "com.google.Chrome", title: "New chat \\ claude.ai")?.entry.route,
      .exportDestination("claude")
    )
    XCTAssertEqual(
      match(bundle: "com.google.Chrome", title: "Roadmap — notion.so")?.entry.route,
      .exportDestination("notion")
    )
  }

  func testBrowserTitleMatchesASite() {
    let result = match(bundle: "com.google.Chrome", title: "Inbox (42) - me@example.com - Gmail")
    XCTAssertEqual(result?.entry.route, .importConnector("email"))
    XCTAssertEqual(result?.trigger.kind, .browserSite)
  }

  func testBrowserTitleMatchIsCaseInsensitive() {
    XCTAssertEqual(
      match(bundle: "com.apple.Safari", title: "Roadmap – NOTION.SO")?.entry.route,
      .exportDestination("notion")
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

  /// A plain substring match makes every short keyword claim a neighbourhood of
  /// unrelated sites — `x.com` matching `max.com` is the worst case, because a
  /// wrong nudge is worse than a missing one.
  func testAKeywordInsideALongerWordIsNotAMatch() {
    XCTAssertNil(match(bundle: "com.google.Chrome", title: "Max — max.com"))
    XCTAssertNil(match(bundle: "com.google.Chrome", title: "Watch on hbomax.com"))
  }

  func testTheSameKeywordStillMatchesAsItsOwnToken() {
    XCTAssertEqual(
      match(bundle: "com.google.Chrome", title: "Home / x.com")?.entry.route,
      .importConnector("x")
    )
    XCTAssertEqual(
      match(bundle: "com.google.Chrome", title: "(3) twitter.com")?.entry.route,
      .importConnector("x")
    )
  }

  /// "Twitter" as a bare word matched any page that merely discussed Twitter.
  func testAPageAboutASiteIsNotThatSite() {
    XCTAssertNil(match(bundle: "com.google.Chrome", title: "Why I quit Twitter — Substack"))
  }

  func testTokenMatchingRules() {
    XCTAssertTrue(IntegrationNudgeMatcher.containsWholeToken("x.com", in: "home / x.com"))
    XCTAssertFalse(IntegrationNudgeMatcher.containsWholeToken("x.com", in: "max.com"))
    XCTAssertTrue(IntegrationNudgeMatcher.containsWholeToken("gmail", in: "inbox - gmail"))
    XCTAssertFalse(IntegrationNudgeMatcher.containsWholeToken("gmail", in: "gmailify settings"))
    XCTAssertFalse(IntegrationNudgeMatcher.containsWholeToken("", in: "anything"))
  }

  /// The browser allowlist decides whether a title is read at all, so a variant
  /// missing from it silently disables browser nudges for those users.
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
