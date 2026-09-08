import XCTest

@testable import Omi_Computer

final class DesktopReleaseNotesTests: XCTestCase {
  private func catalog(_ json: String) throws -> DesktopReleaseNotesCatalog {
    try DesktopReleaseNotesCatalog.decode(from: Data(json.utf8))
  }

  func testDecodesVersionDateAndChanges() throws {
    let parsed = try catalog(
      """
      {"releases": [
        {"version": "0.12.322", "date": "2026-09-08", "changes": ["Fixed a thing", "Added another"]}
      ]}
      """)

    XCTAssertEqual(parsed.releases.count, 1)
    let release = try XCTUnwrap(parsed.releases.first)
    XCTAssertEqual(release.version, "0.12.322")
    XCTAssertEqual(release.changes, ["Fixed a thing", "Added another"])

    // A calendar day in the reader's own zone: formatting it must not slip to September 7.
    var components = DateComponents()
    components.year = 2026
    components.month = 9
    components.day = 8
    let calendar = Calendar.current
    XCTAssertEqual(release.date, calendar.date(from: components))
    let day = try XCTUnwrap(release.date)
    XCTAssertEqual(calendar.component(.day, from: day), 8)
    XCTAssertEqual(calendar.component(.month, from: day), 9)
  }

  func testSortsNewestReleaseFirstByVersionNumberNotStringOrder() throws {
    let parsed = try catalog(
      """
      {"releases": [
        {"version": "0.12.9", "date": "2026-01-01", "changes": ["Older"]},
        {"version": "0.12.100", "date": "2026-01-02", "changes": ["Newer"]},
        {"version": "0.9.400", "date": "2025-01-01", "changes": ["Oldest"]}
      ]}
      """)

    XCTAssertEqual(parsed.releases.map(\.version), ["0.12.100", "0.12.9", "0.9.400"])
  }

  func testDropsEntriesWithNoVersionOrNoChangesInsteadOfFailingTheCatalog() throws {
    let parsed = try catalog(
      """
      {"releases": [
        {"version": "0.12.2", "date": "2026-01-02", "changes": ["Kept"]},
        {"version": "  ", "date": "2026-01-02", "changes": ["No version"]},
        {"version": "0.12.1", "date": "2026-01-01", "changes": ["   ", ""]},
        {"version": "0.12.0", "date": "2026-01-01"}
      ]}
      """)

    XCTAssertEqual(parsed.releases.map(\.version), ["0.12.2"])
  }

  func testMissingDateStillYieldsAReadableEntry() throws {
    let parsed = try catalog(
      """
      {"releases": [{"version": "0.12.5", "changes": ["No date on this one"]}]}
      """)

    let release = try XCTUnwrap(parsed.releases.first)
    XCTAssertNil(release.date)
    XCTAssertEqual(release.changes, ["No date on this one"])
  }

  func testMalformedDocumentThrowsRatherThanReturningPartialReleases() {
    XCTAssertThrowsError(try catalog("not json at all"))
  }

  func testNoteForRunningVersionIsFoundAndUnknownVersionIsNil() throws {
    let parsed = try catalog(
      """
      {"releases": [
        {"version": "0.12.2", "date": "2026-01-02", "changes": ["Two"]},
        {"version": "0.12.1", "date": "2026-01-01", "changes": ["One"]}
      ]}
      """)

    XCTAssertEqual(parsed.note(forVersion: "0.12.1")?.changes, ["One"])
    XCTAssertNil(parsed.note(forVersion: "0.12.99"))
  }

  func testNotesNewerThanRunningVersionExcludeTheRunningOne() throws {
    let parsed = try catalog(
      """
      {"releases": [
        {"version": "0.12.3", "date": "2026-01-03", "changes": ["Three"]},
        {"version": "0.12.2", "date": "2026-01-02", "changes": ["Two"]},
        {"version": "0.12.1", "date": "2026-01-01", "changes": ["One"]}
      ]}
      """)

    XCTAssertEqual(parsed.notes(newerThan: "0.12.2").map(\.version), ["0.12.3"])
    XCTAssertTrue(parsed.notes(newerThan: "0.12.3").isEmpty)
  }

  func testVersionOrderingComparesNumericComponentsNotText() {
    XCTAssertTrue(DesktopReleaseVersion.isDescending("0.12.100", "0.12.99"))
    XCTAssertFalse(DesktopReleaseVersion.isDescending("0.12.99", "0.12.100"))
    XCTAssertFalse(DesktopReleaseVersion.isDescending("0.12.1", "0.12.1"))
    // A shorter version is the same as one padded with zeros.
    XCTAssertFalse(DesktopReleaseVersion.isDescending("1.0", "1.0.0"))
    XCTAssertTrue(DesktopReleaseVersion.isDescending("1.0.1", "1.0"))
    // Non-numeric noise never traps; it reads as the leading number.
    XCTAssertTrue(DesktopReleaseVersion.isDescending("0.13.0-beta", "0.12.9"))
  }
}
