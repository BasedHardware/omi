import XCTest

@testable import Omi_Computer

final class ClaudeCodeSessionsTests: XCTestCase {
  func testMatchesCLIBinariesOnly() {
    // Native install and pnpm/bun bundle layouts.
    XCTAssertTrue(ClaudeCodeSessions.isClaudeCLI(executablePath: "/Users/x/.local/bin/claude"))
    XCTAssertTrue(
      ClaudeCodeSessions.isClaudeCLI(
        executablePath:
          "/Users/x/Library/pnpm/global/5/.pnpm/@anthropic-ai+claude-code@2.1.190/node_modules/@anthropic-ai/claude-code/bin/claude.exe"
      ))

    // Claude Desktop and its helpers must never be killed.
    XCTAssertFalse(
      ClaudeCodeSessions.isClaudeCLI(executablePath: "/Applications/Claude.app/Contents/MacOS/Claude"))
    XCTAssertFalse(
      ClaudeCodeSessions.isClaudeCLI(
        executablePath:
          "/Applications/Claude.app/Contents/Frameworks/Claude Helper.app/Contents/MacOS/Claude Helper"))
    XCTAssertFalse(
      ClaudeCodeSessions.isClaudeCLI(executablePath: "/Applications/Claude.app/Contents/Helpers/chrome-native-host"))
    XCTAssertFalse(ClaudeCodeSessions.isClaudeCLI(executablePath: "claudette"))
  }

  func testCompletionSubtitleStates() {
    XCTAssertEqual(
      ClaudeCodeSessions.completionSubtitle(sessionCount: 0, didStop: false),
      "You're all set — Omi Memory loads automatically in your next Claude Code session.")
    XCTAssertEqual(
      ClaudeCodeSessions.completionSubtitle(sessionCount: 2, didStop: false),
      "Restart Claude Code to load Omi Memory.")
    XCTAssertEqual(
      ClaudeCodeSessions.completionSubtitle(sessionCount: 2, didStop: true),
      "Sessions stopped — run claude --continue in your terminal to pick up where you left off.")
  }
}
