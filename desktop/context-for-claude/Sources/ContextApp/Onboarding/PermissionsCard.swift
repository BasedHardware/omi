import SwiftUI

// MARK: - One row's worth of state

/// A capability as the card draws it: the sentence, the checkbox and the status word.
///
/// A value rather than four parallel lookups inside the view, because "what does this card put on
/// screen" is the thing the layout has to be measured against, and a computed property reading
/// `@State` on a `View` cannot be handed to a measurement.
struct PermissionsCardRow: Equatable {
    var capability: Capability
    var granted: Bool
    /// One word — `Granted` / `Allow` / `Open Settings` / `Asking…` / `Later` / `Action required`.
    ///
    /// It is an **imperative** on every row that still has something to do, and that is the whole
    /// point of it now. Nothing on this card fires by itself, so the status column is the row's only
    /// affordance: "Open" described a state nobody was being asked to change, and a card of four
    /// described states with no visible verb is a card people sit and wait on.
    var status: String

    var title: String { capability.title }
}

// MARK: - The card

/// The permissions step's column: what is about to happen, the four rows, and whichever of the two
/// footers the run has reached.
///
/// Split out of `OnboardingView` because **this is the card whose height varies**. Every other step
/// is a headline, a sentence and a button; this one grows a 42 pt escape panel while a gate waits in
/// System Settings, on top of a preamble that changes length with the phase and four sentences that
/// wrap or do not. The card is a fixed size, so "does the tallest state still fit" is a real question
/// with a wrong answer available — and a `private var` on a `View` is not something a test can
/// measure.
///
/// It takes values and closures and owns no state, so `NSHostingView(rootView:).fittingSize` on it
/// is exactly the height the real card demands. `PermissionsCardTests` measures every state this
/// way against `contentHeight`.
struct PermissionsCard: View {
    /// The headline. Changes under the user as the run moves ("First…" → "Say yes.").
    let title: String
    /// What is about to happen, in the order it happens.
    let preamble: String
    let rows: [PermissionsCardRow]
    /// A gate has an ask in flight, so the rows are not a second entrance to it.
    var rowsDisabled: Bool = false
    /// The capability whose wait may be escaped — a gate is standing in System Settings for it.
    var postponing: Capability?
    /// Every required capability has an answer, so the card may be left.
    var canContinue: Bool = false
    /// When the mark started saying the headline. Defaults to now, which is what a card appearing
    /// wants; a caller passing an instant in the past gets the delivery already finished.
    var phraseStart: Date = Date()

    var onRow: (Capability) -> Void = { _ in }
    var onPostpone: (Capability) -> Void = { _ in }
    var onContinue: () -> Void = {}
    var onDeferRest: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: InkLayout.permissionsBlockSpacing) {
            // The preamble is said before the first dialog, never after. macOS asks in its own
            // words — terse, system-voiced, and identical to the prompt of every app that ever
            // abused the same permission — and a user meeting that cold has only the app's
            // reputation to go on. Screen-recording tools die at exactly this prompt. Naming what is
            // coming, in order, in the app's own voice, is the difference between consenting and
            // being startled — and it is *this* card where having a face attached to that voice is
            // worth the most.
            //
            // The title changes under the user as the run moves, which `TalkingMark` treats as a new
            // phrase: the mark says the new line.
            TalkingMark(
                lead: [(title, .plain)], leadStyle: .firstTitle, aside: preamble, start: phraseStart)

            VStack(spacing: InkLayout.permissionsRowSpacing) {
                ForEach(rows, id: \.capability) { row in
                    InkPermissionRow(
                        title: row.title,
                        granted: row.granted,
                        status: row.status,
                        // **The row is the trigger.** It used to be described as "the way back for
                        // someone who said no and changed their mind", because the sequence asked
                        // for each of these itself. The sequence is gone: this tap is the only thing
                        // that raises a macOS prompt on this card.
                        action: { onRow(row.capability) }
                    )
                }
            }
            // While a gate has an ask in flight the rows are not a second entrance to it. A tap
            // during an episode used to fire a request for a *different* capability, which is the
            // collision the broker now refuses and this stops from being offered.
            .disabled(rowsDisabled)

            if let postponing {
                postponePanel(for: postponing)
            } else {
                footer
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: The way off the card

    /// Continue, and — while anything required is still unanswered — the escape beside it.
    ///
    /// The card **cannot** advance by itself any more, and that is deliberate rather than a
    /// consequence. It used to leave the moment the last required grant landed, which was fine while
    /// a run was driving: the grant was the end of something. Now the user is driving, and a card
    /// that vanished under them the instant they granted the third row would take the fourth — the
    /// one macOS never prompts for — away with it before they had a chance to click it.
    private var footer: some View {
        HStack(spacing: 10) {
            InkButton("Continue") { onContinue() }
                .disabled(!canContinue)
            if !canContinue {
                InkButton("I’ll do these later", kind: .secondary) { onDeferRest() }
            }
        }
        .padding(.top, 2)
    }

    // MARK: The escape

    /// The escape from one capability's wait, and the only thing other than a grant that ends it.
    ///
    /// It is a button the user presses on purpose, with the consequence written next to it — never a
    /// default, never a timeout, never a quiet Continue. A literal "grant or you cannot proceed" is
    /// unimplementable on macOS: TCC prompts once, after a Deny only System Settings remains, and a
    /// user who simply refuses would be stranded on this card forever.
    private func postponePanel(for capability: Capability) -> some View {
        HStack(spacing: 10) {
            InkButton("I’ll do this later", kind: .secondary) { onPostpone(capability) }
            Text(Self.postponeConsequence(for: capability))
                .inkStyle(.statusLabel)
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 2)
    }

    /// What is actually lost by saying "later" — named, so the choice is informed.
    static func postponeConsequence(for capability: Capability) -> String {
        switch capability {
        case .microphone: return "I won’t hear anything you say until you do."
        case .systemAudio: return "I’ll hear you on calls, but not the other side."
        case .screen: return "I won’t see your screen at all until you do."
        case .accessibility: return "I’ll read your screen from pixels rather than text."
        }
    }
}

#if DEBUG
#Preview("Permissions — nothing asked yet") {
    PermissionsCard(
        title: "First…",
        preamble: """
            macOS asks separately for each of these, and I won’t ask for any of them until you tell \
            me to. Read them, then click the one you’re ready for — I take them one at a time.
            """,
        rows: [
            PermissionsCardRow(capability: .microphone, granted: false, status: "Allow"),
            PermissionsCardRow(capability: .systemAudio, granted: false, status: "Allow"),
            PermissionsCardRow(capability: .screen, granted: false, status: "Allow"),
            PermissionsCardRow(capability: .accessibility, granted: false, status: "Allow"),
        ],
        phraseStart: Date().addingTimeInterval(-5))
    .frame(width: InkLayout.permissionsMaxWidth)
    .padding(InkLayout.pagePaddingHorizontal)
    .background(Ink.surface)
}
#endif
