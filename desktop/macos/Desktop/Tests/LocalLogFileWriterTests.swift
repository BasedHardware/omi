import XCTest

@testable import Omi_Computer

final class LocalLogFileWriterTests: XCTestCase {
  func testAppendCreatesAndAppendsToFile() throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-log-writer-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }

    let logFile = directory.appendingPathComponent("omi.log")
    guard case .success = LocalLogFileWriter.append(Data("first\n".utf8), to: logFile.path) else {
      return XCTFail("Expected first append to succeed")
    }
    guard case .success = LocalLogFileWriter.append(Data("second\n".utf8), to: logFile.path) else {
      return XCTFail("Expected second append to succeed")
    }

    let contents = try String(contentsOf: logFile, encoding: .utf8)
    XCTAssertEqual(contents, "first\nsecond\n")
  }

  func testAppendFailureReturnsErrorInsteadOfRaisingException() throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-log-writer-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }

    let result = LocalLogFileWriter.append(Data("line\n".utf8), to: directory.path)
    guard case .failure(let error) = result else {
      return XCTFail("Appending to a directory should fail")
    }

    XCTAssertTrue(error.description.contains("failed"))
  }
}
