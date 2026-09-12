import XCTest

final class IsolatedTestDefaultsTests: XCTestCase {
  @MainActor
  func testXCTestHelperCleansDomainBeforeEarlierTeardownBlocks() throws {
    var retainedDefaults: UserDefaults?
    // XCTest runs teardown blocks in reverse registration order. Keep a defaults
    // reference alive until after the helper's teardown has removed its domain.
    addTeardownBlock {
      XCTAssertNil(retainedDefaults?.string(forKey: "auth_userId"))
    }
    retainedDefaults = try makeIsolatedDefaults()
    retainedDefaults?.set("owner", forKey: "auth_userId")
  }

  func testFixturesKeepTheSameAuthKeyIndependentAndCleanOnlyTheirOwnedDomain() throws {
    let first = try IsolatedTestDefaults()
    let second = try IsolatedTestDefaults()
    let key = "auth_userId"
    first.defaults.set("owner-a", forKey: key)
    XCTAssertNil(second.defaults.string(forKey: key))
    second.defaults.set("owner-b", forKey: key)

    XCTAssertNotEqual(first.suiteName, second.suiteName)
    XCTAssertEqual(first.defaults.string(forKey: key), "owner-a")
    first.cleanUp()
    first.cleanUp()
    XCTAssertNil(first.defaults.string(forKey: key))
    XCTAssertEqual(second.defaults.string(forKey: key), "owner-b")
  }

  func testReleasingFixtureCleansDomainEvenWhenDefaultsAreRetained() throws {
    var fixture: IsolatedTestDefaults? = try IsolatedTestDefaults()
    let defaults = try XCTUnwrap(fixture?.defaults)
    defaults.set("owner", forKey: "auth_userId")
    fixture = nil
    XCTAssertNil(defaults.string(forKey: "auth_userId"))
  }
}
