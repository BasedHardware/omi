import AppKit
import XCTest

@testable import Omi_Computer

/// The onboarding "Use Omi memory where you work" step (and the matching home
/// stack) must show a real brand mark for every destination even on a machine
/// where none of the apps are installed. Regression coverage for icons falling
/// back to a generic gray SF Symbol when the hardcoded /Applications path was
/// missing and no bundled logo existed (Notion, ChatGPT, Claude).
final class ConnectorBrandIconResourceTests: XCTestCase {

  /// Every brand the onboarding exports step can display, minus the ones whose
  /// icon intentionally comes from elsewhere (agents → emoji, localFiles →
  /// system folder icon, appleNotes → always-present system app, x → glyph).
  private let brandsRequiringBundledLogo: [ConnectorBrand] = [
    .notion, .obsidian, .chatgpt, .claude, .claudeCode, .codex,
    .openclaw, .hermes, .gemini, .gmail, .calendar,
  ]

  func testEveryOnboardingBrandResolvesABundledLogo() {
    for brand in brandsRequiringBundledLogo {
      let url = ConnectorBrandImageLoader.bundledImageURL(for: brand)
      XCTAssertNotNil(url, "brand \(brand.rawValue) has no bundled logo — it would render as a generic symbol")
      if let url {
        XCTAssertNotNil(NSImage(contentsOf: url), "bundled logo for \(brand.rawValue) is not a loadable image")
      }
    }
  }
}
