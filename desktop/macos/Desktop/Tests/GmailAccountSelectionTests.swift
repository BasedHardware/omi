import XCTest

@testable import Omi_Computer

final class GmailAccountSelectionTests: XCTestCase {
  override func setUp() {
    super.setUp()
    GmailSelectionStore.resetForTesting()
  }

  override func tearDown() {
    GmailSelectionStore.resetForTesting()
    super.tearDown()
  }

  private func config(_ name: String, _ path: String) -> [String: String] {
    ["name": name, "db_path": path, "password": "pw"]
  }

  func testFilterKeepsOnlySelectedProfileWhenPresent() {
    let configs = [
      config("Chrome (Default)", "/a/Default/Network/Cookies"),
      config("Chrome (Work)", "/a/Profile 1/Network/Cookies"),
    ]
    GmailSelectionStore.persist(cookiePath: "/a/Profile 1/Network/Cookies", label: "work@corp.com")

    XCTAssertEqual(
      GmailSelectionStore.filter(configs),
      [config("Chrome (Work)", "/a/Profile 1/Network/Cookies")]
    )
  }

  func testFilterFallsBackToAllConfigsWhenSelectedProfileIsGone() {
    let configs = [
      config("Chrome (Default)", "/a/Default/Network/Cookies"),
      config("Chrome (Work)", "/a/Profile 1/Network/Cookies"),
    ]
    GmailSelectionStore.persist(cookiePath: "/gone/Profile 9/Network/Cookies", label: "old@corp.com")

    XCTAssertEqual(GmailSelectionStore.filter(configs), configs)
  }

  func testFilterReturnsAllWhenNoSelectionMade() {
    let configs = [
      config("Chrome (Default)", "/a/Default/Network/Cookies"),
      config("Arc", "/b/Default/Network/Cookies"),
    ]

    XCTAssertEqual(GmailSelectionStore.filter(configs), configs)
    XCTAssertFalse(GmailSelectionStore.hasMadeChoice)
  }

  func testSnapshotFilterUsesProvidedPathNotCurrentSelection() {
    let configs = [
      config("Chrome (Default)", "/a/Default/Network/Cookies"),
      config("Chrome (Work)", "/a/Profile 1/Network/Cookies"),
    ]
    // A snapshot taken before the selection changed must still resolve against
    // the snapshot's profile, not the freshly persisted one.
    let snapshot = GmailSelectionStore.selectedCookiePath
    GmailSelectionStore.persist(cookiePath: "/a/Profile 1/Network/Cookies", label: "work@corp.com")

    XCTAssertEqual(
      GmailSelectionStore.filter(configs, selectedCookiePath: snapshot),
      configs)
    XCTAssertEqual(
      GmailSelectionStore.filter(configs, selectedCookiePath: "/a/Profile 1/Network/Cookies"),
      [config("Chrome (Work)", "/a/Profile 1/Network/Cookies")])
  }

  func testSnapshotFilterFallsBackWhenSnapshotProfileIsGone() {
    let configs = [
      config("Chrome (Default)", "/a/Default/Network/Cookies")
    ]
    XCTAssertEqual(
      GmailSelectionStore.filter(configs, selectedCookiePath: "/gone/Profile 9/Network/Cookies"),
      configs)
  }

  func testHasMadeChoiceAfterPersist() {
    XCTAssertFalse(GmailSelectionStore.hasMadeChoice)
    GmailSelectionStore.persist(cookiePath: nil, label: "Automatic")
    XCTAssertTrue(GmailSelectionStore.hasMadeChoice)
    XCTAssertNil(GmailSelectionStore.selectedCookiePath)
  }

  func testParseAccountsMapsPythonOutput() {
    let json: [String: Any] = [
      "ok": true,
      "accounts": [
        ["name": "Chrome (Work)", "db_path": "/a/Profile 1/Network/Cookies", "email": "work@corp.com"],
        ["name": "Arc", "db_path": "/b/Default/Network/Cookies", "email": NSNull()],
        ["name": "Chrome (Default)", "db_path": "/a/Default/Network/Cookies", "email": "junk@gmail.com"],
      ],
    ]

    let accounts = GmailAccountProbe.parseAccounts(json)

    XCTAssertEqual(accounts.count, 2)
    XCTAssertEqual(accounts[0].browserName, "Chrome (Default)")
    XCTAssertEqual(accounts[0].email, "junk@gmail.com")
    XCTAssertEqual(accounts[1].browserName, "Chrome (Work)")
    XCTAssertEqual(accounts[1].id, "/a/Profile 1/Network/Cookies")
  }

  func testParseAccountsSkipsRowsWithoutPath() {
    let json: [String: Any] = [
      "ok": true,
      "accounts": [
        ["name": "No Path", "email": "x@y.com"],
        ["name": "Arc", "db_path": "/b/Default/Network/Cookies", "email": NSNull()],
      ],
    ]

    let accounts = GmailAccountProbe.parseAccounts(json)

    XCTAssertTrue(accounts.isEmpty)
  }
}
