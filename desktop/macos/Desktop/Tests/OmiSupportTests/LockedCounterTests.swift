import OmiSupport
import XCTest

final class LockedCounterTests: XCTestCase {
  func testCountsEveryIncrementAcrossConcurrentTasks() async {
    let counter = LockedCounter()
    await withTaskGroup(of: Void.self) { group in
      for _ in 0..<100 {
        group.addTask { counter.increment() }
      }
    }
    XCTAssertEqual(counter.count, 100)
  }

  func testIncrementReturnsTheNewCount() {
    let counter = LockedCounter()
    XCTAssertEqual(counter.increment(), 1)
    XCTAssertEqual(counter.increment(), 2)
    XCTAssertEqual(counter.count, 2)
  }
}
