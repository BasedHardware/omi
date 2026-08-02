import AppKit
import ContextCore
import SwiftUI

/// The timeline window's chrome, laid out to the spec in `docs/rewind-and-settings.md` § Part 1.
///
/// Every colour is a system semantic through `Ink`, so the window works in both appearances. The implementation this was ported from is hardcoded dark — dozens of literal
/// `Color.white.opacity(…)` and `NSColor(white:…)` values, plus a forced `.preferredColorScheme(.dark)`
/// — which is invisible on a light window. There is no `.white` or `NSColor(white:` anywhere in this
/// directory except the two places a label sits on a saturated app-colour chip, where a fixed light
/// label is correct precisely because the chip is not a semantic surface and does not invert.
struct RewindView: View {
    @ObservedObject var model: RewindModel
    /// Opens Settings. Owned by the app shell, which is not this agent's file, so it arrives as a
    /// closure the shell supplies rather than a call into a type that may not exist yet.
    var onOpenSettings: () -> Void = {}
    /// Hands a query to Claude. Same reasoning — the spec is explicit that the search bar routes to
    /// Claude rather than being a second retrieval engine, and that route lives in the shell.
    var onSearch: (String) -> Void = { _ in }

    @State private var showsDatePicker = false

    /// Our word for the mode. Theirs is "Coasting"; the spec asks for our own.
    ///
    /// "Remembering" is the app's own vocabulary — the onboarding copy is "I listen, I watch, and I
    /// remember" — and it describes what the window is actually doing: showing what was remembered,
    /// present tense, while the user moves through it.
    static let modeTitle = "Remembering"

    var body: some View {
        VStack(spacing: 0) {
            header
            frameStage
            track
        }
        // Deliberately no background. `RewindWindow` hosts this on `InkGlassView`, which owns the
        // material and the scrim; an opaque `Ink.surface` here would paint over the glass and this
        // window would be the one surface in the app that is not translucent. Two grounds is how a
        // translucent surface ends up opaque in one appearance and muddy in the other.
        .onAppear { model.loadInitial() }
        // The frame-image zoom, which the spec insists is a different feature from the track zoom.
        // Both live here so the two key paths cannot be confused at the call site.
        .background(zoomKeyboardShortcuts)
    }

    // MARK: - Header

    private var header: some View {
        ZStack {
            Text(RewindView.modeTitle)
                .inkStyle(InkType.rowCopy, color: Ink.primary)

            HStack(spacing: 8) {
                searchPill
                gearButton
                Spacer(minLength: 0)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .overlay(alignment: .bottom) { Divider() }
    }

    /// "Search All", showing its `/` hint. A button rather than a text field: pressing it is what
    /// hands a query to Claude, and drawing an editable field here would promise an in-app search
    /// index that does not exist.
    private var searchPill: some View {
        Button {
            onSearch("")
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11, weight: .semibold))
                Text("Search All")
                    .font(.system(size: 12, weight: .medium))
                Text("/")
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Ink.tertiary)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1)
                    .background(
                        RoundedRectangle(cornerRadius: 3, style: .continuous)
                            .fill(Ink.wash))
            }
            .foregroundStyle(Ink.primary)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                Capsule(style: .continuous)
                    .fill(Ink.rowFill)
                    .overlay(Capsule(style: .continuous).strokeBorder(Ink.hairline, lineWidth: 1)))
        }
        .buttonStyle(.plain)
        .keyboardShortcut("/", modifiers: [])
        .help("Search everything captured")
    }

    private var gearButton: some View {
        Button(action: onOpenSettings) {
            Image(systemName: "gearshape")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Ink.primary)
                .frame(width: 26, height: 26)
                .background(Circle().fill(Ink.rowFill))
        }
        .buttonStyle(.plain)
        .help("Settings")
    }

    // MARK: - The frame

    private var frameStage: some View {
        GeometryReader { geometry in
            ZStack {
                framePicture(in: geometry.size)

                // Chevrons sit on the frame's own left and right edges, per the spec.
                HStack {
                    segmentChevron(forward: false)
                    Spacer(minLength: 0)
                    segmentChevron(forward: true)
                }
                .padding(.horizontal, 10)

                VStack {
                    Spacer(minLength: 0)
                    HStack(alignment: .bottom) {
                        timestampPill
                        Spacer(minLength: 0)
                        controlCluster
                    }
                }
                .padding(14)
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// The captured frame, with a border keyed to the segment it belongs to.
    private func framePicture(in size: CGSize) -> some View {
        // Nil is an honest outcome: a frame can belong to no activity block (short stretches are
        // dropped by the activity query), and then the border is a neutral hairline rather than an
        // invented colour.
        let borderColor = model.currentBlock.map { RewindPalette.color(forApp: $0.app) } ?? Ink.hairline
        let shape = RoundedRectangle(cornerRadius: 10, style: .continuous)

        return ZStack {
            if let image = model.image {
                GeometryReader { inner in
                    Image(nsImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .scaleEffect(model.imageZoom)
                        .frame(width: inner.size.width, height: inner.size.height)
                        .clipped()
                        .overlay {
                            if model.showsLiveText, let liveText = model.liveText, !liveText.isEmpty {
                                LiveTextOverlay(result: liveText, containerSize: inner.size)
                                    .scaleEffect(model.imageZoom)
                            }
                        }
                }
            } else {
                emptyStage
            }
        }
        .clipShape(shape)
        .overlay(shape.strokeBorder(borderColor, lineWidth: 2))
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
    }

    /// What the stage says when there is no picture — which has three distinct causes that must not
    /// be collapsed into one blank rectangle.
    private var emptyStage: some View {
        VStack(spacing: 8) {
            if let loadError = model.loadError {
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 20))
                    .foregroundStyle(Ink.errorRed)
                Text(loadError).inkStyle(InkType.statusLabel, color: Ink.secondary)
            } else if model.frames.isEmpty {
                Image(systemName: "moon.zzz")
                    .font(.system(size: 22))
                    .foregroundStyle(Ink.tertiary)
                Text("Nothing was captured on this day.")
                    .inkStyle(InkType.statusLabel, color: Ink.secondary)
            } else if model.imageIsMissing {
                Image(systemName: "photo.badge.exclamationmark")
                    .font(.system(size: 22))
                    .foregroundStyle(Ink.tertiary)
                // Retention deletes pictures and keeps the text. Saying so is better than a blank
                // frame that reads as a bug.
                Text("This frame's picture is no longer on disk.")
                    .inkStyle(InkType.statusLabel, color: Ink.secondary)
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Ink.rowFill)
    }

    private func segmentChevron(forward: Bool) -> some View {
        let enabled = forward ? model.hasNextSegment : model.hasPreviousSegment
        return Button {
            model.goToAdjacentSegment(forward: forward)
        } label: {
            Image(systemName: forward ? "chevron.right" : "chevron.left")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Ink.primary)
                .frame(width: 30, height: 44)
                .background(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(Ink.rowFill)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .strokeBorder(Ink.hairline, lineWidth: 1)))
        }
        .buttonStyle(.plain)
        .opacity(enabled ? 1 : 0)
        .disabled(!enabled)
        .keyboardShortcut(forward ? .rightArrow : .leftArrow, modifiers: [.option])
        .help(forward ? "Next segment" : "Previous segment")
    }

    // MARK: - Bottom-left: the date/time pill

    private var timestampPill: some View {
        Button {
            showsDatePicker.toggle()
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "calendar")
                    .font(.system(size: 11, weight: .medium))
                Text(model.timestampLabel)
                    .font(.system(size: 12, weight: .medium))
                Image(systemName: "chevron.down")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(Ink.tertiary)
            }
            .foregroundStyle(Ink.primary)
            .padding(.horizontal, 11)
            .padding(.vertical, 6)
            .background(
                Capsule(style: .continuous)
                    .fill(.regularMaterial)
                    .overlay(Capsule(style: .continuous).strokeBorder(Ink.hairline, lineWidth: 1)))
        }
        .buttonStyle(.plain)
        .popover(isPresented: $showsDatePicker, arrowEdge: .bottom) {
            datePicker
        }
    }

    private var datePicker: some View {
        VStack(spacing: 10) {
            DatePicker(
                "",
                selection: Binding(
                    get: { model.day },
                    set: { model.load(day: $0) }),
                in: pickerRange,
                displayedComponents: .date
            )
            .datePickerStyle(.graphical)
            .labelsHidden()
            .frame(width: 260)
        }
        .padding(14)
    }

    /// Bounded by what was actually captured, so the picker cannot offer a day that opens empty.
    private var pickerRange: ClosedRange<Date> {
        guard let coverage = model.coverage else {
            let today = Calendar.current.startOfDay(for: Date())
            return today...today
        }
        let oldest = Date(timeIntervalSince1970: coverage.lowerBound)
        let newest = Date(timeIntervalSince1970: coverage.upperBound)
        return min(oldest, newest)...max(oldest, newest)
    }

    // MARK: - Bottom-right: the four circular buttons

    /// In the spec's order: open externally, live text, zoom out, zoom in.
    private var controlCluster: some View {
        HStack(spacing: 8) {
            openExternallyButton
            liveTextButton
            // The tooltips name the pinch because the gesture is otherwise undiscoverable: nothing on
            // screen says the track answers to fingers, and these two buttons are where somebody
            // looking for the feature will hover first.
            circleButton(
                systemName: "minus.magnifyingglass",
                help: "Zoom the timeline out — or pinch in on the track",
                enabled: model.canZoomTrackOut
            ) { model.zoomTrack(in: false) }
            circleButton(
                systemName: "plus.magnifyingglass",
                help: "Zoom the timeline in — or pinch out on the track",
                enabled: model.canZoomTrackIn
            ) { model.zoomTrack(in: true) }
        }
    }

    /// Shown **only** when the frame resolves to something that genuinely exists on disk.
    ///
    /// Hidden — not disabled — for everything else. A disabled control still advertises that the
    /// feature exists and that this frame merely failed at it, which is the opposite of the truth:
    /// our schema has no URL for the frame at all (see `OpenExternally`). On the real database this
    /// resolves 3 frames of 3,149, so the button is almost always absent, and that is the honest
    /// rendering of what is known.
    @ViewBuilder
    private var openExternallyButton: some View {
        if let frame = model.currentFrame, let target = OpenExternally.target(for: frame) {
            circleButton(
                systemName: target.symbolName,
                help: target.accessibilityDescription,
                enabled: true
            ) { OpenExternally.open(target) }
            .keyboardShortcut(.return, modifiers: [])
        }
    }

    private var liveTextButton: some View {
        circleButton(
            // Two genuinely different glyphs. Recognition runs on demand and can take most of a
            // second, so the button has to show that it is working. The previous ternary returned
            // "text.viewfinder" on both branches: it coded for a state it never rendered.
            systemName: model.isRecognizing ? "arrow.triangle.2.circlepath" : "text.viewfinder",
            help: "Highlight selectable text in this frame",
            // Dim until a pass has actually detected something, which is the spec's wording read
            // literally. It stays pressable — pressing it is what runs the pass.
            enabled: model.liveTextIsAvailable,
            isOn: model.showsLiveText
        ) { model.toggleLiveText() }
    }

    private func circleButton(
        systemName: String,
        help: String,
        enabled: Bool,
        isOn: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(isOn ? Ink.surface : Ink.primary)
                .frame(width: 30, height: 30)
                .background(
                    Circle()
                        // Erased to one type so the accent fill and the material are the same
                        // expression: `?:` cannot mix `Color` with `Material`.
                        .fill(isOn ? AnyShapeStyle(Ink.accent) : AnyShapeStyle(.regularMaterial))
                        .overlay(Circle().strokeBorder(Ink.hairline, lineWidth: 1)))
        }
        .buttonStyle(.plain)
        // Dimmed rather than removed: unlike "open externally", these features do exist on every
        // frame — the dimming reports state, not absence.
        .opacity(enabled ? 1 : 0.45)
        .help(help)
    }

    // MARK: - The track

    private var track: some View {
        RewindTrack(
            blocks: model.blocks,
            frames: model.frames,
            trackStart: model.trackStart,
            trackSpan: model.trackSpan,
            playheadAt: model.currentFrame?.capturedAt,
            onScrub: { model.scrub(to: $0) },
            onTravel: { model.travel(by: $0) },
            spanBounds: model.trackSpanBounds,
            // A pinch over the track is the second way into the *same* zoom the two magnifier buttons
            // drive: it hands the model a `RewindZoom.Target` and the model's single mutation point
            // does the rest, so the gesture and the buttons cannot get out of step.
            onZoom: { model.setTrackWindow($0) }
        )
        .frame(height: RewindTrackView.height)
        .padding(.horizontal, 18)
        .padding(.top, 4)
        .padding(.bottom, 14)
    }

    /// `⌘ +` / `⌘ −` zoom the **frame image**, which the spec is explicit must not be the same as the
    /// track zoom the buttons drive. Two hidden buttons carry the shortcuts because a `View` cannot
    /// hold a `keyboardShortcut` without something focusable to attach it to.
    private var zoomKeyboardShortcuts: some View {
        Group {
            Button("") { model.zoomImage(in: true) }
                .keyboardShortcut("+", modifiers: [.command])
            Button("") { model.zoomImage(in: false) }
                .keyboardShortcut("-", modifiers: [.command])
            // Left and right arrows step one frame, which is the finest scrub there is.
            Button("") { model.step(-1) }.keyboardShortcut(.leftArrow, modifiers: [])
            Button("") { model.step(1) }.keyboardShortcut(.rightArrow, modifiers: [])
        }
        .opacity(0)
        .frame(width: 0, height: 0)
        .accessibilityHidden(true)
    }
}
