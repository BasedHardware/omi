import XCTest

final class IsolatedTestDefaultsTests: XCTestCase {
  @MainActor
  func testDefaultsHandleCanCrossIntoANonisolatedAsyncAPI() async throws {
    let defaults = try makeIsolatedDefaults()
    defaults.set("owner", forKey: "auth_userId")
    let owner = await Self.readOwner(defaults: defaults)
    XCTAssertEqual(owner, "owner")
    XCTAssertEqual(defaults.string(forKey: "auth_userId"), "owner")
  }

  private nonisolated static func readOwner(defaults: UserDefaults) async -> String? {
    defaults.string(forKey: "auth_userId")
  }

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
    let first = IsolatedTestDefaults()
    let firstDefaults = try first.makeDefaults()
    let second = IsolatedTestDefaults()
    let secondDefaults = try second.makeDefaults()
    let key = "auth_userId"
    firstDefaults.set("owner-a", forKey: key)
    XCTAssertNil(secondDefaults.string(forKey: key))
    secondDefaults.set("owner-b", forKey: key)

    XCTAssertNotEqual(first.suiteName, second.suiteName)
    XCTAssertEqual(firstDefaults.string(forKey: key), "owner-a")
    first.cleanUp()
    first.cleanUp()
    XCTAssertNil(firstDefaults.string(forKey: key))
    XCTAssertEqual(secondDefaults.string(forKey: key), "owner-b")
  }

  func testReleasingFixtureCleansDomainEvenWhenDefaultsAreRetained() throws {
    var fixture: IsolatedTestDefaults? = IsolatedTestDefaults()
    let defaults = try XCTUnwrap(fixture).makeDefaults()
    defaults.set("owner", forKey: "auth_userId")
    fixture = nil
    XCTAssertNil(defaults.string(forKey: "auth_userId"))
  }
}
