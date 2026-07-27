import GRDB
import XCTest

@testable import Omi_Computer

/// Exercises the on-device WhatsApp reader's pure logic and its merge into the People graph:
/// JID classification + the `@lid` → phone bridge, reading that bridge from a synthetic `LID.sqlite`
/// (temp fixture — never the user's real database), and the cross-channel merge where a person seen
/// on both iMessage and WhatsApp resolves to one multi-channel node and WhatsApp group co-membership
/// contributes real, correctly-sourced edges/communities.
final class WhatsAppReaderTests: XCTestCase {

  // MARK: - JID classification + phone resolution

  func testJIDClassificationAndPhoneResolution() {
    // Real people/group JIDs are kept; WhatsApp's system JIDs are filtered out.
    XCTAssertTrue(WhatsAppReader.isRealContactJID("120363000000000000@g.us"))
    XCTAssertTrue(WhatsAppReader.isRealContactJID("15551234567@s.whatsapp.net"))
    XCTAssertTrue(WhatsAppReader.isRealContactJID("778899001122@lid"))
    XCTAssertFalse(WhatsAppReader.isRealContactJID("status@broadcast"))
    XCTAssertFalse(WhatsAppReader.isRealContactJID("123@status"))
    XCTAssertFalse(WhatsAppReader.isRealContactJID("123@lid.status"))
    XCTAssertFalse(WhatsAppReader.isRealContactJID("no-at-sign"))

    // `@s.whatsapp.net` carries the phone in its local part; `@lid` needs the bridge.
    let bridge = ["778899001122@lid": "15557788990", "778899001122": "15557788990"]
    XCTAssertEqual(
      WhatsAppReader.phoneDigits(forJID: "15551234567@s.whatsapp.net", lidBridge: [:]), "15551234567")
    XCTAssertEqual(WhatsAppReader.phoneDigits(forJID: "778899001122@lid", lidBridge: bridge), "15557788990")
    // An unbridged LID has no phone; a too-short local part is not a real number.
    XCTAssertNil(WhatsAppReader.phoneDigits(forJID: "999@lid", lidBridge: bridge))
    XCTAssertNil(WhatsAppReader.phoneDigits(forJID: "123@s.whatsapp.net", lidBridge: [:]))

    XCTAssertEqual(WhatsAppReader.last10("15551234567"), "5551234567")
    XCTAssertNil(WhatsAppReader.last10("12345"))
  }

  // MARK: - LID → phone bridge read from a synthetic LID.sqlite fixture

  func testLIDBridgeReadsIdentifierToPhone() throws {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("WhatsAppReaderTests-lid-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }

    let lidURL = dir.appendingPathComponent("LID.sqlite")
    // Build a minimal ZWAZACCOUNT table shaped like WhatsApp's real one, then release the handle so
    // the read-only copy sees the committed file.
    do {
      let queue = try DatabaseQueue(path: lidURL.path)
      try queue.write { db in
        try db.execute(
          sql: "CREATE TABLE ZWAZACCOUNT (Z_PK INTEGER PRIMARY KEY, ZIDENTIFIER VARCHAR, ZPHONENUMBER VARCHAR)")
        try db.execute(
          sql: "INSERT INTO ZWAZACCOUNT (ZIDENTIFIER, ZPHONENUMBER) VALUES (?, ?)",
          arguments: ["778899001122@lid", "15557788990"])
        // A LID with no phone must be skipped (WHERE ZPHONENUMBER IS NOT NULL).
        try db.execute(sql: "INSERT INTO ZWAZACCOUNT (ZIDENTIFIER) VALUES (?)", arguments: ["223344556677@lid"])
      }
    }

    let bridge = WhatsAppReader.loadLIDBridge(from: lidURL, into: dir.appendingPathComponent("copy"))
    // Keyed by both the full `@lid` identifier and its numeric local part.
    XCTAssertEqual(bridge["778899001122@lid"], "15557788990")
    XCTAssertEqual(bridge["778899001122"], "15557788990")
    XCTAssertNil(bridge["223344556677@lid"], "a LID with a NULL phone must not appear in the bridge")

    // End-to-end: a group-member `@lid` JID resolves to its phone through the loaded bridge.
    XCTAssertEqual(WhatsAppReader.phoneDigits(forJID: "778899001122@lid", lidBridge: bridge), "15557788990")

    // A missing bridge file is a clean empty map, never a throw.
    XCTAssertTrue(
      WhatsAppReader.loadLIDBridge(from: dir.appendingPathComponent("nope.sqlite"), into: dir).isEmpty)
  }

  // MARK: - Decode + cross-channel merge into the graph

  /// Dana appears on BOTH channels (same `phone_last10`); Eve and a group-only member are
  /// WhatsApp-only; Frank is iMessage-only. After merge, Dana is one multi-channel node, WhatsApp
  /// co-membership produces WhatsApp-sourced edges, and the WhatsApp group becomes a "whatsapp"
  /// community.
  func testWhatsAppExportDecodesAndMergesAcrossChannels() throws {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("WhatsAppReaderTests-merge-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }

    // WhatsApp export written in the SAME shape as imessage_export.json (with chat_guid/is_group,
    // which the graph decoder tolerates), read back through the real decode path.
    let waURL = dir.appendingPathComponent("whatsapp_export.json")
    let waJSON = """
      {
        "generated_at": "2026-07-11T00:00:00Z",
        "total_messages": 42,
        "handles": [
          { "handle": "+15550001111", "phone_last10": "5550001111", "contact_name": "Dana",
            "message_count": 30, "last_date": "2026-07-10T09:00:00Z", "is_group": false },
          { "handle": "+15552223333", "phone_last10": "5552223333", "contact_name": "Eve",
            "message_count": 12, "last_date": "2026-07-09T09:00:00Z", "is_group": false }
        ],
        "groups": [
          { "chat_guid": "120363111@g.us", "display_name": "Cabo Trip", "member_count": 3,
            "members": [
              { "handle": "+15550001111", "phone_last10": "5550001111" },
              { "handle": "+15552223333", "phone_last10": "5552223333" },
              { "handle": "+15554445555", "phone_last10": "5554445555" }
            ] }
        ]
      }
      """
    try XCTUnwrap(waJSON.data(using: .utf8)).write(to: waURL)

    // iMessage export: Dana shared by phone, plus an iMessage-only "Roommates" pair.
    let imURL = dir.appendingPathComponent("imessage_export.json")
    let imJSON = """
      {
        "generated_at": "2026-07-21T00:00:00Z",
        "total_messages": 100,
        "handles": [
          { "handle": "+1 (555) 000-1111", "phone_last10": "5550001111", "contact_name": "Dana",
            "message_count": 100, "last_date": "2026-07-20T09:00:00Z" }
        ],
        "groups": [
          { "display_name": "Roommates", "member_count": 2,
            "members": [ { "phone_last10": "5550001111" }, { "phone_last10": "5556667777" } ] }
        ]
      }
      """
    try XCTUnwrap(imJSON.data(using: .utf8)).write(to: imURL)

    let waRoot = try XCTUnwrap(PeopleGraphBuilder.readExport(at: waURL), "WhatsApp export must decode")
    let imRoot = try XCTUnwrap(PeopleGraphBuilder.readExport(at: imURL), "iMessage export must decode")

    // The WhatsApp export decodes to the same lenient shape, carrying its own contact names.
    XCTAssertEqual(waRoot.handles.count, 2)
    XCTAssertEqual(waRoot.groups.count, 1)
    XCTAssertEqual(waRoot.handles.first { $0.phoneLast10 == "5550001111" }?.contactName, "Dana")

    let merged = PeopleGraphBuilder.mergedRoot(imessage: imRoot, whatsapp: waRoot)
    // Merge stamps each side's channel; the on-disk exports never carried one.
    XCTAssertTrue(merged.handles.contains { $0.channel == "whatsapp" && $0.phoneLast10 == "5550001111" })
    XCTAssertTrue(merged.handles.contains { $0.channel == "imessage" && $0.phoneLast10 == "5550001111" })
    XCTAssertTrue(merged.groups.contains { $0.channel == "whatsapp" })

    let people = PeopleGraphBuilder.buildCanonicalPeople(root: merged, contactsByPhone: [:])
    let graph = PeopleGraphBuilder.buildGraph(root: merged, people: people)
    let communities = PeopleGraphBuilder.buildCommunities(root: merged, people: people)
    let persons = PeopleGraphBuilder.createPeople(people: people, graph: graph, communities: communities)

    // ---- Dana dedupes across channels → ONE canonical node ----
    let danaID = try XCTUnwrap(people.idByPhone["5550001111"], "Dana's phone must resolve to one node")
    let danaMatches = persons.filter { ($0["id"] as? String) == danaID }
    XCTAssertEqual(danaMatches.count, 1, "the same person on two channels must be a single card")
    let dana = try XCTUnwrap(danaMatches.first)
    XCTAssertEqual(dana["closeness"] as? Double, 130.0, "closeness sums message_count across channels (100+30)")
    let danaChannels = try XCTUnwrap(dana["channels"] as? [[String: Any]])
    XCTAssertEqual(
      Set(danaChannels.compactMap { $0["key"] as? String }), ["imessage", "whatsapp"],
      "Dana's card must show both connectors")
    // lastTouch attributes to the channel with the newest date (iMessage, 07-20 > WhatsApp 07-10).
    XCTAssertEqual((dana["lastTouch"] as? [String: Any])?["channel"] as? String, "imessage")

    // ---- WhatsApp-only people become nodes ----
    XCTAssertNotNil(people.idByPhone["5552223333"], "Eve (WhatsApp-only) must appear in the graph")
    XCTAssertNotNil(people.idByPhone["5554445555"], "a WhatsApp group-only member must appear")

    // ---- edges carry honest provenance ----
    XCTAssertTrue(
      graph.edges.contains { $0.sources == ["whatsapp"] }, "the WhatsApp group must yield whatsapp-sourced edges")
    XCTAssertTrue(
      graph.edges.contains { $0.sources == ["imessage"] }, "the iMessage group must yield imessage-sourced edges")
    XCTAssertEqual(graph.groupsUsedByChannel["whatsapp"], 1)
    XCTAssertEqual(graph.groupsUsedByChannel["imessage"], 1)

    // ---- communities carry the source channel ----
    let cabo = try XCTUnwrap(
      communities.list.first { ($0["name"] as? String) == "Cabo Trip" }, "the WhatsApp group is a community")
    XCTAssertEqual(cabo["channel"] as? String, "whatsapp")
    let roommates = try XCTUnwrap(communities.list.first { ($0["name"] as? String) == "Roommates" })
    XCTAssertEqual(roommates["channel"] as? String, "imessage")
  }
}
