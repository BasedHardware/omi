import XCTest

@testable import Omi_Computer

/// Behavior of `AppIconCache.getIcon(for:size:)` — the name→icon resolution used by
/// the Excluded Apps rows (and every other `AppIconView`). Resolution is entirely
/// local (NSWorkspace + filesystem scan of the standard app folders); these tests
/// pin the observable contract of each lookup stage without touching the network.
final class AppIconCacheTests: XCTestCase {

  /// Stage 1 (exact path match): a system app that always lives in
  /// /System/Applications resolves by its exact name.
  func testExactNameResolvesSystemApp() async {
    let icon = (await AppIconCache.shared.getIcon(for: "Calculator", size: 24)).image
    XCTAssertNotNil(icon, "Calculator.app lives in /System/Applications and must resolve")
  }

  /// Resolved icons are resized to 2× the requested point size for retina.
  func testIconIsResizedToTwiceRequestedSize() async {
    guard let icon = (await AppIconCache.shared.getIcon(for: "TextEdit", size: 24)).image else {
      return XCTFail("TextEdit.app should resolve from /System/Applications")
    }
    XCTAssertEqual(icon.size.width, 48, accuracy: 0.5)
    XCTAssertEqual(icon.size.height, 48, accuracy: 0.5)
  }

  /// Stage 2 (case-insensitive directory scan): lowercase input still resolves.
  func testLowercaseNameResolvesViaCaseInsensitiveScan() async {
    let icon = (await AppIconCache.shared.getIcon(for: "calculator", size: 24)).image
    XCTAssertNotNil(icon, "case-insensitive scan should match Calculator.app")
  }

  /// Stage 2 also does substring matching — a distinctive fragment of an app
  /// name resolves to that app. (This is the fuzziness that can mis-attribute
  /// icons between similarly named apps; the test documents it as current
  /// behavior, not as an endorsement.)
  func testSubstringFragmentResolvesViaContainsMatch() async {
    let icon = (await AppIconCache.shared.getIcon(for: "extedi", size: 24)).image
    XCTAssertNotNil(icon, "'extedi' is a substring of TextEdit and should resolve via contains()")
  }

  /// Unknown names fall through every stage and return nil (the view then shows
  /// the letter-monogram fallback).
  func testUnknownAppReturnsNil() async {
    let icon = (await AppIconCache.shared.getIcon(for: "DefinitelyNotAnInstalledApp2026", size: 24)).image
    XCTAssertNil(icon)
  }

  /// CoreServices apps (Finder, Archive Utility) resolve without being in the
  /// classic /Applications folders — regression for the default excluded-apps
  /// list showing fallback icons.
  func testCoreServicesAppsResolve() async {
    let finder = (await AppIconCache.shared.getIcon(for: "Finder", size: 24)).image
    XCTAssertNotNil(finder, "Finder lives in /System/Library/CoreServices")
    let archiveUtility = (await AppIconCache.shared.getIcon(for: "Archive Utility", size: 24)).image
    XCTAssertNotNil(archiveUtility, "Archive Utility lives in CoreServices/Applications")
  }

  /// Renamed system apps resolve through their current name ("System
  /// Preferences" no longer exists on modern macOS; stored names may predate
  /// the System Settings rename).
  func testRenamedSystemAppResolvesThroughAlias() async {
    let icon = (await AppIconCache.shared.getIcon(for: "System Preferences", size: 24)).image
    XCTAssertNotNil(icon, "System Preferences should alias to System Settings")
  }

  /// Second lookup for the same name is served from NSCache — the exact same
  /// NSImage instance comes back, proving no re-resolution happens.
  func testSecondLookupHitsCache() async {
    let first = (await AppIconCache.shared.getIcon(for: "Calculator", size: 24)).image
    let second = (await AppIconCache.shared.getIcon(for: "Calculator", size: 24)).image
    XCTAssertNotNil(first)
    XCTAssertTrue(first === second, "cache hit must return the identical NSImage instance")
  }

  /// Diagnostic map of which lookup stage serves common names — logged, not
  /// asserted, because stages 3–4 depend on what is running/installed on the
  /// host. Run with `--filter AppIconCacheTests` and read the log to see how a
  /// given name is pulled.
  func testLogResolutionForCommonNames() async {
    let probes = [
      "Calculator",  // stage 1: exact /System/Applications path
      "safari",  // stage 2: case-insensitive scan of /Applications
      "Finder",  // stage 3 only: lives in CoreServices, resolves iff running
      "Passwords",  // default excluded app on macOS 15+
      "zoom.us",  // third-party, resolves only if installed
    ]
    for name in probes {
      let icon = (await AppIconCache.shared.getIcon(for: name, size: 24)).image
      print(
        "AppIconCacheTests: '\(name)' → \(icon == nil ? "nil (fallback symbol)" : "resolved \(Int(icon!.size.width))pt"))"
      )
    }
  }
}
