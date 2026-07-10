import XCTest

@testable import Omi_Computer

final class AppInstallerTests: XCTestCase {

  // MARK: - Installer-location detection

  func testMountedDMGPathIsInstallerLocation() {
    XCTAssertTrue(AppInstaller.isInstallerLocation("/Volumes/Omi Beta/Omi Beta.app"))
    XCTAssertTrue(AppInstaller.isInstallerLocation("/Volumes/Omi/Omi.app"))
  }

  func testTranslocatedPathIsInstallerLocation() {
    XCTAssertTrue(
      AppInstaller.isInstallerLocation(
        "/private/var/folders/ab/x1/T/AppTranslocation/1B2F3C4D/d/Omi Beta.app"))
  }

  func testInstalledAndDevPathsAreNotInstallerLocations() {
    XCTAssertFalse(AppInstaller.isInstallerLocation("/Applications/Omi Beta.app"))
    XCTAssertFalse(AppInstaller.isInstallerLocation("/Applications/omi-fix-rewind.app"))
    // Local dev builds run from checkouts and temp build dirs — never gated.
    XCTAssertFalse(
      AppInstaller.isInstallerLocation("/Users/nik/projects/omi/desktop/macos/.build/Omi.app"))
    XCTAssertFalse(AppInstaller.isInstallerLocation("/Users/nik/Downloads/Omi Beta.app"))
  }

  // MARK: - Install destination

  func testInstalledURLKeepsBundleName() {
    let url = AppInstaller.installedURL(
      forBundleURL: URL(fileURLWithPath: "/Volumes/Omi Beta/Omi Beta.app"))
    XCTAssertEqual(url.path, "/Applications/Omi Beta.app")
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
}
