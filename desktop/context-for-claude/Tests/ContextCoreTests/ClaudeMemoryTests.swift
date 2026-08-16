import XCTest

@testable import ContextCore

/// The standing instruction this app writes into the user's **global** `~/.claude/CLAUDE.md`.
///
/// Every test here is about the same property: that file is loaded into every prompt the user ever
/// runs, and it may already carry hundreds of lines they wrote themselves. So the merge is asserted
/// as a pure function over a string — nothing here touches a home directory — and what is asserted is
/// mostly what the merge *does not* do.
final class ClaudeMemoryTests: XCTestCase {

    // MARK: - Writing into somebody else's file

    /// A file with the user's own instructions in it keeps every one of them.
    func testTheUsersOwnInstructionsSurviveTheMerge() {
        let mine = """
            # My rules

            - Always run the tests before saying you are done.
            - Never push to main.
            """

        let merged = ClaudeMemory.merged(into: mine)

        XCTAssertTrue(merged.hasPrefix(mine), "the user's file must not be rewritten around our block")
        XCTAssertTrue(merged.contains("Always run the tests before saying you are done."))
        XCTAssertTrue(merged.contains("Never push to main."))
        XCTAssertTrue(ClaudeMemory.isInstalled(in: merged))
    }

    /// **Connecting twice must not write the block twice**, which is the failure that costs the user
    /// tokens on every request forever rather than once.
    func testMergingTwiceLeavesExactlyOneBlock() {
        let once = ClaudeMemory.merged(into: "# My rules\n")
        let twice = ClaudeMemory.merged(into: once)

        XCTAssertEqual(once, twice, "a second merge changed a file that was already correct")
        XCTAssertEqual(occurrences(of: ClaudeMemory.beginMarker, in: twice), 1)
        XCTAssertEqual(occurrences(of: ClaudeMemory.endMarker, in: twice), 1)
    }

    /// An older build's block is replaced in place rather than appended to, so an update does not
    /// leave the user carrying two versions of the same instruction that disagree.
    func testAStaleBlockIsReplacedRatherThanAppended() {
        let stale = """
            # My rules

            \(ClaudeMemory.beginMarker)

            ## Context for Claude (this Mac)

            Some older wording that named tools this build no longer ships.

            \(ClaudeMemory.endMarker)

            - And a rule I wrote after it.
            """
        XCTAssertFalse(ClaudeMemory.isInstalled(in: stale))

        let merged = ClaudeMemory.merged(into: stale)

        XCTAssertTrue(ClaudeMemory.isInstalled(in: merged))
        XCTAssertFalse(merged.contains("Some older wording"))
        XCTAssertTrue(
            merged.contains("- And a rule I wrote after it."),
            "replacing our block must not take what follows it with it")
        XCTAssertEqual(occurrences(of: ClaudeMemory.beginMarker, in: merged), 1)
    }

    /// An empty or missing file gets the block and nothing else — no stray blank lines, no heading
    /// we invented for a file the user has never opened.
    func testAnEmptyFileGetsJustTheBlock() {
        XCTAssertEqual(ClaudeMemory.merged(into: ""), ClaudeMemory.block + "\n")
        XCTAssertEqual(ClaudeMemory.merged(into: "\n\n  \n"), ClaudeMemory.block + "\n")
    }

    /// **A half-finished hand edit must not cost the user the rest of their file.**
    ///
    /// An opening marker with no close is what a partial edit or a bad merge leaves behind. Slicing
    /// from that marker to the end of the file — the obvious implementation — would delete every
    /// instruction they wrote after it. Doing nothing to the damaged region and appending a fresh
    /// block is the recoverable direction: they end up with a stray line to delete rather than with
    /// their standing instructions gone.
    func testAnUnclosedMarkerIsNotTreatedAsABlock() {
        let damaged = """
            \(ClaudeMemory.beginMarker)

            half of an old block

            - A rule I wrote, after the damage.
            """

        let merged = ClaudeMemory.merged(into: damaged)

        XCTAssertTrue(merged.contains("- A rule I wrote, after the damage."))
        XCTAssertTrue(merged.contains("half of an old block"))
        XCTAssertTrue(merged.hasSuffix(ClaudeMemory.block + "\n"))
    }

    // MARK: - Taking it back out

    /// Disconnecting removes our paragraph and leaves theirs.
    func testStrippingLeavesTheUsersFileBehind() {
        let mine = "# My rules\n\n- Never push to main."
        let merged = ClaudeMemory.merged(into: mine)

        let stripped = ClaudeMemory.stripped(from: merged)

        XCTAssertFalse(ClaudeMemory.isInstalled(in: stripped))
        XCTAssertFalse(stripped.contains(ClaudeMemory.beginMarker))
        XCTAssertTrue(stripped.contains("- Never push to main."))
    }

    /// …and a file that was only ever our block comes back empty, which is what lets `remove()`
    /// delete a `CLAUDE.md` this app created rather than leaving an empty file behind.
    func testStrippingOurOwnFileLeavesNothing() {
        XCTAssertEqual(ClaudeMemory.stripped(from: ClaudeMemory.merged(into: "")), "")
    }

    /// Stripping a file that never had a block is a no-op, byte for byte.
    func testStrippingAFileWithoutABlockChangesNothing() {
        let mine = "# My rules\n\n- Never push to main.\n"
        XCTAssertEqual(ClaudeMemory.stripped(from: mine), mine)
    }

    // MARK: - What it says

    /// The instruction is only worth writing if it states the rule the product needs: look *before*
    /// answering, and never claim to be blind. Both phrasings have been the difference between
    /// Claude calling a tool and Claude asking the user to paste something they already said.
    func testTheInstructionTellsClaudeToLookFirstAndNeverClaimItCannot() {
        let text = ClaudeMemory.instruction

        XCTAssertTrue(text.contains("`recent`"), "the tool for an unbound \"this\" has to be named")
        XCTAssertTrue(text.contains("`recall`"), "and the one for a name it does not know")
        XCTAssertTrue(text.contains("`status`"), "and the one to call before claiming nothing exists")
        XCTAssertTrue(
            text.localizedCaseInsensitiveContains("before you answer"),
            "the rule is about when to look, and 'before' is the whole of it")
        XCTAssertTrue(
            text.localizedCaseInsensitiveContains("never tell this user you lack context"),
            "the observed failure is a confident refusal, so the refusal is what has to be forbidden")
    }

    /// The markers are comments, so the block is invisible in any Markdown renderer — and they are
    /// not a heading, because a heading called "Context for Claude" is something a user might
    /// plausibly type themselves, and we must never rewrite a section they wrote.
    func testTheMarkersAreInvisibleCommentsAndSayTheyAreManaged() {
        XCTAssertTrue(ClaudeMemory.beginMarker.hasPrefix("<!--"))
        XCTAssertTrue(ClaudeMemory.endMarker.hasSuffix("-->"))
        XCTAssertTrue(
            ClaudeMemory.beginMarker.localizedCaseInsensitiveContains("overwritten"),
            "anyone editing inside the block has to be told it will not survive")
    }

    private func occurrences(of needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }
}
