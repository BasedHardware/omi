import XCTest

@testable import Omi_Computer

/// Guards the on-device contact-photo writer.
///
/// The regression: every People avatar surface read
/// `<user dir>/people_photos/<person id>.jpg` (`PeoplePhotos.photoPath(forID:)`,
/// `PersonProfileAvatar`, the connection chips) but **nothing in the app ever wrote that folder**,
/// so everyone rendered as initials even though the Contacts store had their photo. These tests pin
/// the two things a writer must never get wrong: the file name can't escape the folder, and it has
/// to match the name the reader builds from the same id.
final class PeopleContactPhotosTests: XCTestCase {

  // MARK: - File naming

  func testUnsafeIdentifiersAreRejectedRatherThanRewritten() {
    let unsafe = [
      "", "..", "../secrets", "a/b", "/etc/passwd", "alice.jpg", "alice photo", "alice\u{0}",
      String(repeating: "a", count: 129),
    ]
    for id in unsafe {
      XCTAssertNil(
        PeopleContactPhotos.fileName(forID: id),
        "\"\(id)\" must not become a path — the reader rebuilds the path from the raw id, so a "
          + "rewritten name would never be found and an escaping one must never be written")
    }
    XCTAssertEqual(PeopleContactPhotos.fileName(forID: "alice-nguyen"), "alice-nguyen.jpg")
  }

  func testEveryCanonicalPersonIdIsAWritableFileName() throws {
    let hostileNames = [
      "Alice Nguyen", "+1 (555) 123-4567", "../../etc/passwd", "..", "José 🙂", "a/b\\c:d",
    ]
    for name in hostileNames {
      let id = PeopleGraphBuilder.slug(name)
      let fileName = try XCTUnwrap(
        PeopleContactPhotos.fileName(forID: id),
        "slug(\"\(name)\") = \"\(id)\" must be writable — every person id comes from slug()")
      XCTAssertEqual(fileName, "\(id).jpg")
    }
  }

  // MARK: - Writing

  func testPhotoIsWrittenInsideTheUserDirectoryAndSkippedWhenUnchanged() throws {
    let userDir = try makeUserDirectory()
    let jpeg = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x01, 0x02])

    guard case .written(let path) = PeopleContactPhotos.store(thumbnail: jpeg, forID: "alice", in: userDir)
    else { return XCTFail("the first store of a photo must write it") }

    let url = URL(fileURLWithPath: path)
    XCTAssertEqual(url.lastPathComponent, "alice.jpg", "must match PeoplePhotos' <id>.jpg convention")
    XCTAssertEqual(url.deletingLastPathComponent().lastPathComponent, "people_photos")
    XCTAssertTrue(
      url.deletingLastPathComponent().deletingLastPathComponent().path == userDir.path,
      "photos stay inside the caller's per-user directory")
    XCTAssertEqual(try Data(contentsOf: url), jpeg)

    XCTAssertEqual(
      PeopleContactPhotos.store(thumbnail: jpeg, forID: "alice", in: userDir), .unchanged(path),
      "identical bytes must not be rewritten on every run")
    XCTAssertEqual(
      PeopleContactPhotos.store(thumbnail: Data([0xFF, 0xD8, 0x03]), forID: "alice", in: userDir),
      .written(path), "a changed photo must be picked up")
  }

  func testAnUnsafeIdentifierWritesNothingAtAll() throws {
    let userDir = try makeUserDirectory()
    XCTAssertEqual(
      PeopleContactPhotos.store(thumbnail: Data([0x01, 0x02]), forID: "../escaped", in: userDir),
      .skipped)
    XCTAssertFalse(
      FileManager.default.fileExists(atPath: PeopleContactPhotos.directory(in: userDir).path),
      "a rejected id must not even create the folder")
    XCTAssertFalse(
      FileManager.default.fileExists(
        atPath: userDir.deletingLastPathComponent().appendingPathComponent("escaped.jpg").path),
      "nothing may be written outside the per-user directory")
  }

  func testEmptyThumbnailIsSkipped() throws {
    let userDir = try makeUserDirectory()
    XCTAssertEqual(PeopleContactPhotos.store(thumbnail: Data(), forID: "alice", in: userDir), .skipped)
  }

  // MARK: - Wiring onto the person cards

  func testCreatePeopleStampsPhotoPathsOnlyForPeopleThatHaveOne() throws {
    let root = try export()
    let people = PeopleGraphBuilder.buildCanonicalPeople(
      root: root, contactsByPhone: ["5551234567": "Alice Nguyen", "5559876543": "Bob Chen"])
    let graph = PeopleGraphBuilder.buildGraph(root: root, people: people)
    let communities = PeopleGraphBuilder.buildCommunities(root: root, people: people)

    let withoutPhotos = PeopleGraphBuilder.createPeople(
      people: people, graph: graph, communities: communities)
    XCTAssertTrue(
      withoutPhotos.allSatisfy { $0["photoPath"] as? String == nil },
      "no photo written means no photoPath — the avatar falls back to initials")

    let alice = try XCTUnwrap(people.idByPhone["5551234567"])
    let cards = PeopleGraphBuilder.createPeople(
      people: people, graph: graph, communities: communities,
      photoPaths: [alice: "/tmp/omi-test/people_photos/\(alice).jpg"])
    let aliceCard = try XCTUnwrap(cards.first { ($0["id"] as? String) == alice })
    XCTAssertEqual(aliceCard["photoPath"] as? String, "/tmp/omi-test/people_photos/\(alice).jpg")
    for card in cards where (card["id"] as? String) != alice {
      XCTAssertNil(card["photoPath"], "only people with a written photo get a path")
    }
  }

  // MARK: - Writer/reader convention (static checker, not behavioral coverage)

  /// `PeoplePhotos` (in `PeoplePage.swift`) resolves the read path independently of this writer, so
  /// a rename on either side would silently empty every avatar again. This asserts the two agree on
  /// the folder name and the `<id>.jpg` file name; it is a source tripwire, not a behavior test.
  func testReaderResolvesTheSameFolderAndFileNameConvention() throws {
    let source = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/MainWindow/Pages/PeoplePage.swift"),
      encoding: .utf8)
    let start = try XCTUnwrap(source.range(of: "enum PeoplePhotos {"))
    let rest = source[start.upperBound...]
    let body = String(rest[..<(rest.range(of: "\n}\n")?.lowerBound ?? rest.endIndex)])
    XCTAssertTrue(
      body.contains("\"\(PeopleContactPhotos.directoryName)\""),
      "the reader must resolve the same folder the writer creates")
    XCTAssertTrue(
      body.contains("\"\\(id).jpg\""), "the reader must build the same <id>.jpg file name")
  }

  // MARK: - Helpers

  private func makeUserDirectory() throws -> URL {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleContactPhotosTests-\(UUID().uuidString)", isDirectory: true)
      .appendingPathComponent("user", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: dir.deletingLastPathComponent()) }
    return dir
  }

  private func export() throws -> PeopleGraphBuilder.ExportRoot {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleContactPhotosTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: dir) }
    let url = dir.appendingPathComponent("imessage_export.json")
    let json = """
      {
        "handles": [
          { "handle": "+15551234567", "phone_last10": "5551234567", "message_count": 90 },
          { "handle": "+15559876543", "phone_last10": "5559876543", "message_count": 20 }
        ],
        "groups": []
      }
      """
    try XCTUnwrap(json.data(using: .utf8)).write(to: url)
    return try XCTUnwrap(PeopleGraphBuilder.readExport(at: url))
  }
}
