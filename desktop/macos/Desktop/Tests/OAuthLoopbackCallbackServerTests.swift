import XCTest
import Darwin
@testable import Omi_Computer

final class OAuthLoopbackCallbackServerTests: XCTestCase {
  func testReceivesCodeAndStateFromLoopbackCallback() async throws {
    let server = try OAuthLoopbackCallbackServer.start(expectedState: "test-state")
    defer { server.stop() }

    let callbackTask = Task {
      try await server.waitForCallback()
    }

    let response = try sendLoopbackRequest(port: server.port, target: "/callback?code=test-code&state=test-state")
    XCTAssertTrue(response.hasPrefix("HTTP/1.1 200 OK"))

    let result = try await callbackTask.value
    XCTAssertEqual(result.code, "test-code")
    XCTAssertEqual(result.state, "test-state")

    server.stop()
    server.stop()
  }

  func testIgnoresInvalidAndMismatchedRequestsBeforeValidCallback() async throws {
    let server = try OAuthLoopbackCallbackServer.start(expectedState: "expected-state")
    defer { server.stop() }

    let callbackTask = Task {
      try await server.waitForCallback()
    }

    let invalidResponse = try sendLoopbackRequest(port: server.port, target: "/favicon.ico")
    XCTAssertTrue(invalidResponse.hasPrefix("HTTP/1.1 400 Bad Request"))

    let mismatchedResponse = try sendLoopbackRequest(port: server.port, target: "/callback?code=bad&state=wrong-state")
    XCTAssertTrue(mismatchedResponse.hasPrefix("HTTP/1.1 400 Bad Request"))

    let validResponse = try sendLoopbackRequest(port: server.port, target: "/callback?code=good-code&state=expected-state")
    XCTAssertTrue(validResponse.hasPrefix("HTTP/1.1 200 OK"))

    let result = try await callbackTask.value
    XCTAssertEqual(result.code, "good-code")
    XCTAssertEqual(result.state, "expected-state")
  }

  private func sendLoopbackRequest(port: UInt16, target: String) throws -> String {
    let fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
    XCTAssertGreaterThanOrEqual(fd, 0)
    defer { close(fd) }

    var addr = sockaddr_in()
    addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = port.bigEndian
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr)

    let connectResult = withUnsafePointer(to: &addr) {
      $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
      }
    }
    XCTAssertEqual(connectResult, 0)

    let request = "GET \(target) HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
    request.withCString { pointer in
      _ = send(fd, pointer, strlen(pointer), 0)
    }

    var data = Data()
    var buffer = [UInt8](repeating: 0, count: 4096)
    while true {
      let count = recv(fd, &buffer, buffer.count, 0)
      if count > 0 {
        data.append(buffer, count: count)
      } else {
        break
      }
    }
    return String(data: data, encoding: .utf8) ?? ""
  }
}
