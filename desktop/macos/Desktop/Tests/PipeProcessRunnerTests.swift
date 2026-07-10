import XCTest

@testable import Omi_Computer

final class PipeProcessRunnerTests: XCTestCase {
  func testDrainsLargeStdoutBeforeWaitingForExit() throws {
    let result = try PipeProcessRunner.run(
      executableURL: URL(fileURLWithPath: "/usr/bin/python3"),
      arguments: [
        "-c",
        "import sys; sys.stdout.write('x' * (1024 * 1024)); sys.stdout.flush()",
      ],
      timeoutSeconds: 5
    )

    XCTAssertEqual(result.terminationStatus, 0)
    XCTAssertEqual(result.stdout.count, 1024 * 1024)
    XCTAssertFalse(result.timedOut)
  }

  func testDrainsLargeStderrBeforeWaitingForExit() throws {
    let result = try PipeProcessRunner.run(
      executableURL: URL(fileURLWithPath: "/usr/bin/python3"),
      arguments: [
        "-c",
        "import sys; sys.stderr.write('x' * (1024 * 1024)); sys.stderr.flush()",
      ],
      timeoutSeconds: 5
    )

    XCTAssertEqual(result.terminationStatus, 0)
    XCTAssertEqual(result.stderr.count, 1024 * 1024)
    XCTAssertFalse(result.timedOut)
  }

  func testTimesOutHungProcessWithActionableError() {
    XCTAssertThrowsError(
      try PipeProcessRunner.run(
        executableURL: URL(fileURLWithPath: "/bin/sh"),
        arguments: ["-c", "sleep 5"],
        timeoutSeconds: 0.2,
        killGraceSeconds: 0.1
      )
    ) { error in
      let message = error.localizedDescription
      XCTAssertTrue(message.contains("timed out"), message)
    }
  }

  func testWritesStdinAndDrainsStdout() throws {
    let result = try PipeProcessRunner.run(
      executableURL: URL(fileURLWithPath: "/usr/bin/python3"),
      arguments: [
        "-c",
        "import sys; sys.stdout.write(sys.stdin.read().upper())",
      ],
      stdinData: Data("browser config".utf8),
      timeoutSeconds: 5
    )

    XCTAssertEqual(result.terminationStatus, 0)
    XCTAssertEqual(String(data: result.stdout, encoding: .utf8), "BROWSER CONFIG")
  }

  func testPassesEnvironmentOverrides() throws {
    let result = try PipeProcessRunner.run(
      executableURL: URL(fileURLWithPath: "/bin/sh"),
      arguments: ["-c", "printf %s \"$OMI_PIPE_PROCESS_TEST\""],
      environment: ["OMI_PIPE_PROCESS_TEST": "custom-env"],
      timeoutSeconds: 5
    )

    XCTAssertEqual(result.terminationStatus, 0)
    XCTAssertEqual(String(data: result.stdout, encoding: .utf8), "custom-env")
  }
}
