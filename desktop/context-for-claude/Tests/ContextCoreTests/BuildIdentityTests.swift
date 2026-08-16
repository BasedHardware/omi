import ContextCore
import Foundation
import XCTest

/// **Two builds may not share one platform identity.**
///
/// macOS stores a *code requirement* — which pins the signing certificate — beside every TCC grant,
/// keyed by bundle identifier. A locally signed developer build carrying the release's identifier
/// therefore writes a record the notarized release can never satisfy, and vice versa. Measured on a
/// developer's Mac, both bundles claiming `com.omi.context-for-claude`:
///
/// ```
/// dev      identifier "com.omi.context-for-claude" and certificate leaf = H"bb925114bcb6…"
/// release  identifier "com.omi.context-for-claude" and anchor apple generic
///          and … certificate leaf[subject.OU] = "9536L8KLMP"
/// ```
///
/// Whichever was granted first won the record; `tccd` refused the other one from then on, while
/// System Settings still drew the switch **on** — the allowed flag and the stored requirement are
/// separate fields, so toggling it forever changes nothing. That cost days of debugging.
///
/// A build not signed by Developer ID now gets its own identifier, and everything the OS or Claude
/// keys on follows it. These tests are about that "follows it": the identifiers must diverge for a
/// development build and must be *exactly* the shipping strings otherwise.
final class BuildIdentityTests: XCTestCase {

    private let shipping = ContextPaths.shippingBundleIdentifier
    private let development = ContextPaths.shippingBundleIdentifier + ".dev"

    // MARK: - Which identifier this process adopts

    /// **The measurement this whole guard exists for, asserted rather than assumed.**
    ///
    /// `Bundle.main` inside the XCTest runner is Xcode's `xctest` tool, not this app — measured
    /// here, and *not* nil, which is what a comment elsewhere in this package claims. Without the
    /// rule below, the log subsystem, the Keychain service and the `tccutil` line this test process
    /// resolves would all carry `com.apple.dt.xctest.tool`.
    func testTheTestRunnersOwnBundleIsNotAdoptedByThisProcess() {
        let reported = Bundle.main.bundleIdentifier
        XCTAssertNotEqual(
            reported, shipping,
            "this process is not running from the app bundle; if it were, the fallback below would prove nothing")
        XCTAssertEqual(
            ContextPaths.bundleIdentifier, shipping,
            """
            Reported \(reported ?? "nil"). Anything that is not ours must fall back to the shipping \
            identifier — adopting a foreign one puts a stranger's string on the log subsystem and \
            on a Keychain service this app then owns forever.
            """)
        XCTAssertFalse(ContextPaths.isDevelopmentBuild)
    }

    func testOnlyOurOwnFamilyOfIdentifiersIsAdopted() {
        XCTAssertEqual(ContextPaths.ownIdentifier(reportedBy: shipping), shipping)
        XCTAssertEqual(ContextPaths.ownIdentifier(reportedBy: development), development)
        XCTAssertEqual(
            ContextPaths.ownIdentifier(reportedBy: shipping + ".beta"), shipping + ".beta",
            "any future side-by-side build is ours by the same rule, without a code change here")
    }

    func testEverythingElseFallsBackToTheShippingIdentifier() {
        for reported in [
            nil, "", "com.apple.dt.xctest.tool", "com.omi.computer-macos", "com.anthropic.claudefordesktop",
            // A near miss, and the reason the rule is prefix-*plus-dot* rather than a bare prefix:
            // this is somebody else's identifier that merely starts with ours.
            "com.omi.context-for-claude-test",
            "com.omi.context-for-claudex",
        ] as [String?] {
            XCTAssertEqual(
                ContextPaths.ownIdentifier(reportedBy: reported), shipping,
                "\(reported ?? "nil") is not one of ours and must not become this app's identity")
        }
    }

    func testDevelopmentIsJustBeingSomethingOtherThanWhatShips() {
        XCTAssertFalse(ContextPaths.isDevelopmentBuild(shipping))
        XCTAssertTrue(ContextPaths.isDevelopmentBuild(development))
    }

    // MARK: - The names Claude keys on

    /// The key *is* the registration: whoever writes it owns where Claude spawns the binary from.
    /// A dev build sharing the production key repoints the user's production connector at a locally
    /// signed binary in a build directory, silently, on launch.
    func testADevelopmentBuildRegistersUnderItsOwnConnectorAndSkillName() {
        XCTAssertEqual(ClaudeConfig.serverName(forBundle: development), "context-for-claude-dev")
        XCTAssertEqual(ClaudeSkill.name(forBundle: development), "context-for-claude-dev")

        XCTAssertNotEqual(
            ClaudeConfig.serverName(forBundle: development), ClaudeConfig.serverName(forBundle: shipping))
        XCTAssertNotEqual(
            ClaudeSkill.name(forBundle: development), ClaudeSkill.name(forBundle: shipping))
    }

    /// The other half, and the one that stops this fix from quietly renaming the shipping product:
    /// a release build's names are the strings every existing registration already hangs off.
    func testAProductionBuildsNamesAreExactlyTheStringsThatShip() {
        XCTAssertEqual(ClaudeConfig.serverName(forBundle: shipping), "context-for-claude")
        XCTAssertEqual(ClaudeSkill.name(forBundle: shipping), "context-for-claude")
    }

    // MARK: - Disjointness, over the real document operations

    /// **A development build must leave the installed release's registration exactly as it found
    /// it.** Driven through the same `merged`/`removed` the app calls, over a config that already
    /// holds the production entry — the shape on the machine where this went wrong.
    func testADevelopmentBuildNeitherRewritesNorRemovesTheProductionEntry() throws {
        let installed = "/Applications/Context for Claude.app/Contents/MacOS/context-for-claude-mcp"
        let local = "/Users/dev/build/context-for-claude-mcp"
        let existing: [String: Any] = [
            "mcpServers": [
                "context-for-claude": ["type": "stdio", "command": installed],
                "omi-memory": ["type": "http", "url": "https://example.invalid"],
            ]
        ]

        let merged = ClaudeConfig.merged(
            into: existing, mcpBinaryPath: local, as: ClaudeConfig.serverName(forBundle: development))
        let servers = try object(merged["mcpServers"])

        XCTAssertEqual(
            try object(servers["context-for-claude"])["command"] as? String, installed,
            "the production connector still has to spawn the installed app, not a build directory")
        XCTAssertEqual(try object(servers["context-for-claude-dev"])["command"] as? String, local)
        XCTAssertNotNil(servers["omi-memory"], "every sibling server survives, as always")

        // And disconnecting the dev build takes only the dev build with it.
        let removed = try object(
            ClaudeConfig.removed(from: merged, as: ClaudeConfig.serverName(forBundle: development))["mcpServers"])
        XCTAssertNil(removed["context-for-claude-dev"])
        XCTAssertEqual(try object(removed["context-for-claude"])["command"] as? String, installed)
        XCTAssertNotNil(removed["omi-memory"])
    }

    /// The mirror image: an installed release must not read a dev entry as its own registration and
    /// conclude there is nothing to do.
    func testAProductionBuildDoesNotMistakeTheDevEntryForItsOwn() {
        let local = "/Users/dev/build/context-for-claude-mcp"
        let existing: [String: Any] = [
            "mcpServers": ["context-for-claude-dev": ["type": "stdio", "command": local]]
        ]
        XCTAssertFalse(
            ClaudeConfig.isRegistered(
                in: existing, mcpBinaryPath: local, as: ClaudeConfig.serverName(forBundle: shipping)))
    }

    /// **The managed block in the user's global `~/.claude/CLAUDE.md` is replaced by marker match**,
    /// so two builds sharing markers means a locally built app overwrites the installed release's
    /// block — in the file that steers every Claude session on this Mac. The release markers must
    /// also stay byte-identical to what has shipped, or every block already written by an installed
    /// copy is orphaned and `write` appends a second one.
    func testTheManagedMemoryBlockIsOwnedPerBuild() {
        // Byte-for-byte what shipped. Changing these orphans every block an installed copy wrote,
        // and `write` then appends a second one instead of replacing it.
        XCTAssertEqual(
            ClaudeMemory.beginMarker(forBundle: shipping),
            "<!-- BEGIN Context for Claude — managed block, edits here are overwritten -->")
        XCTAssertEqual(ClaudeMemory.endMarker(forBundle: shipping), "<!-- END Context for Claude -->")

        XCTAssertNotEqual(
            ClaudeMemory.beginMarker(forBundle: development),
            ClaudeMemory.beginMarker(forBundle: shipping),
            "a dev build sharing the release's marker overwrites its block in the user's global memory")
        XCTAssertNotEqual(
            ClaudeMemory.endMarker(forBundle: development),
            ClaudeMemory.endMarker(forBundle: shipping))
    }

    /// The block tells Claude which MCP server to call, so it has to name the one this build
    /// actually registered — otherwise a dev build instructs the model to call a server that is not
    /// there, and every tool it advertises goes unused.
    func testTheManagedBlockNamesTheServerThisBuildRegisters() {
        let releaseText = ClaudeMemory.instruction(
            forServer: ClaudeConfig.serverName(forBundle: shipping))
        let devText = ClaudeMemory.instruction(
            forServer: ClaudeConfig.serverName(forBundle: development))

        XCTAssertTrue(releaseText.contains("`context-for-claude` MCP server"))
        XCTAssertTrue(devText.contains("`context-for-claude-dev` MCP server"))
        XCTAssertFalse(
            devText.contains("`context-for-claude` MCP server"),
            "a dev build must not point Claude at the release's server name")
    }

    private func object(_ value: Any?) throws -> [String: Any] {
        try XCTUnwrap(value as? [String: Any])
    }
}
