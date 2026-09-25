import AppKit
import SwiftUI

/// The tutorial's card: one surface, whatever the step.
///
/// Every card is the same three things in the same order — **the mark saying one line**, whatever
/// that line needs the user to touch, and the controls. Nothing else. The words are not written here:
/// they come from `TutorialModel.speech`, which is where a claim can be tested, and this file only
/// decides how they are delivered.
///
/// Two things are deliberately absent, and both were here before:
///
/// - **A step counter.** A number that says how much of this is left is a number people read as a
///   reason to leave. The user is told what to do next and nothing about the length of the queue.
/// - **A frame readout.** The capture beat used to show five dots filling and "3 of 5 frames", which
///   is this app's plumbing narrated at someone who has been using it for ninety seconds. The gate is
///   unchanged — the step still cannot be left until the frames are genuinely in the store — but the
///   card says "Scroll through it for a bit" and then "Got it", which is the same fact in a human's
///   words. Nothing here is on a timer; see `TutorialModel.outcome`.
///
/// The two beats that ask for a *physical action* draw it rather than describe it: the way in
/// presses itself on a keyboard, and the way across is swiped by two fingers on a trackpad. Both
/// live in `TutorialDemonstrations.swift`, both are rendered only while their step is still waiting,
/// and neither can move the flow along.
///
/// Every colour is an `Ink` token — a named system colour or an alpha on one — so it reads correctly
/// in both appearances and carries no borrowed brand. Nothing here is purple, and nothing here reads
/// a hue off the machine, which is the only way that can be true on every machine (`INV-UI-1`).
struct TutorialCardView: View {
    @ObservedObject var model: TutorialModel
    @ObservedObject var chrome: TutorialOverlayChrome

    /// The air either side of everything on the card. A constant rather than a literal in the
    /// modifier so that anything measuring what the card has room for is measuring the same number
    /// the card is drawn with, rather than a second copy of it that drifts.
    static let horizontalPadding: CGFloat = 22

    /// The card's outer width. A coach mark with an arrow is drawn a little narrower so the arrow has
    /// room to sit outside the panel without leaving the window.
    private var cardWidth: CGFloat {
        TutorialOverlay.width - (chrome.arrow == nil ? 0 : 18)
    }

    /// Fixed, and the same for every step: the window is sized from this card's ideal height at this
    /// width (`TutorialOverlay.fittingHeight()`), so the width must not depend on anything the window
    /// does.
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // The mark says the card's own words — the same component and the same call-site shape
            // onboarding uses, because it is the same character and this is the screen straight
            // after those.
            TalkingMark(
                lead: model.speech.runs,
                leadStyle: InkType.stepHeadline,
                aside: model.speech.aside)

            extras
            footer
        }
        .padding(.horizontal, Self.horizontalPadding)
        .padding(.vertical, 20)
        .frame(width: cardWidth, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
        // The app's shared glass, not a fill of its own: a coach mark floats over the desktop beside
        // the very windows it points at, and it has to be made of the same thing they are.
        //
        // **`InkGlassSurface` and not `.inkGlassPanel()`, because the modifier draws the specular top
        // edge outside its own clip.**
        //
        // The modifier assembles the panel in SwiftUI — an `InkGlassBackdrop` and the scrim in a
        // `ZStack`, cut with `.clipShape` — and then hangs the sheen on as an `.overlay` *after* that
        // cut. The material and the scrim come out rounded (the clip really does become a
        // `masksToBounds` layer at 22 pt continuous — checked by walking the hosted tree, not
        // assumed); the sheen does not. It is a 1 pt white line at 50%, laid across the card's full
        // width at its very top — and the top corners are exactly where the panel is curving away
        // from it, so the line carries straight on past both of them into transparent space and
        // squares the card off.
        //
        // Which is why one look at this card produced two complaints: "above it, there's a weird line
        // showing up", and "I can see like weird like boxy edges and it's not completely rounded".
        // One defect; the second is what the first looks like from a step back.
        //
        // `InkGlassSurface` is the app's real `InkGlassView`, where the sheen is a *subview of the
        // panel* and is therefore cut by the same corner as everything else on it — the highlight
        // stops where the glass does, which is what makes it read as light caught on a face rather
        // than as a hairline drawn over one. Two things the modifier also carried do not come with it
        // and are therefore stated here: the ambient shadow, and the light appearance that makes
        // `Ink`'s dynamic colours resolve dark on the panel.
        //
        // The modifier itself still has the defect and `SearchSurface` still wears it. Fixing it
        // there is moving one `.overlay` inside the `.clipShape` in `InkGlass.swift`.
        .environment(\.colorScheme, .light)
        .background {
            InkGlassSurface()
                .shadow(
                    color: .black.opacity(Double(InkGlassShadow.ambient.opacity)),
                    // SwiftUI's blur radius is half Core Animation's for the same visual spread.
                    radius: InkGlassShadow.ambient.radius / 2,
                    y: -InkGlassShadow.ambient.offsetY)
        }
        .overlay(alignment: .top) { arrow(.top) }
        .overlay(alignment: .bottom) { arrow(.bottom) }
        .padding(chrome.arrow == nil ? 0 : 9)
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.settle)), value: model.step)
    }

    /// The pointer, drawn only on the edge the placement asked for and offset to track the target.
    ///
    /// The same glass as the card, clipped to the triangle rather than filled with a flat colour: a
    /// solid tab on a translucent card is visible as a tab on every wallpaper that is not the one it
    /// was picked against.
    @ViewBuilder
    private func arrow(_ edge: TutorialArrow.Edge) -> some View {
        if let arrow = chrome.arrow, arrow.edge == edge {
            InkGlassSurface(cornerRadius: 0)
                .clipShape(TutorialArrowShape(pointsUp: edge == .top))
                .frame(width: 20, height: 10)
                .offset(x: arrow.offset, y: edge == .top ? -9 : 9)
        }
    }

    // MARK: - What the step needs the user to touch

    /// Only the steps that ask for something have anything here. A card whose whole content is one
    /// spoken line and a button is the shape most of them want.
    @ViewBuilder
    private var extras: some View {
        switch model.step {
        case .screenAccess where !model.screenIsGranted:
            HStack(spacing: 10) {
                InkButton(model.isRequestingScreenAccess ? "Waiting…" : "Allow") {
                    model.requestScreenAccess()
                }
                .disabled(model.isRequestingScreenAccess)
                // Only after the ask, and only as a button. The model no longer opens the pane on
                // the user's behalf — `Permissions.request(.screen)` already does when there is one
                // to open, and doing it twice opened two windows on one press.
                if model.didAskForScreenAccess {
                    InkButton("Open Settings", kind: .secondary) { model.openScreenSettings() }
                } else {
                    // Only before the ask. Afterwards the mark's own line says it, and three things
                    // on this row wrapped the sentence under the buttons.
                    Text("I will notice the moment you do.")
                        .inkStyle(InkType.statusLabel, color: Ink.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

        // Only while something could still arrive. A spinner over "nothing will arrive until Screen
        // Recording is on" would be the card miming work it knows is not happening.
        case .collectFrames where model.outcome == .waiting:
            listening

        // The way in, moving. Shown only when it is genuinely registered: a tutorial that taught
        // keys this machine does not listen for would be teaching a surface that is not there, and
        // this beat cannot be earned on such a machine at all.
        //
        // **Two drawings, because this app ships two shapes of gesture and neither picture can tell
        // the other's story.** The app's own way in is both Command keys pressed *together*, which
        // has no keycap spelling at all — two ⌘ chips side by side are exactly as good a picture of
        // "press the left one, then the right one", and that ambiguity has been reported before. So
        // it gets a keyboard's bottom row with the space bar between the two caps, and they go down
        // on the same beat. A rebound chord is typed, and gets the chip that types itself. The model
        // decides which from the printed shortcut and nothing else (`activityChordIsCommandPair`),
        // so the drawing and the card's own sentence cannot disagree about the gesture.
        case .openActivity where model.activityChordIsArmed:
            HStack(spacing: 10) {
                if model.activityChordIsCommandPair {
                    TutorialCommandPairDemo()
                } else {
                    TutorialChordDemo(chord: model.activityChord)
                }
                Text("opens it from anywhere.")
                    .inkStyle(InkType.statusLabel, color: Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

        // The gesture, being made, and only until they have made it. Leaving a loop running under
        // "there you go" would be the card still asking for something it has already been given —
        // which is also what stops it: this branch is the only thing rendering it.
        //
        // Two fingers on a trackpad now, not a hand glyph on a strip: the beat's words asked for two
        // fingers and its picture showed one shape on no particular surface, which is what was
        // reported. See `TutorialScrollDemo`.
        case .timeline where model.timelineIsOpen && !model.didDrag:
            TutorialScrollDemo()

        case .claudeHandoff:
            VStack(alignment: .leading, spacing: 12) {
                Text("“\(TutorialModel.suggestedQuestion)”")
                    .inkStyle(InkType.rowCopy, color: Ink.primary)
                    .fixedSize(horizontal: false, vertical: true)
                if model.isAskingClaude {
                    listening
                } else if model.claudeAsk == nil, model.claudeNeedsRestart {
                    // The consent row, and the only place anything in this app offers to quit
                    // another one. Both choices are real: declining still hands the question over,
                    // to the Claude they already have, and the card then says the reach may be
                    // stale rather than quietly taking their session to force a gate.
                    HStack(spacing: 10) {
                        InkButton("Restart it and ask") { model.askClaude(restartingFirst: true) }
                        InkButton("Keep it open", kind: .secondary) {
                            model.askClaude(restartingFirst: false)
                        }
                    }
                } else if model.claudeAsk != nil {
                    // A retry rather than the old "Restart Claude": the handoff has already run, and
                    // the only thing left worth offering is doing it again if it did not land.
                    InkButton("Ask Claude again", kind: .secondary) { model.askClaude() }
                }
            }

        // The one control this beat has, and only in the one state that needs it: the user closed the
        // search panel before finding anything. Everything else about this beat happens *in* the real
        // panel — the field, the results, the card that is pressed to travel back — which is why
        // there is nothing else here.
        case .query where !model.searchPanelIsOpen && !model.gateIsSatisfied
            && model.openedMomentHasPicture == nil:
            InkButton("Open search", kind: .secondary) { model.openSearchPanel() }

        case .claudeProof where model.proof == nil:
            listening

        default:
            EmptyView()
        }
    }

    /// The one thing the card shows while it is waiting on something real: that it is awake.
    ///
    /// Indeterminate on purpose. Both waits — frames landing, Claude calling a tool — used to be
    /// narrated with counts and machinery, and neither number ever helped: there is nothing the user
    /// can do with "3 of 5" that they cannot do with "not yet". What it must never become is a bar
    /// that fills on a clock, which would be the one lie this whole flow is built to avoid.
    private var listening: some View {
        ProgressView()
            .controlSize(.small)
            .accessibilityLabel(Text("Waiting"))
    }

    // The search beat's field and its grid of results stood here (`TutorialQueryField`,
    // `TutorialResultsGrid`, `TutorialResultCard` and its style). All of it is gone, and none of it
    // was replaced: the beat is conducted in the real search panel now, so the field is
    // `SearchBarView`'s field and the results are `SearchResultsView`'s grid.
    //
    // It is worth naming what the deleted grid was for, because the reasoning survives its code. It
    // existed to answer a report — *"this after search after onboarding needs to show results in
    // tabular form with screen if any. This list with only text looks so bland."* — and the fix was
    // to draw each hit as a picture of the moment, through the same `SearchThumbnail` and the same
    // `FrameLoader` the real panel uses, so that the tutorial did not teach a different-looking
    // result from the one the user was about to meet. That was the right instinct arriving one step
    // short of its conclusion: the way to stop teaching a different-looking result is not to draw a
    // faithful copy of the panel at 470 pt, it is to open the panel.

    // MARK: - Footer

    /// The waiver sits on its own row above the controls rather than inside them. Its label is a whole
    /// sentence — it has to be, because it is the one control that says what did *not* happen — and on
    /// a live walkthrough it squeezed the primary button down to "Con ti…".
    private var footer: some View {
        VStack(alignment: .leading, spacing: 10) {
            if model.waiverIsOffered {
                Button(waiverLabel) { model.waive() }
                    .buttonStyle(.plain)
                    .inkStyle(InkType.statusLabel, color: Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 12) {
                if let title = primaryTitle {
                    InkButton(title) { model.advance() }
                        // One condition, and it is the model's. This used to add "or the handoff is
                        // running" here, which covered the state where Claude had been asked and
                        // left uncovered the state before it — the consent question, whose two
                        // answers are on this very card. `gateIsSatisfied` now holds both
                        // (`TutorialModel.isAwaitingAnAnswer`), so the button and `advance()` cannot
                        // disagree about what this beat is waiting for.
                        .disabled(!model.gateIsSatisfied)
                        .fixedSize()
                }
                Spacer(minLength: 8)
                // Every step is skippable, and skipping tears the whole thing down.
                if model.step != .menuBar {
                    Button("Skip") { model.skip() }
                        .buttonStyle(.plain)
                        .inkStyle(InkType.statusLabel, color: Ink.secondary)
                        .fixedSize()
                }
            }
        }
    }

    /// The primary action's label, or nil for the one step no button can move: the proof beat, which
    /// needs Claude. Everywhere else the button is present and *disabled* until the gate is met, so
    /// the way forward is always visible and never a lie about being ready.
    private var primaryTitle: String? {
        switch model.step {
        case .invitation: return "Start"
        case .screenAccess: return model.screenIsGranted ? "Continue" : nil
        case .collectFrames: return "Continue"
        // No button can move these three: one needs a keypress the tutorial must not fake, one a
        // gesture it must not mime, and one a click on the real pill — the press *is* the transition
        // in every case, and a Continue beside it would be a second way past a lesson that has not
        // been given. All three have a labelled way out that says what did not happen.
        case .openActivity: return nil
        case .timeline: return model.didDrag ? "Continue" : nil
        case .findMoments: return nil
        case .query, .claudeHandoff: return "Continue"
        case .claudeProof: return model.proof == nil ? nil : "Continue"
        case .allSet: return "Continue"
        case .menuBar: return "Done"
        case .finished, .skipped: return nil
        }
    }

    private var waiverLabel: String {
        switch model.step.gate {
        case .realFrames: return "Nothing is arriving — carry on anyway"
        case .screenRecordingGrant: return "Carry on without it"
        // "Carry on anyway" and no longer "open it for me". The waiver used to promise a window,
        // because the chord opened the timeline and the beat after it needed one; the chord opens the
        // Activity search panel now, which is not what the beat after wants, and that beat opens its
        // own timeline whatever happened here. There is nothing left to offer but the way past, and a
        // label that offered more would be describing an action nothing takes.
        case .realHotkey: return "That shortcut isn't working — carry on anyway"
        case .realGesture: return "I can't drag it — carry on anyway"
        case .realSearchPanel: return "I can't find that button — open search for me"
        case .userAction, .realSearchResult, .genuineToolCall: return ""
        }
    }
}

// MARK: - The arrow

struct TutorialArrowShape: Shape {
    let pointsUp: Bool

    func path(in rect: CGRect) -> Path {
        var path = Path()
        if pointsUp {
            path.move(to: CGPoint(x: rect.midX, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        } else {
            path.move(to: CGPoint(x: rect.midX, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
        }
        path.closeSubpath()
        return path
    }
}
// MARK: - What used to stand here

// `TutorialQueryField`, `TutorialResultGrid`, `TutorialResultsGrid`, `TutorialResultCard` and its
// button style were all below this line, along with the `TutorialMomentPreview` that predated them.
// Roughly three hundred lines of a search surface, drawn on a coach mark 470 pt wide, reachable only
// during the two minutes of a tutorial that runs once per install.
//
// None of it was wrong on its own terms — the grid was two across because three would have put a
// 133 pt card under `SearchLayout.minimumCardWidth`; the cards used `SearchThumbnail`,
// `SearchSpokenWell`, `RewindAppIcon` and `SearchTime.describe` precisely so the tutorial's results
// looked like the real ones. The whole of it was the wrong idea, and the comments arguing the card
// down to two columns are the tell: they are the arithmetic of fitting a 760 pt panel into a coach
// mark, which is work that only exists if the coach mark is standing in for the panel.
//
// It is not standing in for anything now. `TutorialStep.findMoments` waits for `SearchBarWindow` to
// come up because the user pressed the real pill; `TutorialStep.query` waits for that panel to
// answer a real question. The card beside it says one line and offers Continue, which is all a coach
// mark was ever supposed to be.
