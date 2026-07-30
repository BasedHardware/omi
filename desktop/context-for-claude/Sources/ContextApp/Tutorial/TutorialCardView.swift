import AppKit
import SwiftUI

/// The tutorial's card: one surface, whatever the step.
///
/// Every colour is an `Ink` token — a system semantic or `controlAccentColor` — so it reads correctly
/// in both appearances and carries no borrowed brand. Nothing here is purple (`INV-UI-1`).
struct TutorialCardView: View {
    @ObservedObject var model: TutorialModel
    @ObservedObject var chrome: TutorialOverlayChrome

    /// Fixed, and the same for every step: the window is sized from this card's ideal height at this
    /// width (`TutorialOverlay.fittingHeight()`), so the width must not depend on anything the window
    /// does.
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            content
            footer
        }
        .padding(.horizontal, 22)
        .padding(.vertical, 20)
        .frame(width: TutorialOverlay.width - (chrome.arrow == nil ? 0 : 18), alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
        .background(surface)
        .overlay(alignment: .top) { arrow(.top) }
        .overlay(alignment: .bottom) { arrow(.bottom) }
        .padding(chrome.arrow == nil ? 0 : 9)
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.settle)), value: model.step)
    }

    private var surface: some View {
        RoundedRectangle(cornerRadius: 16, style: .continuous)
            .fill(Ink.surface)
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(Ink.hairline, lineWidth: 1))
            .shadow(color: Color.black.opacity(0.22), radius: 18, y: 6)
    }

    /// The pointer, drawn only on the edge the placement asked for and offset to track the target.
    @ViewBuilder
    private func arrow(_ edge: TutorialArrow.Edge) -> some View {
        if let arrow = chrome.arrow, arrow.edge == edge {
            TutorialArrowShape(pointsUp: edge == .top)
                .fill(Ink.surface)
                .overlay(
                    TutorialArrowShape(pointsUp: edge == .top)
                        .stroke(Ink.hairline, lineWidth: 1))
                .frame(width: 20, height: 10)
                .offset(x: arrow.offset, y: edge == .top ? -9 : 9)
        }
    }

    // MARK: - Steps

    @ViewBuilder
    private var content: some View {
        switch model.step {
        case .invitation: invitation
        case .article: article
        case .screenAccess: screenAccess
        case .collectFrames: collectFrames
        case .openTimeline: openTimeline
        case .timeline: timeline
        case .scrollBack: scrollBack
        case .findMoments: findMoments
        case .query: query
        case .foundIt: foundIt
        case .claudeHandoff: claudeHandoff
        case .claudeProof: claudeProof
        case .allSet: allSet
        case .menuBar: menuBar
        case .finished, .skipped: EmptyView()
        }
    }

    // G1
    private var invitation: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline("Learn how this works")
            prose("Two minutes. You'll collect a few real frames, open the timeline, and find one of them again.")
        }
    }

    // G2
    private var article: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline("Something to look at")
            if model.articleDidOpen == false {
                prose("Your browser didn't open. Open this yourself, then continue:")
                Text(TutorialModel.articleURL.absoluteString)
                    .inkStyle(InkType.statusLabel, color: Ink.accent)
                    .textSelection(.enabled)
                InkButton("Try again", kind: .secondary) { model.openArticleAgain() }
            } else {
                prose("I opened Ling's Cars in your browser. Leave it open — there is a lot on that page.")
            }
        }
    }

    // G3
    private var screenAccess: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline(model.screenIsGranted ? "Thank you" : "I need to see your screen")
            prose(model.screenIsGranted
                  ? "Screen Recording is on. Frames can land now."
                  : "Screen Recording is off, so nothing you look at can be captured — and the rest of this tutorial would have nothing to find.")
            if !model.screenIsGranted {
                HStack(spacing: 10) {
                    InkButton(model.isRequestingScreenAccess ? "Waiting…" : "Allow") {
                        model.requestScreenAccess()
                    }
                    .disabled(model.isRequestingScreenAccess)
                    Text("I'll notice the moment you do.")
                        .inkStyle(InkType.statusLabel, color: Ink.tertiary)
                }
            }
        }
    }

    // G4/G5 — the live counter. The number comes from the capture store on every tick.
    private var collectFrames: some View {
        VStack(alignment: .leading, spacing: 12) {
            headline("Scroll around on this page")
            prose("Keep going — well past the banners and into the small print. I only store a frame when the screen genuinely changes.")
            HStack(spacing: 10) {
                ForEach(0..<TutorialModel.frameTarget, id: \.self) { index in
                    Circle()
                        .fill(index < model.framesCollected ? Ink.accent : Ink.wash)
                        .frame(width: 9, height: 9)
                }
                // Past the target the count keeps being the store's answer rather than the target's —
                // capping it would be the first small lie — so the label drops the "of 5" instead of
                // reading "6 of 5", which is what a live walkthrough showed.
                Text(model.gateIsSatisfied
                     ? "\(model.framesCollected) frames"
                     : "\(model.framesCollected) of \(TutorialModel.frameTarget) frames")
                    .inkStyle(InkType.rowCopy, color: Ink.primary)
                    .monospacedDigit()
            }
            if !model.gateIsSatisfied {
                Text(model.framesCollected == 0
                     ? "Nothing yet — this counts real frames in your own store, so it only moves when one lands."
                     : "Counting from your store, not from a clock.")
                    .inkStyle(InkType.statusLabel, color: Ink.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // G6
    private var openTimeline: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline("It's time to open the timeline")
            HStack(spacing: 8) {
                chordKey(TutorialModel.timelineChord)
                Text("is the chord.")
                    .inkStyle(InkType.prose, color: Ink.secondary)
            }
            prose(TutorialModel.timelineChordIsArmed
                  ? "Try it whenever you like — this button opens it too."
                  : "That chord isn't live on this machine yet, so this button is what opens it today.")
        }
    }

    // G7
    private var timeline: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline(model.timelineIsOpen ? "Everything I remembered" : "The timeline didn't open")
            prose(model.timelineIsOpen
                  ? "One frame per moment, laid out in real time — a long gap looks like a long gap."
                  : "There's no capture database to open it against yet, so there is nothing for it to show.")
        }
    }

    // G8
    private var scrollBack: some View {
        VStack(alignment: .leading, spacing: 12) {
            headline("Scroll left to see the past")
            prose("The track underneath is time. Drag it left and you travel back through your own day.")
            TutorialScrollHint()
        }
    }

    // G9
    private var findMoments: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline("Find specific moments")
            prose("Click Search All, up there. I'll notice when you do.")
        }
    }

    // G10/G11
    private var query: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline("Type what you're looking for")
            prose("A word you actually saw on that page, then press Return.")
            TutorialQueryField(model: model)
            if let message = model.searchMessage {
                Text(message)
                    .inkStyle(InkType.statusLabel, color: Ink.errorRed)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // G12
    private var foundIt: some View {
        VStack(alignment: .leading, spacing: 12) {
            headline("Found it")
            prose(model.chosenMemory == nil
                  ? "Tap the memory to jump back to that exact moment."
                  : "That's the moment, as it was.")
            VStack(spacing: 6) {
                ForEach(model.results) { memory in
                    TutorialMemoryRow(
                        memory: memory,
                        isChosen: model.chosenMemory == memory,
                        action: { model.choose(memory) })
                }
            }
            if let moment = model.chosenMoment {
                TutorialMomentPreview(moment: moment)
            } else if model.chosenMemory != nil {
                Text("No stored picture survives for that second — the text is what I still have.")
                    .inkStyle(InkType.statusLabel, color: Ink.tertiary)
            }
        }
    }

    private var claudeHandoff: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline("Now hand it to Claude")
            prose("Claude reads its MCP config when it starts, so it has to be restarted before it can ask me anything.")
            Text("“\(TutorialModel.suggestedQuestion)”")
                .inkStyle(InkType.rowCopy, color: Ink.primary)
            HStack(spacing: 10) {
                InkButton(model.claudeIsInstalled ? "Restart Claude" : "Copy the question") {
                    model.handOffToClaude()
                }
                Text(model.didRestartClaude ? "Restarting, and copied." : "In a terminal: claude")
                    .inkStyle(InkType.statusLabel, color: Ink.tertiary)
            }
        }
    }

    private var claudeProof: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline(model.proof == nil ? "Ask Claude" : "Claude just read your context")
            if let proof = model.proof {
                prose("It called \(proof.tool). That is a real call, recorded by the server that served it.")
            } else {
                prose("Paste the question into Claude. I'll only say this worked once Claude has genuinely called one of my tools — nothing here is on a timer.")
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Waiting for a real tool call.")
                        .inkStyle(InkType.statusLabel, color: Ink.tertiary)
                }
            }
        }
    }

    // G13
    private var allSet: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline("You're all set")
            prose(model.framesSummary)
        }
    }

    // G14
    private var menuBar: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline("One more thing")
            prose("You can always find me up here, in the menu bar.")
        }
    }

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
                TutorialProgressDots(index: model.progress.index, total: model.progress.total)
                Spacer(minLength: 8)
                // Every step is skippable, and skipping tears the whole thing down.
                if model.step != .menuBar {
                    Button("Skip") { model.skip() }
                        .buttonStyle(.plain)
                        .inkStyle(InkType.statusLabel, color: Ink.tertiary)
                        .fixedSize()
                }
                if let title = primaryTitle {
                    InkButton(title) { model.advance() }
                        .disabled(!model.gateIsSatisfied)
                        .fixedSize()
                }
            }
        }
    }

    /// The primary action's label, or nil for the steps whose gate no button can satisfy — the search
    /// beat, which needs a real result, and the proof beat, which needs Claude.
    private var primaryTitle: String? {
        switch model.step {
        case .invitation: return "Start"
        case .article: return "I see it"
        case .screenAccess: return model.screenIsGranted ? "Continue" : nil
        case .collectFrames: return "Continue"
        case .openTimeline: return "Open the timeline"
        case .timeline, .scrollBack, .findMoments, .foundIt, .claudeHandoff: return "Continue"
        case .query: return nil
        case .claudeProof: return model.proof == nil ? nil : "Continue"
        case .allSet: return "Continue"
        case .menuBar: return "Done"
        case .finished, .skipped: return nil
        }
    }

    private var waiverLabel: String {
        switch model.step.gate {
        case .realFrames: return "Nothing is arriving — continue anyway"
        case .screenRecordingGrant: return "Continue without it"
        case .userAction, .realSearchResult, .genuineToolCall: return ""
        }
    }

    // MARK: - Pieces

    /// `stepHeadline` rather than a hand-assembled face and size: `Ink`'s roles carry their tracking,
    /// and the header comment in that file is explicit that a caller who reaches for
    /// `.openRunde(_:_:)` and forgets the tracking has shipped a different product.
    private func headline(_ text: String) -> some View {
        Text(text)
            .inkStyle(InkType.stepHeadline, color: Ink.primary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func prose(_ text: String) -> some View {
        Text(text)
            .inkStyle(InkType.prose, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func chordKey(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .foregroundStyle(Ink.primary)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(Ink.rowFill)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .strokeBorder(Ink.hairline, lineWidth: 1)))
    }
}

// MARK: - Progress

struct TutorialProgressDots: View {
    let index: Int
    let total: Int

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<max(total, 1), id: \.self) { position in
                Circle()
                    .fill(position <= index ? Ink.primary.opacity(0.75) : Ink.wash)
                    .frame(width: 5, height: 5)
            }
        }
        .accessibilityLabel(Text("Step \(index + 1) of \(total)"))
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

// MARK: - G8's hint

/// Three marks travelling leftwards, which is the gesture the step is asking for. Collapses to a
/// static arrow under Reduce Motion, where a loop would be exactly what the setting exists to stop.
struct TutorialScrollHint: View {
    @State private var shift = false

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "arrow.left")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Ink.secondary)
            ZStack(alignment: .leading) {
                Capsule().fill(Ink.wash).frame(height: 6)
                HStack(spacing: 5) {
                    ForEach(0..<3, id: \.self) { _ in
                        Capsule().fill(Ink.accent.opacity(0.85)).frame(width: 22, height: 6)
                    }
                }
                .offset(x: shift ? -34 : 34)
            }
            .frame(height: 6)
            .clipShape(Capsule())
        }
        .onAppear {
            guard !InkReduceMotion.isEnabled else { return }
            withAnimation(.easeInOut(duration: 1.5).repeatForever(autoreverses: false)) {
                shift = true
            }
        }
    }
}

// MARK: - G10's field

/// The query field. Submits on Return and never pretends: the search it runs is the real one.
struct TutorialQueryField: View {
    @ObservedObject var model: TutorialModel
    @State private var draft = ""
    @FocusState private var isFocused: Bool

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Ink.tertiary)
            TextField("", text: $draft, prompt: Text("a word you saw"))
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundStyle(Ink.primary)
                .focused($isFocused)
                .onSubmit { model.search(draft) }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Ink.rowFill)
                .overlay(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .strokeBorder(Ink.hairline, lineWidth: 1)))
        .onAppear { isFocused = true }
    }
}

// MARK: - G12's result

struct TutorialMemoryRow: View {
    let memory: TutorialMemory
    let isChosen: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: memory.kind == "screen" ? "rectangle.on.rectangle" : "waveform")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Ink.tertiary)
                    .frame(width: 12)
                VStack(alignment: .leading, spacing: 2) {
                    Text(memory.text)
                        .font(.system(size: 12))
                        .foregroundStyle(Ink.primary)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                    Text([memory.app, memory.when].compactMap { $0 }.joined(separator: " · "))
                        .inkStyle(InkType.statusLabel, color: Ink.tertiary)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(isChosen ? Ink.rowFillHover : Ink.rowFill))
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .strokeBorder(isChosen ? Ink.accent.opacity(0.7) : Color.clear, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

/// The picture that was really taken at the chosen moment, loaded off the main thread.
struct TutorialMomentPreview: View {
    let moment: TutorialMoment
    @State private var image: NSImage?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(maxHeight: 140)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .strokeBorder(Ink.hairline, lineWidth: 1))
            }
            Text("\(moment.app) · \(ContextTimeLabel.short(moment.at))")
                .inkStyle(InkType.statusLabel, color: Ink.tertiary)
        }
        .task(id: moment.imagePath) {
            let path = moment.imagePath
            image = await Task.detached { NSImage(contentsOfFile: path) }.value
        }
    }
}

/// A clock time, for the one label that needs one. Deliberately local to the tutorial: the timeline
/// has its own formatter and neither should reach into the other's.
enum ContextTimeLabel {
    private static let formatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm:ss a"
        return formatter
    }()

    static func short(_ epoch: Double) -> String {
        formatter.string(from: Date(timeIntervalSince1970: epoch))
    }
}
