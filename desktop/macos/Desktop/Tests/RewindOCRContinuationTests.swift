import XCTest

@testable import Omi_Computer

final class RewindOCRContinuationTests: XCTestCase {
  private enum TestFailure: Error, Equatable {
    case callback
    case perform
  }

  func testCallbackErrorWinsWhenPerformAlsoThrows() async {
    do {
      _ = try await RewindOCRService.awaitSingleVisionCompletion {
        (finish: @escaping @Sendable (Result<String, Error>) -> Bool) in
        XCTAssertTrue(finish(.failure(TestFailure.callback)))
        throw TestFailure.perform
      }
      XCTFail("expected callback error")
    } catch {
      XCTAssertEqual(error as? TestFailure, .callback)
    }
  }

  func testPerformErrorWinsOverLateCallback() async {
    let callbackGate = DispatchSemaphore(value: 0)
    let callbackResults = AsyncStream<Bool>.makeStream()
    do {
      _ = try await RewindOCRService.awaitSingleVisionCompletion {
        (finish: @escaping @Sendable (Result<String, Error>) -> Bool) in
        DispatchQueue.global(qos: .userInitiated).async {
          callbackGate.wait()
          callbackResults.continuation.yield(finish(.failure(TestFailure.callback)))
          callbackResults.continuation.finish()
        }
        throw TestFailure.perform
      }
      XCTFail("expected perform error")
    } catch {
      XCTAssertEqual(error as? TestFailure, .perform)
    }
    callbackGate.signal()
    let lateCallbackWon = await callbackResults.stream.first { _ in true }
    XCTAssertEqual(lateCallbackWon, false)
  }
}
