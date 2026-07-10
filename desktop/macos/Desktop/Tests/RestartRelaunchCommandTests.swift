import XCTest

@testable import Omi_Computer

/// PERM-06: after a Quit & Reopen the reopened bundle must stay reachable on the
/// harness's *original* automation port.
///
/// The bug (Codex Wave 18 FAIL): `AppState.restartApp()` relaunches via a bare
/// `open <bundle>` — no argv, no env. The bridge resolves its port argv → env →
/// default, so the reopened app fell back to whatever `OMI_AUTOMATION_PORT` the
/// launchd session carried (or 47777), NOT the port the harness launched with
/// (e.g. 47894 via `--automation-port=`). The harness kept polling the pre-quit
/// port, found no listener, and could not prove signed-in/onboarded continuity.
///
/// The fix re-passes the port as an argv on the non-prod relaunch, since argv is
/// the highest-precedence port source and beats any inherited env. These pin the
/// command the relaunch runs; the live stall→reopen path is the e2e / Codex lane
/// (SKILL §2i). `restartApp()` itself can't be unit-run (it terminates the host).
final class RestartRelaunchCommandTests: XCTestCase {

  func testNonProdRelaunchRePassesTheAutomationPort() {
    let cmd = AppState.relaunchCommand(
      appPath: "/Applications/omi-perm06v.app", isNonProduction: true, automationPort: 47894)
    XCTAssertTrue(
      cmd.contains("open \"/Applications/omi-perm06v.app\""),
      "must open the resolved bundle path")
    XCTAssertTrue(
      cmd.contains("--args --automation-port=47894"),
      "non-prod relaunch must re-pass the port so the reopened bundle rebinds it")
  }

  func testProdRelaunchIsBareOpenWithNoAutomationArgs() {
    let cmd = AppState.relaunchCommand(
      appPath: "/Applications/Omi.app", isNonProduction: false, automationPort: 47894)
    XCTAssertEqual(
      cmd, "sleep 0.5 && open \"/Applications/Omi.app\"",
      "production relaunch must stay a plain `open` — no automation args, byte-identical to before")
  }

  func testDelayPrecedesOpenSoTheRestartResponseFlushes() {
    // restartApp() terminates the process; the relaunch must be scheduled after the
    // `sleep` so the in-flight HTTP/UI action completes before the app dies.
    let cmd = AppState.relaunchCommand(
      appPath: "/Applications/omi-x.app", isNonProduction: true, automationPort: 1)
    guard let sleepIdx = cmd.range(of: "sleep"), let openIdx = cmd.range(of: "open") else {
      return XCTFail("relaunch command must both sleep and open")
    }
    XCTAssertTrue(sleepIdx.lowerBound < openIdx.lowerBound, "the delay must precede the open")
  }

  func testPortFlagMatchesTheBridgesOwnPrefix() {
    // The re-passed flag must be the exact one the bridge parses, so DRY on the
    // single source of truth rather than a hardcoded string that could drift.
    let cmd = AppState.relaunchCommand(
      appPath: "/Applications/omi-x.app", isNonProduction: true, automationPort: 40000)
    XCTAssertTrue(cmd.contains("\(DesktopAutomationLaunchOptions.portPrefix)40000"))
  }
}
