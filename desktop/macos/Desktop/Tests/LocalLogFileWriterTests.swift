import Darwin
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
    XCTAssertEqual(try posixPermissions(of: logFile.path), 0o600)
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

    guard case .openFailed = error else {
      return XCTFail("Expected open failure, got \(error)")
    }
  }

  func testAppendRejectsSymlinkDestination() throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-log-writer-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }

    let target = directory.appendingPathComponent("target.log")
    try "original\n".write(to: target, atomically: true, encoding: .utf8)

    let symlink = directory.appendingPathComponent("omi.log")
    try FileManager.default.createSymbolicLink(at: symlink, withDestinationURL: target)

    let result = LocalLogFileWriter.append(Data("line\n".utf8), to: symlink.path)
    guard case .failure(let error) = result else {
      return XCTFail("Appending to a symlink should fail")
    }

    guard case .openFailed(let code) = error else {
      return XCTFail("Expected open failure, got \(error)")
    }
    XCTAssertEqual(code, ELOOP)
    XCTAssertEqual(try String(contentsOf: target, encoding: .utf8), "original\n")
  }

  private func posixPermissions(of path: String) throws -> Int {
    let attributes = try FileManager.default.attributesOfItem(atPath: path)
    let number = try XCTUnwrap(attributes[.posixPermissions] as? NSNumber)
    return number.intValue
  }
}
