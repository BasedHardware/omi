import XCTest

private let isolatedDefaultsOwnerKey = "auth_userId"

final class IsolatedTestDefaultsTests: XCTestCase {
  @MainActor
  func testDefaultsHandleCanCrossIntoANonisolatedAsyncAPI() async throws {
    let defaults = try makeIsolatedDefaults()
    defaults.set("owner", forKey: isolatedDefaultsOwnerKey)
    let owner = await Self.readOwner(defaults: defaults)
    XCTAssertEqual(owner, "owner")
    XCTAssertEqual(defaults.string(forKey: isolatedDefaultsOwnerKey), "owner")
  }

  private nonisolated static func readOwner(defaults: UserDefaults) async -> String? {
    defaults.string(forKey: isolatedDefaultsOwnerKey)
  }

  @MainActor
  func testXCTestHelperCleansDomainBeforeEarlierTeardownBlocks() throws {
    var retainedDefaults: UserDefaults?
    // XCTest runs teardown blocks in reverse registration order. Keep a defaults
    // reference alive until after the helper's teardown has removed its domain.
    addTeardownBlock {
      XCTAssertNil(retainedDefaults?.string(forKey: isolatedDefaultsOwnerKey))
    }
    retainedDefaults = try makeIsolatedDefaults()
    retainedDefaults?.set("owner", forKey: isolatedDefaultsOwnerKey)
  }

  func testFixturesKeepTheSameAuthKeyIndependentAndCleanOnlyTheirOwnedDomain() throws {
    let first = IsolatedTestDefaults()
    let firstDefaults = try first.makeDefaults()
    let second = IsolatedTestDefaults()
    let secondDefaults = try second.makeDefaults()
    let key = isolatedDefaultsOwnerKey
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
    defaults.set("owner", forKey: isolatedDefaultsOwnerKey)
    fixture = nil
    XCTAssertNil(defaults.string(forKey: isolatedDefaultsOwnerKey))
  }
}
