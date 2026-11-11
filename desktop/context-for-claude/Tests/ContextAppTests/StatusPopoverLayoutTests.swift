import AppKit
import SwiftUI
import XCTest

@testable import ContextApp

/// **The popover's height has to be a function of what is in it.**
///
/// The bug: the panel was pinned at `320 × 380` while its content measures 384 pt in the plainest
/// state and past 470 pt in the reported one — signed in, both Claude surfaces connected, an upload
/// error underneath. SwiftUI answers an under-proposed `VStack` by shrinking the children that can
/// shrink, and every line in the connection/account block is `.fixedSize(horizontal: false,
/// vertical: true)` precisely so that it will not, so the block's lines were laid out on top of one
/// another: `Connected to Claude Code and Claude Desktop` wrapping to two lines, `Syncing to
/// …@gmail.com` drawn through it, and `HTTP 503` through both. Nothing clipped and nothing logged —
/// the block simply drew three sentences into the room for one row, and it had to be reported from a
/// screenshot.
///
/// What is asserted is the contract that makes that unrepeatable rather than the 380 that broke it:
/// the panel tracks its content's own size, and nothing pins a box smaller than the content asked
/// for. The states are covered separately, as composition, because neither of the two things that
/// drive them can be arranged hermetically — `OmiAuth`'s flags are `private(set)` behind a browser
/// round trip, and `ClaudeRegistrar` reads two config files this process does not own — which is why
/// both lines are values (`ClaudeConnectorLine`, `AccountPresentation`) that can be.
final class StatusPopoverLayoutTests: XCTestCase {

    // MARK: - The panel

    /// **The regression.** `.preferredContentSize` is the size `NSPopover` reads, and the only sizing
    /// option that also grows the panel *while it is open* — which is exactly when the error line
    /// arrives, since `ConversationUploader` publishes into a popover the user is already looking at.
    /// Measured live, the shipped default (`.standardBounds`, which publishes no preferred size at
    /// all) drew 384 pt of content in a 320 pt panel.
    @MainActor
    func testThePopoverTracksItsContentAndPinsNoBoxSmallerThanItAsksFor() throws {
        let popover = StatusItemController.makePopover()
        let content = try XCTUnwrap(popover.contentViewController as? NSHostingController<StatusView>)
        content.view.layoutSubtreeIfNeeded()

        XCTAssertTrue(
            content.sizingOptions.contains(.preferredContentSize),
            "the popover's content publishes no preferred size, so the panel cannot follow it")

        let asked = content.preferredContentSize
        XCTAssertGreaterThan(asked.height, 0, "the content asks for no height at all")

        // An unset `contentSize` is the fix: the panel asks its content. A pin is not forbidden, but
        // it has to clear what the content asked for — under that, the block is proposed less height
        // than its own lines need, and the lines that cannot shrink overlap.
        if popover.contentSize.height > 0 {
            XCTAssertGreaterThanOrEqual(
                popover.contentSize.height, asked.height,
                "the popover reserves \(popover.contentSize.height) pt for \(asked.height) pt of content"
            )
        }
        if popover.contentSize.width > 0 {
            XCTAssertGreaterThanOrEqual(popover.contentSize.width, asked.width)
        }
    }

    // MARK: - The states

    /// The connection/account block as the ordered lines the popover draws, out of the same two values
    /// `StatusView` draws them from.
    private func block(
        claudeCode: Bool = false,
        claudeDesktop: Bool = false,
        liveness: ClaudeServerLiveness.State = .unknown,
        connectorNote: String? = nil,
        signedIn: Bool = false,
        email: String? = nil,
        uploadNote: String? = nil,
        uploadFailed: Bool = false
    ) -> [String] {
        let connector = ClaudeConnectorLine(
            connection: ClaudeConnection(
                claudeCode: claudeCode, claudeDesktop: claudeDesktop, liveness: liveness),
            note: connectorNote,
            isConnecting: false)
        let account = AccountPresentation(
            signedIn: signedIn,
            signingIn: false,
            email: email,
            offeringProviders: false,
            signInError: nil,
            uploadNote: uploadNote,
            uploadFailed: uploadFailed)
        return [connector.summary, connector.note, account.summary, account.note].compactMap { $0 }
    }

    /// **The reported state, line by line.** Three sentences, all present, none of them the same entry
    /// as another — which is what the panel has to make room for three of.
    func testTheReportedStateIsThreeDistinctLines() {
        XCTAssertEqual(
            block(
                claudeCode: true,
                claudeDesktop: true,
                signedIn: true,
                email: "david.d.zhang@gmail.com",
                uploadNote: "HTTP 503",
                uploadFailed: true),
            [
                "Connected to Claude Code and Claude Desktop",
                "Syncing to david.d.zhang@gmail.com",
                "HTTP 503",
            ])
    }

    /// Every state the block can be in: zero, one or both surfaces connected, signed in or out, with
    /// and without a line underneath — including a long error, and an email long enough to wrap. No
    /// state may lose a line or repeat one, because each is a separate entry the block has to stack.
    func testEveryStateKeepsItsLinesAsDistinctNonEmptyEntries() {
        let notes: [String?] = [
            nil,
            "HTTP 503",
            "The last upload failed with HTTP 503 — the service is unavailable, so nothing has "
                + "reached your Omi account since.",
        ]
        let emails = ["a@b.co", "david.d.zhang.a.very.long.address@some-long-domain.example.com"]

        // Liveness is in the sweep because `.notServingClaudeDesktop` adds a *fourth* line to the
        // block — the restart notice — in the state that also carries the longest summary. That is
        // the tallest the connection half can get, and it is the one the panel has to be sized by.
        let livenesses: [ClaudeServerLiveness.State] = [
            .unknown, .servingClaudeDesktop, .notServingClaudeDesktop,
        ]

        for claudeCode in [false, true] {
            for claudeDesktop in [false, true] {
                for liveness in livenesses {
                for signedIn in [false, true] {
                    for note in notes {
                        for email in emails {
                            let lines = block(
                                claudeCode: claudeCode,
                                claudeDesktop: claudeDesktop,
                                liveness: liveness,
                                signedIn: signedIn,
                                email: email,
                                uploadNote: note,
                                uploadFailed: note != nil)
                            let state =
                                "code=\(claudeCode) desktop=\(claudeDesktop) live=\(liveness) "
                                + "signedIn=\(signedIn) note=\(note ?? "nil")"

                            XCTAssertGreaterThanOrEqual(lines.count, 2, state)
                            for line in lines {
                                XCTAssertFalse(line.isEmpty, state)
                            }
                            XCTAssertEqual(
                                Set(lines).count, lines.count,
                                "two lines of the block are the same entry — \(state)")
                        }
                    }
                }
                }
            }
        }
    }

    /// **Why the block cannot be given one row per line.** The sentence naming both surfaces does not
    /// fit the popover's text column at the size every line on that surface is set in, so the reported
    /// state is three entries laid out as four lines. A container that reserves a row each has already
    /// lost, whatever its row height is.
    func testTheSentenceNamingBothSurfacesNeedsMoreThanOneRow() {
        let both = ClaudeConnectorLine(
            connection: ClaudeConnection(claudeCode: true, claudeDesktop: true, liveness: .unknown),
            note: nil,
            isConnecting: false)

        XCTAssertGreaterThan(
            Self.height(of: both.summary), InkPermissionRow.menuRowHeight,
            "\"\(both.summary)\" fits one row, so this no longer measures the state that overlapped")

        // …and it is the tall one, so it is the state the panel has to be sized by.
        for shorter in [
            ClaudeConnectorLine(
                connection: ClaudeConnection(
                    claudeCode: true, claudeDesktop: false, liveness: .unknown),
                note: nil,
                isConnecting: false),
            ClaudeConnectorLine(
                connection: ClaudeConnection(
                    claudeCode: false, claudeDesktop: false, liveness: .unknown),
                note: nil,
                isConnecting: false),
        ] {
            XCTAssertGreaterThan(Self.height(of: both.summary), Self.height(of: shorter.summary))
        }
    }

    /// The width one line of the block gets: the panel, less its own horizontal padding, less the
    /// checkmark column every line is inset onto, less the trailing gutter.
    private static var textColumn: CGFloat {
        StatusView.popoverWidth - 12 * 2 - StatusView.rowTextInset - 4
    }

    /// Laid out at that width in the font the surface uses — a menu item's own size, which is what
    /// `StatusView` sets every line in.
    private static func height(of line: String) -> CGFloat {
        NSAttributedString(
            string: line,
            attributes: [.font: NSFont.systemFont(ofSize: NSFont.systemFontSize)]
        ).boundingRect(
            with: NSSize(width: textColumn, height: .greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin, .usesFontLeading]
        ).height
    }
}
