import Contacts
import XCTest

@testable import Omi_Computer

/// Guards the People tab's **names** on a first run.
///
/// The regression: `syncIfNeeded` fired the Contacts request and immediately ran the export + graph,
/// so a brand-new user's first pass always finished before the permission prompt was answered.
/// `loadContactsByPhone` returns `[:]` until access is `.authorized`, and the iMessage export — unlike
/// WhatsApp's — carries no `contact_name`, so every iMessage person was named by a raw phone number.
/// That is not just cosmetic: `PeopleMemoryWriter.isHumanName` rejects a digit-only name (no facts)
/// and `PeopleThreadIngest` only ingests threads whose phone resolves to a contact (no deep
/// understanding). These tests pin both halves — the cascade, and the access state that explains it.
final class PeopleContactsAccessTests: XCTestCase {

  // MARK: - Access state (pure; no Contacts store is touched)

  func testWithoutMessageMappingConsentThereIsNothingToExplain() {
    let statuses: [CNAuthorizationStatus] = [.notDetermined, .denied, .restricted, .authorized]
    for status in statuses {
      let state = PeopleContactsAccess.state(status: status, messageMappingEnabled: false)
      XCTAssertEqual(
        state, .notRequested,
        "the pipeline never reads messages without consent, so Contacts is not a problem state")
      XCTAssertNil(state.notice, "an unused permission must not produce UI noise")
      XCTAssertFalse(state.canOpenSettings)
    }
  }

  func testDenialIsDistinguishableFromAnUnansweredPrompt() throws {
    let denied = PeopleContactsAccess.state(status: .denied, messageMappingEnabled: true)
    let pending = PeopleContactsAccess.state(status: .notDetermined, messageMappingEnabled: true)

    XCTAssertEqual(denied, .denied)
    XCTAssertEqual(pending, .pending)
    XCTAssertNotEqual(denied, pending, "a refusal and an unanswered prompt are different states")

    XCTAssertTrue(denied.namesUnavailable, "a denial is terminal until the user changes it")
    XCTAssertFalse(pending.namesUnavailable, "an unanswered prompt may still become a grant")
    XCTAssertFalse(denied.namesResolvable)
    XCTAssertFalse(pending.namesResolvable)

    // The UI has to be able to say *why* everyone is a phone number.
    let deniedNotice = try XCTUnwrap(denied.notice)
    XCTAssertTrue(deniedNotice.contains("Contacts"), "the notice must name the permission")
    XCTAssertTrue(
      deniedNotice.lowercased().contains("phone number"),
      "the notice must connect the permission to what the user is actually seeing")
    XCTAssertNotNil(pending.notice)

    // Only a denial/restriction is fixed in System Settings; macOS ignores a second request, so a
    // pending prompt must not offer a button that does nothing.
    XCTAssertTrue(denied.canOpenSettings)
    XCTAssertFalse(pending.canOpenSettings)
  }

  func testRestrictionReadsAsUnavailableAndAuthorizationSaysNothing() {
    let restricted = PeopleContactsAccess.state(status: .restricted, messageMappingEnabled: true)
    XCTAssertEqual(restricted, .restricted)
    XCTAssertTrue(restricted.namesUnavailable)
    XCTAssertNotNil(restricted.notice)

    let authorized = PeopleContactsAccess.state(status: .authorized, messageMappingEnabled: true)
    XCTAssertEqual(authorized, .authorized)
    XCTAssertTrue(authorized.namesResolvable)
    XCTAssertFalse(authorized.namesUnavailable)
    XCTAssertNil(authorized.notice, "the normal case must render no banner at all")
    XCTAssertFalse(authorized.canOpenSettings)
  }

  // MARK: - The naming cascade the access state exists to prevent

  func testIMessagePeopleFallBackToPhoneNumbersWithoutContactsAndResolveWithThem() throws {
    let root = try iMessageOnlyExport()

    // ---- Contacts unavailable (denied, or the prompt not yet answered) ----
    let unnamed = PeopleGraphBuilder.buildCanonicalPeople(root: root, contactsByPhone: [:])
    let unnamedID = try XCTUnwrap(unnamed.idByPhone["5551234567"])
    let unnamedCanon = try XCTUnwrap(unnamed.canonByID[unnamedID])
    XCTAssertEqual(
      unnamedCanon.name, "+1 (555) 123-4567",
      "the iMessage export carries no contact_name, so the raw handle is the only label left")
    XCTAssertFalse(unnamedCanon.identified, "a phone number is not an identification")
    XCTAssertFalse(
      PeopleMemoryWriter.isHumanName(unnamedCanon.name),
      "the fact writer drops digit-only names — this is why the run produced zero facts")

    let unnamedCards = PeopleGraphBuilder.createPeople(
      people: unnamed,
      graph: PeopleGraphBuilder.buildGraph(root: root, people: unnamed),
      communities: PeopleGraphBuilder.buildCommunities(root: root, people: unnamed))
    let unnamedCard = try XCTUnwrap(unnamedCards.first { ($0["id"] as? String) == unnamedID })
    XCTAssertNil(
      unnamedCard["contactName"], "a card must never claim a contact name it never resolved")

    // ---- Contacts authorized: the same export names people ----
    let named = PeopleGraphBuilder.buildCanonicalPeople(
      root: root, contactsByPhone: ["5551234567": "Alice Nguyen"])
    let namedID = try XCTUnwrap(named.idByPhone["5551234567"])
    let namedCanon = try XCTUnwrap(named.canonByID[namedID])
    XCTAssertEqual(namedCanon.name, "Alice Nguyen")
    XCTAssertTrue(namedCanon.identified)
    XCTAssertTrue(
      PeopleMemoryWriter.isHumanName(namedCanon.name),
      "a resolved name is what unlocks relationship facts and thread ingest")

    let namedCards = PeopleGraphBuilder.createPeople(
      people: named,
      graph: PeopleGraphBuilder.buildGraph(root: root, people: named),
      communities: PeopleGraphBuilder.buildCommunities(root: root, people: named))
    let namedCard = try XCTUnwrap(namedCards.first { ($0["id"] as? String) == namedID })
    XCTAssertEqual(namedCard["contactName"] as? String, "Alice Nguyen")
  }

  /// A WhatsApp person keeps their name with no Contacts access at all — the fix must not paper
  /// over the fact that only iMessage depends on the address book.
  func testWhatsAppNamesSurviveWithoutContacts() throws {
    let root = try whatsAppExport()
    let people = PeopleGraphBuilder.buildCanonicalPeople(root: root, contactsByPhone: [:])
    let id = try XCTUnwrap(people.idByPhone["5559876543"])
    let canon = try XCTUnwrap(people.canonByID[id])
    XCTAssertEqual(canon.name, "Bob Chen", "WhatsApp ships its own contact_name")
    XCTAssertTrue(canon.identified)
  }

  // MARK: - Helpers

  /// Shaped exactly like `IMessageExporter`'s output: handles carry `phone_last10` but never a
  /// `contact_name`.
  private func iMessageOnlyExport() throws -> PeopleGraphBuilder.ExportRoot {
    try decode(
      """
      {
        "handles": [
          { "handle": "+1 (555) 123-4567", "phone_last10": "5551234567", "message_count": 120,
            "last_date": "2026-07-01T10:00:00Z" }
        ],
        "groups": []
      }
      """)
  }

  private func whatsAppExport() throws -> PeopleGraphBuilder.ExportRoot {
    try decode(
      """
      {
        "handles": [
          { "handle": "+15559876543", "phone_last10": "5559876543", "contact_name": "Bob Chen",
            "message_count": 40, "last_date": "2026-07-02T10:00:00Z" }
        ],
        "groups": []
      }
      """)
  }

  private func decode(_ json: String) throws -> PeopleGraphBuilder.ExportRoot {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleContactsAccessTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: dir) }
    let url = dir.appendingPathComponent("export.json")
    try XCTUnwrap(json.data(using: .utf8)).write(to: url)
    return try XCTUnwrap(PeopleGraphBuilder.readExport(at: url))
  }
}
