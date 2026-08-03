import XCTest

@testable import Omi_Computer

/// `PeopleListOrder` decides what the People directory shows and in what order,
/// so it is tested directly. People are built by decoding JSON because
/// `PeopleIntelPerson` is decode-only — which also keeps these tests honest
/// about the on-disk shape.
final class PeopleListTableTests: XCTestCase {

  private func person(_ json: String) throws -> PeopleIntelPerson {
    try JSONDecoder().decode(PeopleIntelPerson.self, from: Data(json.utf8))
  }

  private func people(_ jsons: [String]) throws -> [PeopleIntelPerson] {
    try jsons.map(person)
  }

  // MARK: - Reach

  func testReachSumsEveryChannel() throws {
    let p = try person(
      #"""
      {"id":"a","name":"Ada","channels":[
        {"key":"imessage","label":"iMessage","count":40},
        {"key":"whatsapp","label":"WhatsApp","count":2}]}
      """#)
    XCTAssertEqual(PeopleListOrder.reach(p), 42)
    XCTAssertEqual(PeopleListOrder.reach(try person(#"{"id":"z","name":"Zed"}"#)), 0)
  }

  // MARK: - Sorting

  func testSortByNameIsCaseInsensitiveAndReversible() throws {
    let rows = try people([
      #"{"id":"b","name":"bruno"}"#,
      #"{"id":"a","name":"Ada"}"#,
      #"{"id":"c","name":"Cy"}"#,
    ])
    XCTAssertEqual(
      PeopleListOrder.sorted(rows, by: .name, descending: false).map(\.id), ["a", "b", "c"])
    XCTAssertEqual(
      PeopleListOrder.sorted(rows, by: .name, descending: true).map(\.id), ["c", "b", "a"])
  }

  func testSortByReachBreaksTiesByNameSoOrderIsStable() throws {
    let rows = try people([
      #"{"id":"z","name":"Zed","channels":[{"key":"imessage","label":"iMessage","count":5}]}"#,
      #"{"id":"a","name":"Ada","channels":[{"key":"imessage","label":"iMessage","count":5}]}"#,
      #"{"id":"m","name":"Mia","channels":[{"key":"imessage","label":"iMessage","count":9}]}"#,
    ])
    // Ascending: the two 5s come first, ordered by name; then the 9.
    XCTAssertEqual(
      PeopleListOrder.sorted(rows, by: .reach, descending: false).map(\.id), ["a", "z", "m"])
    XCTAssertEqual(
      PeopleListOrder.sorted(rows, by: .reach, descending: true).map(\.id), ["m", "z", "a"])
  }

  func testSortByLastTouchPutsNewestFirstWhenDescending() throws {
    let rows = try people([
      #"{"id":"old","name":"Old","lastTouch":{"channel":"imessage","date":"2026-01-01T00:00:00Z"}}"#,
      #"{"id":"new","name":"New","lastTouch":{"channel":"imessage","date":"2026-06-01T00:00:00Z"}}"#,
    ])
    XCTAssertEqual(
      PeopleListOrder.sorted(rows, by: .lastTouch, descending: true).map(\.id), ["new", "old"])
    XCTAssertEqual(
      PeopleListOrder.sorted(rows, by: .lastTouch, descending: false).map(\.id), ["old", "new"])
  }

  func testPeopleWithNoLastTouchSortOldestRatherThanDisappearing() throws {
    let rows = try people([
      #"{"id":"none","name":"Nora"}"#,
      #"""
      {"id":"dated","name":"Dana","lastTouch":{"channel":"imessage","date":"2026-06-01T00:00:00Z"}}
      """#,
    ])
    let newestFirst = PeopleListOrder.sorted(rows, by: .lastTouch, descending: true)
    XCTAssertEqual(
      newestFirst.map(\.id), ["dated", "none"],
      "a person we have never touched must still be listed, just last")
    XCTAssertEqual(newestFirst.count, rows.count, "sorting must never drop a row")
  }

  func testUnparseableLastTouchDateIsTreatedAsNoTouchNotACrash() throws {
    let rows = try people([
      #"{"id":"bad","name":"Bad","lastTouch":{"channel":"imessage","date":"not-a-date"}}"#,
      #"""
      {"id":"good","name":"Good","lastTouch":{"channel":"imessage","date":"2026-06-01T00:00:00Z"}}
      """#,
    ])
    XCTAssertEqual(
      PeopleListOrder.sorted(rows, by: .lastTouch, descending: true).map(\.id), ["good", "bad"])
  }

  func testSortingPreservesEveryRow() throws {
    let rows = try people([
      #"{"id":"a","name":"Ada","channels":[{"key":"voice","label":"Voice","count":1}]}"#,
      #"{"id":"b","name":"Bo"}"#,
      #"{"id":"c","name":"Cy","lastTouch":{"channel":"imessage","date":"2026-06-01T00:00:00Z"}}"#,
    ])
    for sort in PeopleListSort.allCases {
      for descending in [true, false] {
        XCTAssertEqual(
          Set(PeopleListOrder.sorted(rows, by: sort, descending: descending).map(\.id)),
          ["a", "b", "c"],
          "\(sort) descending=\(descending) changed the row set")
      }
    }
  }
}
