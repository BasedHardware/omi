import XCTest

@testable import Omi_Computer

final class AppInstallerTests: XCTestCase {

  // MARK: - Installer-location detection

  func testMountedDMGPathIsInstallerLocation() {
    XCTAssertTrue(AppInstaller.isInstallerLocation("/Volumes/Omi/Omi.app"))
    XCTAssertTrue(AppInstaller.isInstallerLocation("/Volumes/Omi/Omi.app"))
  }

  func testTranslocatedPathIsInstallerLocation() {
    XCTAssertTrue(
      AppInstaller.isInstallerLocation(
        "/private/var/folders/ab/x1/T/AppTranslocation/1B2F3C4D/d/Omi.app"))
  }

  func testInstalledAndDevPathsAreNotInstallerLocations() {
    XCTAssertFalse(AppInstaller.isInstallerLocation("/Applications/Omi.app"))
    XCTAssertFalse(AppInstaller.isInstallerLocation("/Applications/omi-fix-rewind.app"))
    // Local dev builds run from checkouts and temp build dirs — never gated.
    XCTAssertFalse(
      AppInstaller.isInstallerLocation("/Users/nik/projects/omi/desktop/macos/.build/Omi.app"))
    XCTAssertFalse(AppInstaller.isInstallerLocation("/Users/nik/Downloads/Omi.app"))
  }

  // MARK: - Install destination

  func testInstalledURLKeepsBundleName() {
    let url = AppInstaller.installedURL(
      forBundleURL: URL(fileURLWithPath: "/Volumes/Omi/Omi.app"))
    XCTAssertEqual(url.path, "/Applications/Omi.app")
  }

  // MARK: - Replace-vs-launch decision (never downgrade)

  func testReplacesOlderInstalledBuild() {
    XCTAssertTrue(AppInstaller.shouldReplaceInstalled(installedBuild: "100", sourceBuild: "101"))
  }

  func testDoesNotReplaceSameOrNewerInstalledBuild() {
    XCTAssertFalse(AppInstaller.shouldReplaceInstalled(installedBuild: "101", sourceBuild: "101"))
    XCTAssertFalse(AppInstaller.shouldReplaceInstalled(installedBuild: "102", sourceBuild: "101"))
  }

  func testNumericComparisonNotLexicographic() {
    // "9" < "10" numerically even though lexicographically "9" > "10".
    XCTAssertTrue(AppInstaller.shouldReplaceInstalled(installedBuild: "9", sourceBuild: "10"))
  }

  func testUnreadableInstalledBuildIsReplaced() {
    // A corrupt installed copy (no readable Info.plist) should not block install.
    XCTAssertTrue(AppInstaller.shouldReplaceInstalled(installedBuild: nil, sourceBuild: "101"))
  }

  func testUnreadableSourceBuildDoesNotOverwriteInstalled() {
    XCTAssertFalse(AppInstaller.shouldReplaceInstalled(installedBuild: "101", sourceBuild: nil))
  }

  // MARK: - Atomic replace

  func testCopyFailureLeavesExistingInstallIntact() throws {
    let fm = FileManager.default
    let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    try fm.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? fm.removeItem(at: root) }

    // Pre-existing "installed" bundle with known content.
    let destination = root.appendingPathComponent("Omi.app", isDirectory: true)
    try fm.createDirectory(at: destination, withIntermediateDirectories: true)
    let marker = destination.appendingPathComponent("build.txt")
    try "installed-101".write(to: marker, atomically: true, encoding: .utf8)

    // Source does not exist → copyItem throws (stands in for ENOSPC mid-copy).
    let missingSource = root.appendingPathComponent("FromDMG.app", isDirectory: true)

    XCTAssertThrowsError(
      try AppInstaller.replaceInstalledApp(source: missingSource, destination: destination),
      "a copy failure must propagate, not silently succeed")

    // The working install must survive untouched — the old remove-then-copy
    // deleted it before the (failed) copy.
    XCTAssertTrue(fm.fileExists(atPath: marker.path))
    XCTAssertEqual(try String(contentsOf: marker, encoding: .utf8), "installed-101")
    // No staging litter left behind.
    let leftovers = try fm.contentsOfDirectory(atPath: root.path)
    XCTAssertFalse(leftovers.contains { $0.hasPrefix(".Omi.app.staging") })
  }

  func testReplaceSwapsInNewBundleContent() throws {
    let fm = FileManager.default
    let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    try fm.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? fm.removeItem(at: root) }

    let destination = root.appendingPathComponent("Omi.app", isDirectory: true)
    try fm.createDirectory(at: destination, withIntermediateDirectories: true)
    try "installed-101".write(
      to: destination.appendingPathComponent("build.txt"), atomically: true, encoding: .utf8)

    let source = root.appendingPathComponent("FromDMG.app", isDirectory: true)
    try fm.createDirectory(at: source, withIntermediateDirectories: true)
    try "installed-102".write(
      to: source.appendingPathComponent("build.txt"), atomically: true, encoding: .utf8)

    try AppInstaller.replaceInstalledApp(source: source, destination: destination)

    let installed = try String(
      contentsOf: destination.appendingPathComponent("build.txt"), encoding: .utf8)
    XCTAssertEqual(installed, "installed-102", "the new bundle must be swapped in")
    let leftovers = try fm.contentsOfDirectory(atPath: root.path)
    XCTAssertFalse(leftovers.contains { $0.hasPrefix(".Omi.app.staging") })
  }
}
