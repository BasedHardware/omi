import XCTest

@testable import Omi_Computer

final class DebouncedSearchCoordinatorTests: XCTestCase {
  @MainActor
  func testQueryNormalizationMatchesAcrossSearchSurfaces() {
    XCTAssertEqual(DebouncedSearchCoordinator.normalized("  project atlas \n"), "project atlas")
    XCTAssertEqual(DebouncedSearchCoordinator.normalized(" \n\t "), "")
    XCTAssertTrue(DebouncedSearchCoordinator.isActive(" project atlas "))
    XCTAssertFalse(DebouncedSearchCoordinator.isActive(" \n\t "))
    XCTAssertEqual(DebouncedSearchCoordinator.standardDelayNanoseconds, 250_000_000)
  }

  @MainActor
  func testNonEmptyQueryCommitsThroughInjectedDebounceSleeper() async {
    let committed = expectation(description: "query committed")
    let coordinator = DebouncedSearchCoordinator(
      sleeper: { _ in }
    )

    coordinator.submit("  release notes  ") { query in
      XCTAssertEqual(query, "release notes")
      committed.fulfill()
    }

    await fulfillment(of: [committed], timeout: 1)
  }

  @MainActor
  func testClearingSearchCommitsImmediately() async {
    let committed = expectation(description: "clear committed")
    let coordinator = DebouncedSearchCoordinator(
      sleeper: { _ in
        XCTFail("Clearing search must not wait for the debounce sleeper")
      }
    )

    coordinator.submit("   ") { query in
      XCTAssertEqual(query, "")
      committed.fulfill()
    }

    await fulfillment(of: [committed], timeout: 1)
  }
}
