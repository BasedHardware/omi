import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class OnboardingNoteReceiverTests: XCTestCase {
  func testParserDecodesStripsControlsTrimsAndBoundsNote() {
    let longSuffix = String(repeating: "a", count: 1_600)
    let request = requestHead(
      target: "/onboarding/note?nonce=bound-nonce&note=%20Hello%E2%80%94there%00%0A+\(longSuffix)%20"
    )

    guard case .accepted(let note) = OnboardingNoteReceiver.parse(requestHead: request, nonce: "bound-nonce") else {
      XCTFail("Expected the note request to be accepted")
      return
    }

    XCTAssertTrue(note.hasPrefix("Hello—there+"))
    XCTAssertFalse(note.unicodeScalars.contains(where: CharacterSet.controlCharacters.contains))
    XCTAssertEqual(note.unicodeScalars.count, 1_500)
  }

  func testParserRejectsInvalidRequests() {
    let validTarget = "/onboarding/note?nonce=bound-nonce&note=hello"
    let rejectedRequests = [
      requestHead(target: "/onboarding/note?nonce=wrong&note=hello"),
      requestHead(target: "/onboarding/note?note=hello"),
      requestHead(target: "/onboarding/note?nonce=bound-nonce"),
      requestHead(target: "/other?nonce=bound-nonce&note=hello"),
      requestHead(method: "POST", target: validTarget),
      requestHead(target: "/onboarding/note?nonce=bound-nonce&note="),
      requestHead(target: "/onboarding/note?nonce=bound-nonce&note=%00%0A"),
      "GET \(validTarget) HTTP/1.1\r\nX-Fill: \(String(repeating: "x", count: 16 * 1_024))",
    ]

    for request in rejectedRequests {
      XCTAssertEqual(
        OnboardingNoteReceiver.parse(requestHead: request, nonce: "bound-nonce"),
        .rejected,
        "Expected request to be rejected: \(request.prefix(80))"
      )
    }
  }

  func testLoopbackRoundTripAcceptsOnceAndStopsListener() async throws {
    let receiver = OnboardingNoteReceiver(nonce: "socket-nonce")
    let received = expectation(description: "received one decoded note")
    received.expectedFulfillmentCount = 1
    received.assertForOverFulfill = true
    var callbackCount = 0
    var callbackNote: String?
    receiver.onNote = { note in
      callbackCount += 1
      callbackNote = note
      received.fulfill()
    }

    let port = try await receiver.start()
    defer { receiver.stop() }

    let rejectedResponse = try await response(
      port: port,
      target: "/onboarding/note?nonce=wrong&note=ignored"
    )
    XCTAssertEqual(rejectedResponse.statusCode, 404)
    XCTAssertEqual(callbackCount, 0)

    let acceptedResponse = try await response(
      port: port,
      target: "/onboarding/note?nonce=socket-nonce&note=Ship%20it%E2%80%94today"
    )
    XCTAssertEqual(acceptedResponse.statusCode, 204)
    await fulfillment(of: [received], timeout: 2)
    XCTAssertEqual(callbackCount, 1)
    XCTAssertEqual(callbackNote, "Ship it—today")

    do {
      _ = try await response(
        port: port,
        target: "/onboarding/note?nonce=socket-nonce&note=second"
      )
      XCTFail("Expected the callback-triggered stop to make the port unreachable")
    } catch {
      XCTAssertEqual(callbackCount, 1)
    }
  }

  private func requestHead(method: String = "GET", target: String) -> String {
    "\(method) \(target) HTTP/1.1\r\nHost: 127.0.0.1"
  }

  private func response(port: UInt16, target: String) async throws -> HTTPURLResponse {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.timeoutIntervalForRequest = 1
    configuration.timeoutIntervalForResource = 1
    let session = URLSession(configuration: configuration)
    defer { session.invalidateAndCancel() }

    guard let url = URL(string: "http://127.0.0.1:\(port)\(target)") else {
      throw URLError(.badURL)
    }
    let (_, response) = try await session.data(from: url)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw URLError(.badServerResponse)
    }
    return httpResponse
  }
}
