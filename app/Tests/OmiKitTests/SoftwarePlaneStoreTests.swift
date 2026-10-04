#if !SKIP
  import Foundation
  import XCTest
  @testable import OmiKit

  final class SoftwarePlaneStoreTests: XCTestCase {
    private func withStore(_ body: (UserDefaultsSoftwarePlaneStore) throws -> Void) rethrows {
      // A unique test-only domain, never the app's standard preferences.
      let domain = "omi.tests.plane.\(UUID().uuidString)"
      let defaults = UserDefaults(suiteName: domain)!
      defer { defaults.removePersistentDomain(forName: domain) }
      try body(UserDefaultsSoftwarePlaneStore(defaults: defaults))
    }

    func testSamePlaneAndABAPublicationsChangeRevision() throws {
      try withStore { store in
        store.storeSoftwarePlane(.old)
        let first = store.softwarePlaneSnapshot()
        try store.commitSoftwarePlane(.old) {}
        let samePlane = store.softwarePlaneSnapshot()
        XCTAssertEqual(samePlane.storedPlane, first.storedPlane)
        XCTAssertNotEqual(samePlane.revision, first.revision)
        store.storeSoftwarePlane(.new)
        store.storeSoftwarePlane(.old)
        let returned = store.softwarePlaneSnapshot()
        XCTAssertEqual(returned.storedPlane, first.storedPlane)
        XCTAssertNotEqual(returned.revision, samePlane.revision)
      }
    }

    func testFailedPersistenceKeepsPlaneAndRetiresReaders() throws {
      try withStore { store in
        store.storeSoftwarePlane(.old)
        let before = store.softwarePlaneSnapshot()
        XCTAssertThrowsError(
          try store.commitSoftwarePlane(.new) {
            throw PlaneSaveError.unavailable
          })
        let after = store.softwarePlaneSnapshot()
        XCTAssertEqual(after.storedPlane, "old")
        XCTAssertNotEqual(after.revision, before.revision)
      }
    }

    func testSnapshotCannotObserveCredentialsBeforePlanePublication() {
      withStore { store in
        store.storeSoftwarePlane(.old)
        let persistenceEntered = expectation(description: "credential persistence entered")
        let readerEntered = expectation(description: "concurrent reader entered")
        let readerFinished = expectation(description: "reader completed after publication")
        let commitFinished = expectation(description: "publication completed")
        let releasePersistence = DispatchSemaphore(value: 0)
        let readerReturned = DispatchSemaphore(value: 0)
        defer { releasePersistence.signal() }
        DispatchQueue.global().async {
          defer { commitFinished.fulfill() }
          do {
            try store.commitSoftwarePlane(.new) {
              persistenceEntered.fulfill()
              XCTAssertEqual(releasePersistence.wait(timeout: .now() + 5), .success)
            }
          } catch { XCTFail("Unexpected persistence failure: \(error)") }
        }
        wait(for: [persistenceEntered], timeout: 2)
        DispatchQueue.global().async {
          readerEntered.fulfill()
          // If publication is not atomic, this returns the old plane
          // while the simulated new credentials are already being saved.
          XCTAssertEqual(store.softwarePlaneSnapshot().storedPlane, "new")
          readerReturned.signal()
          readerFinished.fulfill()
        }
        wait(for: [readerEntered], timeout: 2)
        XCTAssertEqual(readerReturned.wait(timeout: .now() + 0.1), .timedOut)
        releasePersistence.signal()
        wait(for: [readerFinished, commitFinished], timeout: 2)
      }
    }
  }

  private enum PlaneSaveError: Error { case unavailable }
#endif
