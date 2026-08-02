import AppKit
import ContextCore
import SwiftUI

/// Appearance: theme, dock icon — then the Timeline section with a live preview above the four
/// control toggles.
///
/// **System is the default and means "follow the system".** Phase 0 of `docs/first-run-experience.md`
/// deleted a forced `NSApp.appearance = .aqua` precisely because pinning the process rendered a light
/// popover inside a dark system menu. This pane does not undo that: `System` installs no appearance at
/// all, and Light/Dark are explicit overrides of it.
///
/// **There is no accent row.** It only ever reached `.tint()` on this one window, so it recoloured the
/// switches on this pane and nothing else — every structural accent in the app reads `Ink.accent` — and
/// its default resolved to the machine's `controlAccentColor`, which paints the window purple on a Mac
/// set to Purple. That is `INV-UI-1` (`docs/product/invariants/brand-ui.md`) violated by the default
/// value of a control that did nothing, so the control is gone rather than narrowed.
struct SettingsAppearancePane: View {
    @ObservedObject var store: SettingsStore

    var body: some View {
        SettingsPaneScroll {
            SettingsSection(title: "Appearance") {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Choose app theme")
                        .font(.system(size: 11))
                        .foregroundStyle(Ink.secondary)
                    HStack(spacing: 10) {
                        ForEach(AppearanceOverride.allCases) { option in
                            SettingsTile(isSelected: store.appearance == option) {
                                Sound.effect(.click)
                                store.appearance = option
                            } content: {
                                AppearanceTilePreview(option: option, title: option.title)
                            }
                        }
                    }
                }
                .padding(12)

                SettingsRowDivider()

                SettingsRow(
                    icon: "dock.rectangle",
                    title: "Show Dock Icon",
                    subtitle: "Keeps the app's icon visible in the Dock during normal use."
                ) {
                    Toggle("", isOn: $store.showsDockIcon)
                        .labelsHidden()
                        .toggleStyle(.switch)
                        .controlSize(.small)
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Timeline")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Ink.secondary)
                    .padding(.horizontal, 4)
                Text(
                    "Choose which controls appear over the timeline. Their keyboard shortcuts keep "
                        + "working even when a control is hidden."
                )
                .font(.system(size: 11))
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 4)

                TimelinePreview(controls: store.timelineControls)
            }

            SettingsSection {
                SettingsRowStack(items: TimelineControlVisibility.Control.allCases) { control in
                    SettingsRow(
                        icon: control.previewSymbol,
                        title: control.title,
                        subtitle: control.subtitle,
                        shortcutHint: control.shortcutHint
                    ) {
                        Toggle(
                            "",
                            isOn: Binding(
                                get: { store.timelineControls[control] },
                                set: { value in
                                    Sound.effect(.click)
                                    var next = store.timelineControls
                                    next[control] = value
                                    store.timelineControls = next
                                })
                        )
                        .labelsHidden()
                        .toggleStyle(.switch)
                        .controlSize(.small)
                    }
                }
            }
        }
    }
}

/// One of the three theme tiles: a miniature window drawn in that appearance, with its name beneath.
///
/// The miniatures are drawn inside an `.environment(\.colorScheme)` for the option they represent, so
/// the Light tile really is light while the app is in Dark. The System tile is split down the middle,
/// which is the only honest way to draw "whatever the system says".
struct AppearanceTilePreview: View {
    let option: AppearanceOverride
    let title: String

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                switch option {
                case .system:
                    HStack(spacing: 0) {
                        miniature(.light).clipShape(Rectangle()).frame(width: 26)
                        miniature(.dark).clipShape(Rectangle()).frame(width: 26)
                    }
                case .light:
                    miniature(.light)
                case .dark:
                    miniature(.dark)
                }
            }
            .frame(width: 52, height: 34)
            .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .strokeBorder(Ink.separator, lineWidth: 1))

            Text(title)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(Ink.primary)
        }
    }

    private func miniature(_ scheme: ColorScheme) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            RoundedRectangle(cornerRadius: 1)
                .fill(Color(nsColor: .labelColor).opacity(0.55))
                .frame(width: 22, height: 3)
            RoundedRectangle(cornerRadius: 1)
                .fill(Color(nsColor: .labelColor).opacity(0.28))
                .frame(width: 34, height: 3)
            RoundedRectangle(cornerRadius: 2)
                .fill(Ink.accent.opacity(0.8))
                .frame(width: 16, height: 5)
        }
        .padding(6)
        .frame(width: 52, height: 34, alignment: .topLeading)
        .background(Color(nsColor: .controlBackgroundColor))
        .environment(\.colorScheme, scheme)
    }
}

/// The live preview of the timeline window, reflecting the four toggles beneath it in real time.
///
/// It draws the **real** `RewindTrack` — the same `NSViewRepresentable` the timeline window uses — over
/// synthetic blocks and frames, so the coloured segments, the app-icon badges and the hour ticks are
/// produced by the shipping code rather than by a drawing that resembles it. That is the whole reason
/// it is a faithful preview and not a picture of one: if the track's rendering changes, this changes
/// with it. `Rewind/*` is untouched.
///
/// The frame stage, the date pill and the control cluster are laid out here rather than reused, because
/// `RewindView` is bound to a `RewindModel` that opens the database and loads a real day — hosting it
/// in a settings pane would open a second reader and show the user's actual screen inside a preview
/// tile. The copy, the symbols, the order and the metrics are all taken from `RewindView`.
struct TimelinePreview: View {
    let controls: TimelineControlVisibility

    /// A fixed, obviously-sample instant. Not `Date()`: a preview that quietly showed the current time
    /// would read as live data about the user's day when it is a mock-up of the chrome.
    private static let sampleStart: Double = {
        var components = DateComponents()
        components.year = 2026
        components.month = 7
        components.day = 29
        components.hour = 9
        components.minute = 0
        return Calendar(identifier: .gregorian).date(from: components)?.timeIntervalSince1970
            ?? 1_785_000_000
    }()

    private static let sampleSpan: Double = 12 * 3600

    /// Real apps, so the derived segment colours are the ones the user will actually see.
    ///
    /// Chosen for the *hues* `RewindPalette` gives them, not arbitrarily: these eight sweep 0.9° →
    /// 186°, so the strip reads red → orange → yellow → green → teal → blue rather than clustering
    /// into one colour. `SettingsTests` pins the sweep, because it is a property of these names and
    /// nothing else enforces it.
    ///
    /// A first draft used Terminal, Figma and iTerm2, which under the palette's old 250° arc landed
    /// at 228°, 244° and 244° and rendered visibly violet segments — exactly what a settings pane
    /// must not show off under `INV-UI-1`. That cannot recur from this side: the arc now stops at
    /// 220°, and `RewindTests` proves on the rendered pixel that no colour the palette can emit reads
    /// violet. Under today's arc those three are 200°, 215° and 215°.
    static let sampleApps = [
        "Notes", "Photos", "Warp", "Messages", "Finder", "Arc", "Cursor", "Xcode",
    ]

    private static let blocks: [ActivityBlock] = {
        var blocks: [ActivityBlock] = []
        var cursor = sampleStart
        for (index, app) in sampleApps.enumerated() {
            let length = Double(30 + (index * 17) % 70) * 60
            blocks.append(
                ActivityBlock(
                    app: app, window: nil, startedAt: cursor, endedAt: cursor + length,
                    sampleText: nil))
            cursor += length + Double(4 + index) * 60
        }
        return blocks
    }()

    private static let frames: [RewindFrame] = blocks.enumerated().flatMap { index, block -> [RewindFrame] in
        stride(from: block.startedAt, to: block.endedAt, by: 300).enumerated().map { step, instant in
            RewindFrame(
                id: Int64(index * 1000 + step),
                capturedAt: instant,
                appName: block.app,
                bundleId: nil,
                windowTitle: nil,
                ocrText: nil,
                imagePath: "/preview")
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            stage
            RewindTrack(
                blocks: Self.blocks,
                frames: Self.frames,
                trackStart: Self.sampleStart,
                trackSpan: Self.sampleSpan,
                playheadAt: Self.sampleStart + Self.sampleSpan * 0.42,
                // Inert: this is a preview of the chrome, and a preview that scrubbed would be a
                // second, silent timeline.
                onScrub: { _ in },
                onTravel: { _ in }
            )
            .frame(height: RewindTrackView.height)
            .padding(.horizontal, 10)
            .padding(.bottom, 8)
            .allowsHitTesting(false)
        }
        .background(Ink.surface)
        .clipShape(RoundedRectangle(cornerRadius: SettingsMetrics.cardRadius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: SettingsMetrics.cardRadius, style: .continuous)
                .strokeBorder(Ink.separator, lineWidth: 1)
        )
        .accessibilityLabel(Text("Timeline preview"))
        .accessibilityValue(
            Text(
                controls.visible.isEmpty
                    ? "No controls shown"
                    : controls.visible.map(\.title).joined(separator: ", ")))
    }

    private var header: some View {
        ZStack {
            Text(RewindView.modeTitle)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(Ink.primary)
            HStack(spacing: 5) {
                HStack(spacing: 4) {
                    Image(systemName: "magnifyingglass").font(.system(size: 8, weight: .semibold))
                    Text("Search All").font(.system(size: 9, weight: .medium))
                }
                .foregroundStyle(Ink.primary)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(Capsule().fill(Ink.rowFill))
                Spacer(minLength: 0)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .overlay(alignment: .bottom) { Divider() }
    }

    /// The frame area: a wash standing in for a screenshot, the segment chevrons on its edges, the date
    /// pill bottom-left and the circular controls bottom-right — every one of them appearing only when
    /// its toggle is on.
    private var stage: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(Ink.wash)
                .overlay(
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .strokeBorder(RewindPalette.color(forApp: Self.sampleApps[6]), lineWidth: 1.5))

            // Says what the empty rectangle is. Without it a blank frame reads as a picture that failed
            // to load, and the one thing this tile must not do is look broken.
            Text("Preview")
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(Ink.secondary)

            if controls.segmentNavigation {
                HStack {
                    chevron("chevron.left")
                    Spacer(minLength: 0)
                    chevron("chevron.right")
                }
                .padding(.horizontal, 5)
            }

            VStack {
                Spacer(minLength: 0)
                HStack(alignment: .bottom, spacing: 6) {
                    datePill
                    Spacer(minLength: 0)
                    HStack(spacing: 5) {
                        if controls.openExternally { circle("globe") }
                        if controls.liveText { circle("text.viewfinder") }
                        if controls.zoomControls {
                            circle("minus.magnifyingglass")
                            circle("plus.magnifyingglass")
                        }
                    }
                }
                .padding(8)
            }
        }
        .frame(height: 116)
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
    }

    private var datePill: some View {
        HStack(spacing: 4) {
            Image(systemName: "calendar").font(.system(size: 8, weight: .medium))
            Text("Jul 29, 2026 at 10:21 PM").font(.system(size: 9, weight: .medium))
            Image(systemName: "chevron.down").font(.system(size: 6, weight: .bold))
                .foregroundStyle(Ink.secondary)
        }
        .foregroundStyle(Ink.primary)
        .padding(.horizontal, 7)
        .padding(.vertical, 4)
        .background(
            Capsule().fill(.regularMaterial)
                .overlay(Capsule().strokeBorder(Ink.hairline, lineWidth: 1)))
    }

    private func chevron(_ symbol: String) -> some View {
        Image(systemName: symbol)
            .font(.system(size: 9, weight: .semibold))
            .foregroundStyle(Ink.primary)
            .frame(width: 18, height: 28)
            .background(
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .fill(Ink.rowFill)
                    .overlay(
                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                            .strokeBorder(Ink.hairline, lineWidth: 1)))
    }

    private func circle(_ symbol: String) -> some View {
        Image(systemName: symbol)
            .font(.system(size: 9, weight: .medium))
            .foregroundStyle(Ink.primary)
            .frame(width: 21, height: 21)
            .background(
                Circle().fill(.regularMaterial)
                    .overlay(Circle().strokeBorder(Ink.hairline, lineWidth: 1)))
    }
}
