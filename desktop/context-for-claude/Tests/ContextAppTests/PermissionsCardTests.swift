import AppKit
import SwiftUI
import XCTest

@testable import ContextApp

// MARK: - The permissions card fits the card it is drawn on

/// **The truncation regression, stated as a measurement.**
///
/// What shipped: the permissions card is drawn on a fixed pane, and its tallest state at the time —
/// the by-hand grant, where a replica of the System Settings row was added under the four permission
/// rows — asked for more height than the pane had. That panel has since been deleted (the overlay it
/// offered now appears by itself), but the *mechanism* is unchanged and is what these measure: a
/// fixed pane, content that can grow, and no warning when the two disagree. Nothing overflowed and
/// nothing warned. SwiftUI paid for the
/// shortfall by offering the four rows less height than they needed, and a `Text` given less height
/// than it needs ends in an ellipsis: three of the four first-person sentences were cut off
/// mid-word on screen ("…so I can hear what you talk…", "…so I know what you're working…", "…so I
/// quote it exactly i…"). The card looked deliberate. It was eating its own copy.
///
/// Two things make that impossible now, and both are asserted here.
///
/// 1. `InkPermissionRow`'s sentence is `.fixedSize` vertically, so a row can only ever grow. A row
///    that cannot be compressed cannot be truncated.
/// 2. Because of (1), the card's *ideal* height is the height it genuinely needs — so measuring it
///    against the pane's budget is a real answer to "does the copy fit", in every state.
///
/// Measured through `NSHostingView.fittingSize` on the real `PermissionsCard`, at the real column
/// width, with the real copy. Asserting that `.fixedSize` appears in the source would be a static
/// tripwire; this runs the layout.
final class PermissionsCardLayoutTests: XCTestCase {

    /// The bundled faces have to be registered or every measurement below is of SF Pro standing in
    /// for Open Runde, at a different line height.
    private static var fonts: Bool { InkTestFonts.registered }

    override func setUp() {
        super.setUp()
        _ = Self.fonts
    }

    /// The width the permissions column really gets: the list measure, or what the page padding
    /// leaves of the pane, whichever is smaller. Same expression as `OnboardingView.columnWidth`.
    @MainActor
    private var column: CGFloat {
        min(
            InkLayout.permissionsMaxWidth,
            OnboardingWindow.cardSize.width - 2 * InkLayout.pagePaddingHorizontal)
    }

    // MARK: The states

    /// Every state the permissions card reaches, named the way the flow reaches them.
    ///
    /// The preambles are copied from `PermissionGate.caption` and `OnboardingView.setupPreamble`
    /// rather than read from them: the gate's phase is `private(set)` and parking one in
    /// `.waitingInSettings` from here would mean adding a production seam for a measurement. The
    /// copy is the part at risk, so the two longest captions — the opening, and the wait on the
    /// screen row — are reproduced verbatim; a card that fits these fits the shorter ones.
    @MainActor
    private func states() -> [(String, PermissionsCard)] {
        let all = Capability.allCases
        func rows(granted: Set<Capability>, status: (Capability) -> String) -> [PermissionsCardRow] {
            all.map {
                PermissionsCardRow(capability: $0, granted: granted.contains($0), status: status($0))
            }
        }
        func card(
            _ title: String, _ preamble: String, granted: Set<Capability> = [],
            status: @escaping (Capability) -> String = { _ in "Allow" },
            postponing: Capability? = nil, canContinue: Bool = false
        ) -> PermissionsCard {
            PermissionsCard(
                title: title, preamble: preamble, rows: rows(granted: granted, status: status),
                postponing: postponing, canContinue: canContinue,
                // Far enough in the past that the phrase has been said, so this measures the
                // finished headline rather than however much of it a given frame had revealed.
                phraseStart: Date().addingTimeInterval(-5))
        }
        let granted: (Capability) -> String = { _ in "Granted" }

        // The longest preamble on the card: the one shown before anything has been asked, which is
        // also the card's resting state now that nothing is asked for until a row is clicked.
        // It used to be the *longest* preamble here — three sentences explaining that macOS asks
        // separately, that we take them one at a time, and that Accessibility has no dialog. One
        // sentence now ("don't explain so much"), so the tallest state on this card is a gate caption
        // rather than the opening; the measurements below cover both either way.
        let opening = "Click one when you’re ready. Nothing is asked until you do."
        // `PermissionGate.caption`, in the phases the card draws a panel for.
        let explaining = "One at a time. I’ll ask, and I’ll wait for your answer before the next one."
        let prompting = "macOS is asking. I’ll wait."
        let confirming = "Got it."
        func waiting(_ detail: String) -> String {
            """
            System Settings is open on the right row. Switch it on and I’ll notice — I won’t \
            move on without an answer. If now is not the time, tell me and I’ll ask again \
            later. \(detail)
            """
        }

        return [
            // **The state the card now rests in**: everything readable, nothing in flight, and the
            // only way forward is a button. This is the tallest of the four-row states and the one
            // the click-to-ask change made load-bearing — the old opening was on screen for as long
            // as it took a timer to reach the first dialog.
            ("nothing granted", card("First…", opening)),
            (
                "nothing granted, already signed in",
                card("Now the permissions.", opening)
            ),
            (
                "explaining the microphone",
                card("Say yes.", explaining, status: { _ in "Asking…" })
            ),
            ("a dialog is up", card("Say yes.", prompting)),
            (
                "one granted",
                card(
                    "Say yes.", confirming, granted: [.microphone],
                    status: { $0 == .microphone ? "Granted" : "Allow" })
            ),
            // The escape panel, on the longest of the four waiting captions.
            (
                "waiting in settings for the screen",
                card(
                    "Say yes.",
                    waiting("It’s under Privacy & Security ▸ Screen & System Audio Recording."),
                    granted: [.microphone, .systemAudio],
                    status: { [.microphone, .systemAudio].contains($0) ? "Granted" : "Asking…" },
                    postponing: .screen)
            ),
            (
                "waiting in settings for the microphone",
                card(
                    "Say yes.", waiting("It’s under Privacy & Security ▸ Microphone."),
                    postponing: .microphone)
            ),
            (
                "deferred",
                card(
                    "Now the permissions.", opening, granted: [.microphone, .systemAudio],
                    status: {
                        [.microphone, .systemAudio].contains($0) ? "Granted" : "Later"
                    },
                    canContinue: true)
            ),
            // The three required grants are in and the fourth — the one macOS never prompts for — is
            // still there to be clicked. The card holds until Continue is pressed, which is the whole
            // reason this state exists at all: it used to leave by itself the instant the third grant
            // landed, taking the fourth row with it.
            (
                "required in, window text still open",
                card(
                    "Now the permissions.", opening,
                    granted: [.microphone, .systemAudio, .screen],
                    status: { $0 == .accessibility ? "Allow" : "Granted" }, canContinue: true)
            ),
            (
                "everything granted",
                card(
                    "Now the permissions.", opening, granted: Set(all), status: granted,
                    canContinue: true)
            ),
            (
                "the screen needs a relaunch",
                card(
                    "Now the permissions.", opening,
                    granted: [.microphone, .systemAudio, .screen],
                    status: { $0 == .screen ? "Action required" : ($0 == .accessibility ? "Allow" : "Granted") },
                    canContinue: true)
            ),
        ]
    }

    // MARK: The assertions

    /// **Every state fits, with the dots' band already taken out of the budget.**
    ///
    /// This is the test the defect needed, and the one that keeps the copy honest: every sentence
    /// on this card is one somebody may rewrite, and a rewrite that costs a line is invisible until
    /// it costs four. `testTheFitMeasurementReportsAnOverflow` is what proves it can still fail.
    @MainActor
    func testEveryPermissionsStateFitsTheCard() {
        XCTAssertTrue(Self.fonts, "no font files found next to the package")
        let budget = OnboardingWindow.cardContentHeight

        for (name, card) in states() {
            let needed = height(of: card)
            XCTAssertGreaterThan(needed, 0, "\(name) drew nothing")
            XCTAssertLessThanOrEqual(
                needed, budget,
                "the permissions card in the \"\(name)\" state needs \(Int(needed.rounded())) pt and "
                    + "the pane leaves \(Int(budget.rounded())) pt — SwiftUI will pay the difference "
                    + "by compressing the rows, which truncates their sentences mid-word")
        }
    }

    /// …and the measurement is still of the real card.
    ///
    /// **The old form of this test was a ratio against the budget** — the tallest state had to be
    /// within 25% of the pane — and it had to change, because what made the card tall changed by
    /// design. The tallest state used to be the by-hand grant: four rows *plus* a 125 pt panel
    /// holding an animated replica of a System Settings row and a "Show me the row" button. That
    /// panel is gone; the overlay it asked permission to draw now appears on its own when the pane
    /// opens. Keeping the ratio would have been asserting that a deleted panel is still there.
    ///
    /// So the claim is restated relative to the card's own parts rather than to the pane, which is
    /// what makes it survive the pane being resized again: the full card has to be substantially
    /// taller than the same card stripped to a headline and one row. A measurement that had stopped
    /// seeing the rows, the preamble or the footer could not clear this.
    @MainActor
    func testTheMeasurementIsStillOfTheWholeCard() {
        let stripped = PermissionsCard(
            title: "First…", preamble: "Short.",
            rows: [PermissionsCardRow(capability: .microphone, granted: false, status: "Allow")],
            phraseStart: Date().addingTimeInterval(-5))
        let tallest = states().map { height(of: $0.1) }.max() ?? 0
        // Three rows fewer, at the 40 pt a single-line row cannot go under — the checkbox plus its
        // padding — so the margin is the arithmetic of the rows themselves rather than a number
        // somebody measured once and would have to re-measure after every copy change.
        let floor = height(of: stripped) + 3 * 40
        XCTAssertGreaterThan(
            tallest, floor,
            "the tallest permissions state measures \(Int(tallest.rounded())) pt against "
                + "\(Int(height(of: stripped).rounded())) pt for a headline and one row — three more "
                + "rows cannot account for less than 120 pt, so this has stopped measuring the card")
    }

    /// **The measurement can fail.**
    ///
    /// Without this, the fit test above would pass just as happily on a measurement structurally
    /// incapable of reporting an overflow. It used to be proved by re-measuring the state that
    /// shipped broken against the 520 pt pane it truncated on; that state no longer exists, so the
    /// overflow is provoked directly instead — a preamble nobody would write, on the real card, in
    /// the real column.
    @MainActor
    func testTheFitMeasurementReportsAnOverflow() {
        let budget = OnboardingWindow.cardContentHeight
        let flooded = PermissionsCard(
            title: "First…",
            preamble: String(
                repeating: "A preamble long enough that this card cannot possibly fit the pane. ",
                count: 12),
            rows: Capability.allCases.map {
                PermissionsCardRow(capability: $0, granted: false, status: "Allow")
            },
            phraseStart: Date().addingTimeInterval(-5))
        XCTAssertGreaterThan(
            height(of: flooded), budget,
            "a card with twelve times too much copy measured as fitting — the fit test is not "
                + "capable of reporting an overflow and therefore is not watching anything")
    }

    /// **A row wraps rather than truncating.** The other half of the fix, asserted on the row itself
    /// so it cannot be undone by a `.lineLimit` three lines away.
    ///
    /// A long sentence must make the row *taller*. The failing behaviour is the opposite: the row
    /// keeps one line's height and the sentence loses its end.
    @MainActor
    func testALongSentenceMakesTheRowTallerRatherThanCuttingIt() {
        XCTAssertTrue(Self.fonts, "no font files found next to the package")
        func rowHeight(_ title: String) -> CGFloat {
            let host = NSHostingView(
                rootView: InkPermissionRow(title: title, granted: false, status: "Open") {}
                    .frame(width: column))
            host.layoutSubtreeIfNeeded()
            return host.fittingSize.height
        }

        let short = rowHeight("Short.")
        // The longest sentence the card actually says.
        let real = rowHeight(Capability.accessibility.title)
        let absurd = rowHeight(String(repeating: "a sentence that has to wrap several times over ", count: 4))

        XCTAssertGreaterThan(
            absurd, short * 2,
            "a sentence four times too long for the row left the row \(absurd) pt tall against a "
                + "one-line \(short) pt — it is being truncated, not wrapped")
        XCTAssertGreaterThanOrEqual(
            real, short,
            "the real accessibility sentence must never measure shorter than one line")
    }

    /// The card is drawn at its ideal height, so `fittingSize` is what the pane is being asked for.
    @MainActor
    private func height(of card: PermissionsCard) -> CGFloat {
        let host = NSHostingView(rootView: card.frame(width: column))
        host.layoutSubtreeIfNeeded()
        return host.fittingSize.height
    }
}

// MARK: - The dots have a band of their own

/// **The collision regression.** The progress dots were an `.overlay(alignment: .bottom)` pinned 62
/// pt off the pane's foot — a position, not a reservation — so on the permissions card they landed
/// inside the fourth permission row, over the consequence line beside "I'll do this later", and on
/// top of the "Show me the row" button, where a lit `Ink.primary` dot on a near-black pill is
/// invisible.
///
/// The fix is arithmetic: the band is subtracted from the height the column is offered. These are
/// the two facts that makes it hold.
@MainActor
final class OnboardingProgressBandTests: XCTestCase {

    /// The band is real height, not a padding value: the content budget is the pane less the page
    /// margins **and** the band.
    func testTheDotsBandIsTakenOutOfTheContentBudget() {
        XCTAssertGreaterThan(InkLayout.progressBandHeight, 0)
        XCTAssertEqual(
            OnboardingWindow.cardContentHeight,
            OnboardingWindow.cardSize.height - 2 * InkLayout.pagePaddingVertical
                - InkLayout.progressBandHeight,
            accuracy: 0.001)
    }

    /// The band clears a 5 pt row of dots with air either side — a band the dots do not fit in is
    /// the same defect one layer down.
    func testTheBandHoldsTheDotsItReserves() {
        let dot: CGFloat = 5
        XCTAssertGreaterThan(
            InkLayout.progressBandHeight, dot * 2,
            "the reserved band has to be visibly more than the dots themselves or they sit on the rim")
    }
}
