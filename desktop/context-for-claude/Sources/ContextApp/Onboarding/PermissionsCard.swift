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
    /// One word — `Granted` / `Open` / `Checking` / `Action required`.
    var status: String

    var title: String { capability.title }
}

// MARK: - The card

/// The permissions step's column: what is about to happen, the four rows, and whichever of the two
/// panels the run has reached.
///
/// Split out of `OnboardingView` because **this is the card whose height varies**. Every other step
/// is a headline, a sentence and a button; this one grows a 42 pt escape panel while the gate waits
/// in System Settings and a 125 pt replica panel when the by-hand grant is offered, on top of a
/// preamble that changes length with the gate's phase and four sentences that wrap or do not. The
/// card is a fixed size, so "does the tallest state still fit" is a real question with a wrong
/// answer available — and a `private var` on a `View` is not something a test can measure.
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
    /// The gate has an ask in flight, so the rows are not a second entrance to it.
    var rowsDisabled: Bool = false
    /// The capability whose wait may be escaped — the gate is standing in System Settings for it.
    var postponing: Capability?
    /// The by-hand grant being offered, and how far along it is.
    var handGrant: Capability?
    var guiding: Bool = false
    /// When the mark started saying the headline. Defaults to now, which is what a card appearing
    /// wants; a caller passing an instant in the past gets the delivery already finished.
    var phraseStart: Date = Date()

    var onRow: (Capability) -> Void = { _ in }
    var onPostpone: (Capability) -> Void = { _ in }
    var onShowRow: (Capability) -> Void = { _ in }
    var onSkipHandGrant: () -> Void = {}

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
                        // The sequence asks for each of these itself. The row stays tappable only
                        // as the way back for someone who said no and changed their mind.
                        action: { onRow(row.capability) }
                    )
                }
            }
            // While the gate has an ask in flight the rows are not a second entrance to it. A tap
            // during the pause between two capabilities used to fire a request for a *different*
            // one, which is the collision the broker now refuses and this stops from being offered.
            .disabled(rowsDisabled)

            if let postponing {
                postponePanel(for: postponing)
            }

            if let handGrant {
                handGrantPanel(for: handGrant)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: The escape

    /// The escape, and the only thing other than a grant that ends a wait.
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
                .foregroundStyle(Ink.tertiary)
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

    // MARK: The choreography

    /// The by-hand grant, offered with a replica of what is about to be shown.
    ///
    /// The replica is ours and is captioned as ours. What it previews is System Settings' own
    /// affordance — on macOS 26 a dashed row with an instruction to drag it up into the list — which
    /// no application can draw and this one does not try to. Half a second of a likeness on our card
    /// is what makes the real thing recognised rather than puzzled over.
    private func handGrantPanel(for capability: Capability) -> some View {
        HStack(alignment: .top, spacing: 16) {
            GhostRowReplica()
                .frame(width: 168)

            VStack(alignment: .leading, spacing: 12) {
                Text(guiding ? "Look for the ring." : "I’ll show you the row.")
                    .inkStyle(.rowCopy)
                    .foregroundStyle(Ink.primary)

                Text(
                    guiding
                        ? "System Settings is open and I’m pointing at the row. Flip it and I’ll notice."
                        : "It opens System Settings and rings the row so you don’t have to hunt for it."
                )
                .inkStyle(.statusLabel)
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 10) {
                    InkButton(guiding ? "Waiting…" : "Show me the row") { onShowRow(capability) }
                        .disabled(guiding)
                    InkButton("Skip it", kind: .secondary) { onSkipHandGrant() }
                }
            }
        }
        .padding(.top, 2)
    }
}

#if DEBUG
#Preview("Permissions — the by-hand grant") {
    PermissionsCard(
        title: "One you flip yourself.",
        preamble: """
            That's the three macOS will ask about. The fourth has no dialog — it is a switch you \
            flip yourself, and this is what it looks like.
            """,
        rows: [
            PermissionsCardRow(capability: .microphone, granted: true, status: "Granted"),
            PermissionsCardRow(capability: .systemAudio, granted: true, status: "Granted"),
            PermissionsCardRow(capability: .screen, granted: true, status: "Granted"),
            PermissionsCardRow(capability: .accessibility, granted: false, status: "Open"),
        ],
        handGrant: .accessibility,
        phraseStart: Date().addingTimeInterval(-5))
    .frame(width: InkLayout.permissionsMaxWidth)
    .padding(InkLayout.pagePaddingHorizontal)
    .background(Ink.surface)
}
#endif
