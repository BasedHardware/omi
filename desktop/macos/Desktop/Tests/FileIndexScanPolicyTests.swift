import XCTest

@testable import Omi_Computer

final class FileIndexScanPolicyTests: XCTestCase {
  func testStandardScanRootsArePlannedFromSuppliedHomeURL() {
    let policy = FileIndexScanPolicy.standard
    let home = URL(fileURLWithPath: "/tmp/omi-test-home", isDirectory: true)
    let applications = URL(fileURLWithPath: "/tmp/omi-test-applications", isDirectory: true)

    let roots = policy.standardScanRoots(homeURL: home, applicationsURL: applications)

    XCTAssertEqual(
      roots.map(\.path),
      [
        "/tmp/omi-test-home/Downloads",
        "/tmp/omi-test-home/Documents",
        "/tmp/omi-test-home/Desktop",
        "/tmp/omi-test-home/Developer",
        "/tmp/omi-test-home/Projects",
        "/tmp/omi-test-home/Code",
        "/tmp/omi-test-home/src",
        "/tmp/omi-test-home/repos",
        "/tmp/omi-test-home/Sites",
        "/tmp/omi-test-applications",
        "/tmp/omi-test-home/Applications",
      ]
    )
  }

  func testSkipFoldersAreRejectedBeforeRecursiveDescent() {
    let policy = FileIndexScanPolicy.standard

    XCTAssertEqual(policy.planDirectoryEntry(directory(named: "node_modules")), .skipSubtree)
    XCTAssertEqual(policy.planDirectoryEntry(directory(named: ".git")), .skipSubtree)
    XCTAssertEqual(policy.planDirectoryEntry(directory(named: "Library")), .skipSubtree)
    XCTAssertEqual(policy.planDirectoryEntry(directory(named: "Source")), .descend)
  }

  func testPackagesAreIndexedAsLeavesWithStableType() {
    let policy = FileIndexScanPolicy.standard
    let homePath = "/Users/tester"
    let modified = Date(timeIntervalSince1970: 1_000)

    let app = policy.makePackageRecord(
      for: URL(fileURLWithPath: "\(homePath)/Applications/Omi.app", isDirectory: true),
      folderName: "Applications",
      homePath: homePath,
      depth: 1,
      createdAt: nil,
      modifiedAt: modified
    )
    XCTAssertEqual(app?.path, "~/Applications/Omi.app")
    XCTAssertEqual(app?.filename, "Omi.app")
    XCTAssertEqual(app?.fileExtension, "app")
    XCTAssertEqual(app?.fileType, "application")
    XCTAssertEqual(app?.sizeBytes, 0)
    XCTAssertEqual(app?.depth, 1)
    XCTAssertEqual(app?.modifiedAt, modified)

    let project = policy.makePackageRecord(
      for: URL(fileURLWithPath: "\(homePath)/Developer/Omi.xcodeproj", isDirectory: true),
      folderName: "Developer",
      homePath: homePath,
      depth: 0,
      createdAt: nil,
      modifiedAt: nil
    )
    XCTAssertEqual(project?.path, "~/Developer/Omi.xcodeproj")
    XCTAssertEqual(project?.fileExtension, "xcodeproj")
    XCTAssertEqual(project?.fileType, "package")

    XCTAssertNil(
      policy.makePackageRecord(
        for: URL(fileURLWithPath: "\(homePath)/Developer/plain-folder", isDirectory: true),
        folderName: "Developer",
        homePath: homePath,
        depth: 0,
        createdAt: nil,
        modifiedAt: nil
      )
    )
  }

  func testMaxDepthAllowsConfiguredDepthAndStopsBelowIt() {
    let policy = FileIndexScanPolicy(maxDepth: 2)

    XCTAssertTrue(policy.shouldScanDirectory(atDepth: 0))
    XCTAssertTrue(policy.shouldScanDirectory(atDepth: 2))
    XCTAssertFalse(policy.shouldScanDirectory(atDepth: 3))
  }

  func testFileRecordsRejectEmptyOversizedAndNonRegularFiles() {
    let policy = FileIndexScanPolicy(maxFileSize: 10)
    let homePath = "/Users/tester"
    let url = URL(fileURLWithPath: "\(homePath)/Documents/report.pdf")

    XCTAssertNil(
      policy.makeFileRecord(
        for: url,
        folderName: "Documents",
        homePath: homePath,
        depth: 0,
        isRegularFile: false,
        sizeBytes: 5,
        createdAt: nil,
        modifiedAt: nil
      )
    )
    XCTAssertNil(
      policy.makeFileRecord(
        for: url,
        folderName: "Documents",
        homePath: homePath,
        depth: 0,
        isRegularFile: true,
        sizeBytes: 0,
        createdAt: nil,
        modifiedAt: nil
      )
    )
    XCTAssertNil(
      policy.makeFileRecord(
        for: url,
        folderName: "Documents",
        homePath: homePath,
        depth: 0,
        isRegularFile: true,
        sizeBytes: 11,
        createdAt: nil,
        modifiedAt: nil
      )
    )

    let record = policy.makeFileRecord(
      for: url,
      folderName: "Documents",
      homePath: homePath,
      depth: 0,
      isRegularFile: true,
      sizeBytes: 10,
      createdAt: nil,
      modifiedAt: nil
    )

    XCTAssertEqual(record?.path, "~/Documents/report.pdf")
    XCTAssertEqual(record?.filename, "report.pdf")
    XCTAssertEqual(record?.fileExtension, "pdf")
    XCTAssertEqual(record?.fileType, FileTypeCategory.document.rawValue)
    XCTAssertEqual(record?.sizeBytes, 10)
  }

  private func directory(named name: String) -> URL {
    URL(fileURLWithPath: "/tmp/omi-file-index-policy/\(name)", isDirectory: true)
  }
}
