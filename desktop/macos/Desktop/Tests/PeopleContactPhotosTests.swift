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

  // MARK: - Matching an address book to the graph

  /// The regression this guards: a real cold start wrote **0** photos, and nothing in the code
  /// could say why — the pass returned a bare `[:]` whether Contacts refused it, nobody had a
  /// photo, or every number failed to match. The matching half was welded to `CNContactStore`, so
  /// no test had ever run it at all.
  ///
  /// The failing condition, reproduced from the real data shape: the graph keys people by the
  /// export's `phone_last10` (`"5551234567"`), while the address book stores whatever the user
  /// typed (`"+1 (555) 123-4567"`, `"555-123-4567"`, `"+15551234567"`). Two normalizers here means
  /// every photo is silently dropped.
  func testAContactPhotoLandsWhateverFormatTheNumberIsStoredIn() throws {
    let userDir = try makeUserDirectory()
    let jpeg = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x01, 0x02])

    for stored in ["+1 (555) 123-4567", "555-123-4567", "+15551234567", "1 555 123 4567"] {
      let dir = try makeUserDirectory()
      var sink = PeopleContactPhotos.Sink(idByPhone: ["5551234567": "alice-nguyen"], userDir: dir)
      sink.offer(phoneNumbers: [stored], thumbnail: jpeg)
      XCTAssertEqual(
        sink.paths["alice-nguyen"],
        PeopleContactPhotos.directory(in: dir).appendingPathComponent("alice-nguyen.jpg").path,
        "\"\(stored)\" must key the same way the graph keyed this person")
      XCTAssertEqual(sink.stats.written, 1)
    }

    // …and a number that genuinely belongs to nobody is a *reported* miss, not a silent one.
    var sink = PeopleContactPhotos.Sink(idByPhone: ["5551234567": "alice-nguyen"], userDir: userDir)
    sink.offer(phoneNumbers: ["+1 (555) 999-0000"], thumbnail: jpeg)
    XCTAssertTrue(sink.paths.isEmpty)
    XCTAssertEqual(sink.stats.contactsWithPhoto, 1)
    XCTAssertEqual(
      sink.stats.unmatchedContacts, 1,
      "\"a photo matched nobody\" must be distinguishable from \"there were no photos\"")
  }

  /// One pass over an address-book shape like the real one: most entries have no photo, some do,
  /// one of those is a stranger, and one person is reachable on two of their numbers. The counts
  /// have to add up — this is the assertion that fails if the matcher ever stops matching.
  func testAPassOverAnAddressBookProducesPathsAndCountsThatAddUp() throws {
    let userDir = try makeUserDirectory()
    let jpeg = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x07])
    var sink = PeopleContactPhotos.Sink(
      idByPhone: [
        "5551234567": "alice-nguyen",  // home number
        "5557654321": "alice-nguyen",  // …same person, mobile
        "5559876543": "bob-chen",
        "5550001111": "dana-wu",  // in the graph, but has no photo in Contacts
      ],
      userDir: userDir)

    sink.offer(phoneNumbers: ["+1 (555) 765-4321", "+1 555 123 4567"], thumbnail: jpeg)  // Alice, twice
    sink.offer(phoneNumbers: ["+15559876543"], thumbnail: Data([0xFF, 0xD8, 0x11]))  // Bob
    sink.offer(phoneNumbers: ["+15554443333"], thumbnail: jpeg)  // a stranger with a photo
    sink.offer(phoneNumbers: ["+15550001111"], thumbnail: Data())  // Dana, no photo
    sink.offer(phoneNumbers: [], thumbnail: Data())  // an entry with neither

    XCTAssertEqual(Set(sink.paths.keys), ["alice-nguyen", "bob-chen"])
    XCTAssertEqual(sink.stats.contactsWithPhoto, 3)
    XCTAssertEqual(sink.stats.matchedContacts, 2)
    XCTAssertEqual(sink.stats.unmatchedContacts, 1)
    XCTAssertEqual(sink.stats.written, 2, "one file per person, not one per matching number")
    for id in sink.paths.keys {
      XCTAssertTrue(
        FileManager.default.fileExists(
          atPath: PeopleContactPhotos.directory(in: userDir).appendingPathComponent("\(id).jpg").path),
        "the path handed to the person card must be a file the avatar reader can open")
    }

    // A second identical pass rewrites nothing but still reports the same people as having photos —
    // otherwise every run after the first would blank every avatar.
    var rerun = PeopleContactPhotos.Sink(
      idByPhone: ["5551234567": "alice-nguyen", "5559876543": "bob-chen"], userDir: userDir)
    rerun.offer(phoneNumbers: ["+1 555 123 4567"], thumbnail: jpeg)
    rerun.offer(phoneNumbers: ["+15559876543"], thumbnail: Data([0xFF, 0xD8, 0x11]))
    XCTAssertEqual(Set(rerun.paths.keys), ["alice-nguyen", "bob-chen"])
    XCTAssertEqual(rerun.stats.written, 0)
    XCTAssertEqual(rerun.stats.unchanged, 2)
  }

  /// Every id the pipeline actually produced on the measured cold start had to be writable. A
  /// person id the shape guard rejects is a photo that can never be stored, so the guard and the id
  /// generator must agree for the ids the graph really mints — including the phone-number and
  /// address-derived labels, which are the majority on a machine without Contacts access.
  func testTheIdsTheGraphReallyMintsAreAllWritableFileNames() throws {
    let realShapes = [
      "alice-nguyen", "urn-biz-29896aa3-06a9-4b54-b544-5e113c222d08", "16516210269",
      "david-d-zhang-gmail-com", "sami-whatsapp", "aryaveer-umn", "person",
    ]
    for id in realShapes {
      XCTAssertEqual(
        PeopleContactPhotos.fileName(forID: id), "\(id).jpg",
        "\"\(id)\" is a shape the graph mints; rejecting it silently loses that person's photo")
    }
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
