import SwiftUI
import XCTest

@testable import Omi_Computer

/// Covers the deterministic half of "send this person their page": which handle a person
/// resolves to, that the written document lands on disk with a safe, non-clobbering name, and
/// that the composer degrades to a reason instead of crashing when it cannot be addressed.
///
/// Deliberately not covered here (not hermetic, and would mean acting on the user's behalf):
/// the live Contacts database, and actually opening or sending in Messages.
final class PersonProfileShareTests: XCTestCase {

  private func makeTempDirectory() throws -> URL {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PersonProfileShareTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: dir) }
    return dir
  }

  private func writeExport(_ json: String, named name: String = "imessage_export.json") throws
    -> URL
  {
    let url = try makeTempDirectory().appendingPathComponent(name)
    try json.write(to: url, atomically: true, encoding: .utf8)
    return url
  }

  // MARK: - Handle resolution

  func testResolvesContactHandlesBySlugOfTheDisplayName() {
    let contacts = [
      ContactHandleRecord(
        name: "Ada Lovelace",
        phones: ["+1 (555) 010-1234"],
        emails: ["ada@example.com"]),
      ContactHandleRecord(name: "Grace Hopper", phones: ["+15550109999"]),
    ]

    let handles = PersonHandleResolver.resolve(
      personID: "ada-lovelace",
      contactName: nil,
      displayName: "Ada Lovelace",
      contacts: contacts,
      exportFileURLs: [])

    XCTAssertEqual(handles.phones, ["+1 (555) 010-1234"])
    XCTAssertEqual(handles.emails, ["ada@example.com"])
    XCTAssertEqual(handles.preferredPhone, "+1 (555) 010-1234")
    XCTAssertFalse(handles.isEmpty)
    XCTAssertEqual(handles.recipients, ["+1 (555) 010-1234", "ada@example.com"])
  }

  func testDoesNotResolveHandlesOfADifferentPerson() {
    let contacts = [ContactHandleRecord(name: "Grace Hopper", phones: ["+15550109999"])]

    let handles = PersonHandleResolver.resolve(
      personID: "ada-lovelace",
      contactName: nil,
      displayName: "Ada Lovelace",
      contacts: contacts,
      exportFileURLs: [])

    XCTAssertTrue(handles.isEmpty)
    XCTAssertNil(handles.preferredPhone)
    XCTAssertEqual(handles, .none)
  }

  func testSlugMatchIgnoresPunctuationCaseAndSpacing() {
    // The person id is a slug; the contact card is human-typed. Both must still line up.
    let contacts = [ContactHandleRecord(name: "  Jean-Luc  O'Brien ", phones: ["+15550107777"])]

    let handles = PersonHandleResolver.resolve(
      personID: "jean-luc-o-brien",
      contactName: nil,
      displayName: "JEAN-LUC O'BRIEN",
      contacts: contacts,
      exportFileURLs: [])

    XCTAssertEqual(handles.phones, ["+15550107777"])
  }

  func testDedupesTheSameNumberAcrossFormatsAndSources() throws {
    // Same person, three spellings of one number (contact card, export handle, group-format
    // export handle) plus one genuinely different number.
    let exportURL = try writeExport(
      """
      {
        "generated_at": "2026-07-25T10:00:00Z",
        "total_messages": 12,
        "handles": [
          {
            "handle": "+1 (555) 010-1234",
            "phone_last10": "5550101234",
            "contact_name": "Ada Lovelace",
            "message_count": 8
          },
          {
            "handle": "+15550101234",
            "phone_last10": "5550101234",
            "contact_name": "Ada Lovelace",
            "message_count": 4
          },
          {
            "handle": "ADA@EXAMPLE.COM",
            "contact_name": "Ada Lovelace",
            "message_count": 2
          }
        ],
        "groups": []
      }
      """)

    let contacts = [
      ContactHandleRecord(
        name: "Ada Lovelace",
        phones: ["555-010-1234", "+1 555 010 5678"],
        emails: ["ada@example.com"])
    ]

    let handles = PersonHandleResolver.resolve(
      personID: "ada-lovelace",
      contactName: "Ada Lovelace",
      displayName: "Ada Lovelace",
      contacts: contacts,
      exportFileURLs: [exportURL])

    XCTAssertEqual(handles.phones, ["555-010-1234", "+1 555 010 5678"])
    XCTAssertEqual(handles.emails, ["ada@example.com"])
  }

  func testFallsBackToRawExportHandleWhenTheresNoContactCard() throws {
    // An unresolved person's id is the slug of their raw handle — that is the only address
    // we have, and it must still be usable.
    let exportURL = try writeExport(
      """
      {
        "generated_at": "2026-07-25T10:00:00Z",
        "total_messages": 3,
        "handles": [
          { "handle": "+15550104321", "phone_last10": "5550104321", "message_count": 3 },
          { "handle": "someone.else@example.com", "message_count": 1 }
        ],
        "groups": []
      }
      """)

    let handles = PersonHandleResolver.resolve(
      personID: PeopleGraphBuilder.slug("+15550104321"),
      contactName: nil,
      displayName: "+15550104321",
      contacts: [],
      exportFileURLs: [exportURL])

    XCTAssertEqual(handles.phones, ["+15550104321"])
    XCTAssertTrue(handles.emails.isEmpty, "an unrelated export row must not be addressed")
  }

  func testExportEmailHandleResolvesAsAnEmailNotAPhone() throws {
    let exportURL = try writeExport(
      """
      {
        "generated_at": "2026-07-25T10:00:00Z",
        "total_messages": 1,
        "handles": [
          { "handle": "ada@example.com", "contact_name": "Ada Lovelace", "message_count": 1 }
        ],
        "groups": []
      }
      """)

    let handles = PersonHandleResolver.resolve(
      personID: "ada-lovelace",
      contactName: nil,
      displayName: "Ada Lovelace",
      contacts: [],
      exportFileURLs: [exportURL])

    XCTAssertTrue(handles.phones.isEmpty)
    XCTAssertEqual(handles.emails, ["ada@example.com"])
  }

  func testMissingExportFileIsNotAnError() {
    let missing = FileManager.default.temporaryDirectory
      .appendingPathComponent("does-not-exist-\(UUID().uuidString).json")

    let handles = PersonHandleResolver.resolve(
      personID: "ada-lovelace",
      contactName: nil,
      displayName: "Ada Lovelace",
      contacts: [ContactHandleRecord(name: "Ada Lovelace", phones: ["+15550101234"])],
      exportFileURLs: [missing])

    XCTAssertEqual(handles.phones, ["+15550101234"])
  }

  func testBlankIdentityResolvesToNothing() {
    let handles = PersonHandleResolver.resolve(
      personID: "",
      contactName: "   ",
      displayName: "",
      contacts: [ContactHandleRecord(name: "Ada Lovelace", phones: ["+15550101234"])],
      exportFileURLs: [])

    XCTAssertEqual(handles, .none, "an unnamed person must never inherit someone's number")
  }

  // MARK: - Filename safety

  func testFileNameStripsPathSeparatorsAndColons() {
    let name = PersonProfileRenderer.safeFileName(for: "Ada / Lovelace: Countess")

    XCTAssertFalse(name.contains("/"))
    XCTAssertFalse(name.contains(":"))
    XCTAssertEqual(name, "Ada Lovelace Countess")
  }

  func testFileNameKeepsEmojiAndNonLatinScripts() {
    let name = PersonProfileRenderer.safeFileName(for: "Ada 🚀 Lovelace 中文")

    XCTAssertEqual(name, "Ada 🚀 Lovelace 中文")
  }

  func testFileNameNeverExceedsTheFilesystemComponentLimit() {
    let long = String(repeating: "🚀", count: 400)
    let name = PersonProfileRenderer.safeFileName(for: long)

    XCTAssertLessThanOrEqual(
      "\(name) 99.pdf".utf8.count, 255,
      "the full component (name + dedupe suffix + extension) must fit an APFS filename")
    XCTAssertFalse(name.isEmpty)
    // Truncation must not split a multi-byte scalar.
    XCTAssertTrue(name.allSatisfy { $0 == "🚀" })
  }

  func testFileNameNeverProducesAHiddenOrEmptyFile() {
    XCTAssertEqual(PersonProfileRenderer.safeFileName(for: "...."), "Person")
    XCTAssertEqual(PersonProfileRenderer.safeFileName(for: "   "), "Person")
    XCTAssertEqual(PersonProfileRenderer.safeFileName(for: "/"), "Person")
    XCTAssertEqual(PersonProfileRenderer.safeFileName(for: ".hidden"), "hidden")
  }

  // MARK: - Writing the document

  func testWriteCreatesTheExportDirectoryWhenMissing() throws {
    let parent = try makeTempDirectory()
    let directory = parent.appendingPathComponent("Omi Exports", isDirectory: true)
    XCTAssertFalse(FileManager.default.fileExists(atPath: directory.path))

    let url = try PersonProfileRenderer.write(
      pdf: Data("%PDF-1.4 test".utf8), personName: "Ada Lovelace", directory: directory)

    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    XCTAssertEqual(url.lastPathComponent, "Ada Lovelace.pdf")
  }

  func testWriteDoesNotClobberAnUnrelatedFileWithTheSameName() throws {
    let directory = try makeTempDirectory()
    let existing = directory.appendingPathComponent("Ada Lovelace.pdf")
    try Data("someone else's file".utf8).write(to: existing)

    let url = try PersonProfileRenderer.write(
      pdf: Data("%PDF-1.4 new".utf8), personName: "Ada Lovelace", directory: directory)

    XCTAssertNotEqual(url, existing)
    XCTAssertEqual(url.lastPathComponent, "Ada Lovelace 2.pdf")
    XCTAssertEqual(try Data(contentsOf: existing), Data("someone else's file".utf8))
    XCTAssertEqual(try Data(contentsOf: url), Data("%PDF-1.4 new".utf8))
  }

  func testExportDirectoryIsTheEstablishedDownloadsFolder() {
    XCTAssertEqual(PersonProfileRenderer.exportDirectory().lastPathComponent, "Omi Exports")
  }

  // MARK: - Rendering

  @MainActor
  func testRendersARealSwiftUIViewToVectorPDF() throws {
    let view = VStack(spacing: 8) {
      Text("Ada Lovelace").font(.title)
      Text("Profile").font(.body)
    }
    .padding(24)
    .frame(width: 420, height: 240)
    .background(Color.white)

    let pdf = try XCTUnwrap(
      PersonProfileRenderer.renderPDF(view, size: CGSize(width: 420, height: 240)),
      "the offscreen renderer must produce a PDF")

    XCTAssertGreaterThan(pdf.count, 0)
    XCTAssertEqual(pdf.prefix(4), Data("%PDF".utf8), "the bytes must be a real PDF document")
  }

  @MainActor
  func testRendersARealSwiftUIViewToPNG() throws {
    let view = Text("Ada Lovelace").frame(width: 200, height: 100).background(Color.white)

    let png = try XCTUnwrap(PersonProfileRenderer.renderPNG(view, size: CGSize(width: 200, height: 100)))

    XCTAssertGreaterThan(png.count, 0)
    XCTAssertEqual(
      png.prefix(8), Data([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
      "the bytes must carry the PNG signature")
  }

  @MainActor
  func testDegenerateSizeStillRendersInsteadOfCrashing() throws {
    let pdf = PersonProfileRenderer.renderPDF(Color.white, size: .zero)

    XCTAssertNotNil(pdf, "a zero size must be clamped, not passed through to AppKit")
  }

  // MARK: - Composing (never sending)

  @MainActor
  func testComposeIsUnavailableWithNoRecipients() throws {
    let directory = try makeTempDirectory()
    let file = directory.appendingPathComponent("Ada Lovelace.pdf")
    try Data("%PDF-1.4".utf8).write(to: file)

    let outcome = PersonProfileShare.compose(fileURL: file, recipients: [], body: "Your page")

    guard case .unavailable(let reason) = outcome else {
      return XCTFail("expected .unavailable, got \(outcome)")
    }
    XCTAssertFalse(reason.isEmpty, "the reason is shown to the user")
  }

  @MainActor
  func testComposeIsUnavailableWhenRecipientsAreOnlyWhitespace() throws {
    let directory = try makeTempDirectory()
    let file = directory.appendingPathComponent("Ada Lovelace.pdf")
    try Data("%PDF-1.4".utf8).write(to: file)

    let outcome = PersonProfileShare.compose(fileURL: file, recipients: ["", "  "], body: "hi")

    guard case .unavailable = outcome else {
      return XCTFail("blank recipients must not reach the composer, got \(outcome)")
    }
  }

  @MainActor
  func testComposeIsUnavailableWhenTheDocumentIsGone() {
    let missing = FileManager.default.temporaryDirectory
      .appendingPathComponent("gone-\(UUID().uuidString).pdf")

    let outcome = PersonProfileShare.compose(
      fileURL: missing, recipients: ["+15550101234"], body: "Your page")

    guard case .unavailable = outcome else {
      return XCTFail("a missing document must not open a composer, got \(outcome)")
    }
  }

  @MainActor
  func testRevealInFinderIsUnavailableForAMissingFile() {
    let missing = FileManager.default.temporaryDirectory
      .appendingPathComponent("gone-\(UUID().uuidString).pdf")

    guard case .unavailable = PersonProfileShare.revealInFinder(missing) else {
      return XCTFail("revealing a missing file must report unavailable")
    }
  }

  @MainActor
  func testCopyMarkdownRejectsEmptyContent() {
    guard case .unavailable = PersonProfileShare.copyMarkdown("   \n ") else {
      return XCTFail("copying nothing must report unavailable")
    }
  }
}
