import XCTest

@testable import Omi_Computer

final class DesktopBuildIdentityTests: XCTestCase {
  private let revision = "0123456789abcdef0123456789abcdef01234567"

  func testCleanGeneratedMetadataProducesKnownIdentity() {
    let identity = DesktopBuildIdentity.from(
      infoDictionary: metadata(revision: revision, workingTreeState: "clean"))

    XCTAssertEqual(
      identity,
      DesktopBuildIdentity(
        schemaVersion: 1,
        revision: revision,
        workingTreeState: .clean))
  }

  func testDirtyGeneratedMetadataPreservesDirtyMarker() {
    let identity = DesktopBuildIdentity.from(
      infoDictionary: metadata(revision: revision, workingTreeState: "dirty"))

    XCTAssertEqual(identity.revision, revision)
    XCTAssertEqual(identity.workingTreeState, .dirty)
  }

  func testMissingGeneratedMetadataIsExplicitlyUnknown() {
    XCTAssertEqual(DesktopBuildIdentity.from(infoDictionary: [:]), .unknown)
  }

  func testPartialOrMalformedMetadataCannotClaimSourceIdentity() {
    XCTAssertEqual(
      DesktopBuildIdentity.from(
        infoDictionary: metadata(revision: "deadbeef", workingTreeState: "clean")),
      .unknown)
    XCTAssertEqual(
      DesktopBuildIdentity.from(
        infoDictionary: metadata(revision: revision, workingTreeState: "unknown")),
      .unknown)
    XCTAssertEqual(
      DesktopBuildIdentity.from(
        infoDictionary: [
          DesktopBuildIdentity.schemaVersionInfoKey: 1,
          DesktopBuildIdentity.revisionInfoKey: revision,
        ]),
      .unknown)
  }

  private func metadata(revision: String, workingTreeState: String) -> [String: Any] {
    [
      DesktopBuildIdentity.schemaVersionInfoKey: DesktopBuildIdentity.metadataSchemaVersion,
      DesktopBuildIdentity.revisionInfoKey: revision,
      DesktopBuildIdentity.workingTreeStateInfoKey: workingTreeState,
    ]
  }
}
