import XCTest

@testable import Omi_Computer

/// Guardrails for the `responseSpring` profile used by the floating bar's
/// AI response panel transitions. The spring constant controls how quickly
/// the panel settles after a query — too slow feels laggy, too fast feels
/// jumpy. These tests pin the profile so future tweaks are intentional.
///
/// Pattern adapted from `CaptureScreenToolTests.testCaptureScreenCaseExistsInSource`.
final class FloatingBarSpringAnimationTests: XCTestCase {

    // MARK: - Profile pin

    /// The helper exposes the spring's response and damping as separate
    /// constants so tests can assert on them directly. If a future change
    /// inlines the values (or drifts them), this test fails loudly.
    func testResponseSpringProfile() {
        XCTAssertEqual(
            FloatingControlBarWindow.responseSpringResponse, 0.18,
            "responseSpring response must stay at 0.18s (snappy but not jumpy)")
        XCTAssertEqual(
            FloatingControlBarWindow.responseSpringDampingFraction, 0.88,
            "responseSpring dampingFraction must stay at 0.88 (no overshoot)")
    }

    // MARK: - Source-level invariant

    /// All 6 previously-hardcoded `.spring(response: 0.4, dampingFraction: 0.8)`
    /// call sites must use the helper. If a future change adds a 7th call site
    /// with the old profile (or drifts the helper values), this test catches it.
    func testResponseSpringUsedAtAllCallSites() throws {
        let sourceFile = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // Tests/
            .deletingLastPathComponent()  // Desktop/
            .appendingPathComponent("Sources")
            .appendingPathComponent("FloatingControlBar")
            .appendingPathComponent("FloatingControlBarWindow.swift")

        let content = try String(contentsOf: sourceFile, encoding: .utf8)

        // Matches both `Self.responseSpring` (inside FloatingControlBarWindow's
        // own methods) and `FloatingControlBarWindow.responseSpring` (inside
        // FloatingBarManager's methods, where `Self` doesn't resolve to the
        // helper's enclosing type).
        let helperUsePattern = #"(?:Self|FloatingControlBarWindow)\.responseSpring"#
        let helperUseRegex = try NSRegularExpression(pattern: helperUsePattern)
        let helperUseCount = helperUseRegex.numberOfMatches(
            in: content, range: NSRange(content.startIndex..., in: content))

        // Strict match against the prior hardcoded profile.
        let oldProfilePattern = #"\.spring\(response:\s*0\.4,\s*dampingFraction:\s*0\.8\)"#
        let oldProfileRegex = try NSRegularExpression(pattern: oldProfilePattern)
        let oldProfileCount = oldProfileRegex.numberOfMatches(
            in: content, range: NSRange(content.startIndex..., in: content))

        XCTAssertGreaterThanOrEqual(
            helperUseCount, 6,
            "Expected >= 6 helper uses in FloatingControlBarWindow.swift, found \(helperUseCount). "
            + "Each `withAnimation(Self.responseSpring)` or `withAnimation(FloatingControlBarWindow.responseSpring)` call site counts as one use.")
        XCTAssertEqual(
            oldProfileCount, 0,
            "Expected 0 remaining `.spring(response: 0.4, dampingFraction: 0.8)` literals, found \(oldProfileCount). "
            + "All such sites must use the responseSpring helper.")

        // Sanity: the out-of-scope `.spring(response: 0.3, dampingFraction: 0.88)`
        // at the clear-visible-conversation call site must be untouched.
        let outOfScopePattern = #"\.spring\(response:\s*0\.3,\s*dampingFraction:\s*0\.88\)"#
        let outOfScopeRegex = try NSRegularExpression(pattern: outOfScopePattern)
        let outOfScopeCount = outOfScopeRegex.numberOfMatches(
            in: content, range: NSRange(content.startIndex..., in: content))
        XCTAssertEqual(
            outOfScopeCount, 1,
            "Expected exactly 1 `.spring(response: 0.3, dampingFraction: 0.88)` (out-of-scope clear-conversation site), found \(outOfScopeCount).")
    }
}
