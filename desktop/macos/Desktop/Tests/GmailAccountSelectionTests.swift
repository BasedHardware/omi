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

  func testFilterReturnsNoConfigsWhenSelectedProfileIsGone() {
    let configs = [
      config("Chrome (Default)", "/a/Default/Network/Cookies"),
      config("Chrome (Work)", "/a/Profile 1/Network/Cookies"),
    ]
    GmailSelectionStore.persist(cookiePath: "/gone/Profile 9/Network/Cookies", label: "old@corp.com")

    XCTAssertEqual(GmailSelectionStore.filter(configs), [])
  }

  func testFilterReturnsAllWhenNoSelectionMade() {
    let configs = [
      config("Chrome (Default)", "/a/Default/Network/Cookies"),
      config("Arc", "/b/Default/Network/Cookies"),
    ]

    XCTAssertEqual(GmailSelectionStore.filter(configs), configs)
    XCTAssertFalse(GmailSelectionStore.hasMadeChoice)
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

    // Rows without a non-empty email are filtered out; remaining rows are
    // sorted by browser name.
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
        ["name": "Arc", "db_path": "/b/Default/Network/Cookies", "email": "arc@example.com"],
      ],
    ]

    let accounts = GmailAccountProbe.parseAccounts(json)

    XCTAssertEqual(accounts.count, 1)
    XCTAssertEqual(accounts[0].browserName, "Arc")
  }
}
