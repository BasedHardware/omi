import Foundation
import XCTest

@testable import ContextCore

/// The Claude Code skill: the one artefact that reaches a subagent, which is the reader with the
/// least context and the least reason to think of asking for more.
///
/// The document's *prose* is not asserted word for word — pinning it would make every edit a test
/// failure. What is asserted is the shape a client actually parses (frontmatter, name, description)
/// and the install being a well-behaved guest in a directory this app does not own.
final class ClaudeSkillTests: XCTestCase {

    // MARK: - The document a client has to parse

    /// Claude reads the frontmatter to decide whether the skill is worth opening. A document whose
    /// frontmatter does not parse is not a weaker skill — it is an unlisted one.
    func testTheDocumentOpensWithFrontmatterCarryingNameAndDescription() throws {
        let lines = ClaudeSkill.document.components(separatedBy: "\n")

        XCTAssertEqual(lines.first, "---", "the document must open with frontmatter")
        let close = try XCTUnwrap(lines.dropFirst().firstIndex(of: "---"), "frontmatter is never closed")
        let frontmatter = lines[1..<close].joined(separator: "\n")

        XCTAssertTrue(frontmatter.contains("name: \(ClaudeSkill.name)"), frontmatter)
        XCTAssertTrue(frontmatter.contains("description:"), frontmatter)
    }

    /// The directory name is what Claude lists the skill under, and the frontmatter `name` is what
    /// it is invoked by. The two disagreeing is a skill that appears under one name and answers to
    /// another — the same failure `ClaudeConfig.serverName` guards on the connector side.
    func testTheDirectoryAndTheDeclaredNameAgree() {
        XCTAssertEqual(ClaudeSkill.directoryURL.lastPathComponent, ClaudeSkill.name)
        XCTAssertTrue(ClaudeSkill.document.contains("name: \(ClaudeSkill.name)"))
    }

    /// The description is read *instead of* the body when an agent is deciding whether this is
    /// relevant, so it has to name the situations rather than summarise the contents. Asserted
    /// through the triggers that matter most and are easiest to lose in an edit: the visual case,
    /// and subagents.
    func testTheDescriptionNamesTheSituationsThatShouldTriggerIt() throws {
        let description = try XCTUnwrap(
            ClaudeSkill.document.range(of: "description:").map {
                String(ClaudeSkill.document[$0.upperBound...].prefix(700)).lowercased()
            })

        XCTAssertTrue(description.contains("screen"), description)
        XCTAssertTrue(description.contains("subagent"), description)
    }

    /// Every tool the server advertises should be findable in the skill: one that lists a subset
    /// teaches an agent that the rest do not exist.
    func testEveryToolTheServerShipsIsNamedInTheSkill() {
        let shipped = [
            "recall", "recent", "look", "screen", "conversations", "transcript", "activity",
            "status", "get_memories", "create_memory", "edit_memory", "delete_memory",
        ]
        for tool in shipped {
            XCTAssertTrue(
                ClaudeSkill.document.contains("`\(tool)`"),
                "the skill never mentions `\(tool)`, so an agent reading it will not know it exists")
        }
    }

    // MARK: - Installing into a directory this app does not own

    func testInstallWritesTheSkillAndSaysWhetherItChangedAnything() throws {
        try inTemporaryHome {
            XCTAssertTrue(try ClaudeSkill.install(), "the first install wrote nothing")
            XCTAssertEqual(
                try String(contentsOf: ClaudeSkill.documentURL, encoding: .utf8), ClaudeSkill.document)
            XCTAssertTrue(ClaudeSkill.isInstalled)

            // Connecting twice is routine — the app registers on every launch — and rewriting an
            // identical file would churn the modification date that says when the skill last
            // changed.
            XCTAssertFalse(try ClaudeSkill.install(), "an unchanged document was rewritten")
        }
    }

    /// A skill left over from an older build describes tools that may no longer exist, and
    /// reporting it as installed is exactly what would make it permanent.
    func testAStaleDocumentIsNotReportedAsInstalledAndIsReplaced() throws {
        try inTemporaryHome {
            try FileManager.default.createDirectory(
                at: ClaudeSkill.directoryURL, withIntermediateDirectories: true)
            try "---\nname: context-for-claude\n---\nolder".write(
                to: ClaudeSkill.documentURL, atomically: true, encoding: .utf8)

            XCTAssertFalse(ClaudeSkill.isInstalled, "a stale document read as current")
            XCTAssertTrue(try ClaudeSkill.install())
            XCTAssertTrue(ClaudeSkill.isInstalled)
        }
    }

    func testRemoveTakesTheWholeDirectoryAndIsSafeToRepeat() throws {
        try inTemporaryHome {
            try ClaudeSkill.install()

            XCTAssertTrue(try ClaudeSkill.remove())
            XCTAssertFalse(FileManager.default.fileExists(atPath: ClaudeSkill.directoryURL.path),
                           "an empty folder left in the user's skills list reads as a broken skill")
            // Disconnecting when nothing is connected is a no-op, not an error.
            XCTAssertFalse(try ClaudeSkill.remove())
        }
    }

    /// Installing must never disturb anything else under `~/.claude/skills` — this app is a guest
    /// in a directory whose other contents belong to the user.
    func testInstallLeavesTheUsersOtherSkillsAlone() throws {
        try inTemporaryHome { home in
            let theirs = home.appendingPathComponent(".claude/skills/their-skill", isDirectory: true)
            try FileManager.default.createDirectory(at: theirs, withIntermediateDirectories: true)
            let theirDocument = theirs.appendingPathComponent("SKILL.md")
            try "theirs".write(to: theirDocument, atomically: true, encoding: .utf8)

            try ClaudeSkill.install()
            try ClaudeSkill.remove()

            XCTAssertEqual(try String(contentsOf: theirDocument, encoding: .utf8), "theirs")
        }
    }

    // MARK: - Harness

    /// Runs `body` with `$HOME` pointed at a fresh directory.
    ///
    /// `FileManager.homeDirectoryForCurrentUser` reads `HOME`, so this is what keeps a test that
    /// writes into `~/.claude` from writing into the developer's real one — the same directory the
    /// installed app is using while these tests run.
    private func inTemporaryHome(_ body: (URL) throws -> Void) throws {
        let home = FileManager.default.temporaryDirectory
            .appendingPathComponent("claude-skill-home-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
        let original = ProcessInfo.processInfo.environment["HOME"]
        setenv("HOME", home.path, 1)
        defer {
            if let original { setenv("HOME", original, 1) } else { unsetenv("HOME") }
            try? FileManager.default.removeItem(at: home)
        }
        try body(home)
    }

    private func inTemporaryHome(_ body: () throws -> Void) throws {
        try inTemporaryHome { _ in try body() }
    }
}
