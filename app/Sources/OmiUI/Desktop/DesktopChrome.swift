import OmiKit
import SwiftUI

// Port of `DesktopTopChrome.tsx` (v5.1 chrome) and `DesktopChromeV5.tsx`
// (v5 pages chrome). Row 1 carries the traffic-light spacer + omnibar +
// capture toggle + gear; row 2 (v5.1) carries the Activity filters and the
// Date/Type/Topic grouping. The v5 IA replaces row 2 with the pages rail
// (Home / Chat / Conversations / Recall / Tasks) and drops the omnibar to
// row 2, sharing every control.

/// Omnibar mode: Search (not Recall) — `OmnibarMode`.
public enum OmnibarMode: String, Sendable {
    case ask = "Ask"
    case search = "Search"
}

/// Desktop stage destinations behind the chrome: Home is the Activity page,
/// Rewind is the capture-detail page, Chat is an overlay (never a route).
public enum DesktopRoute: String, Sendable, Hashable {
    case home = "Home"
    case rewind = "Rewind"
    case settings = "Settings"

    /// The v5 pages rail ids (DesktopChromeV5 `desktopNavItemsV5`).
    public static let v5Rail: [String] = [
        "Home", "Chat", "Conversations", "Rewind", "Tasks",
    ]
}

// MARK: - Row 1: omnibar row

struct DesktopOmnibarRow: View {
    @ObservedObject var store: AppStore
    let mode: OmnibarMode
    let onModeChange: (OmnibarMode) -> Void
    let onSend: () -> Void
    let onStop: () -> Void
    let route: DesktopRoute
    let onNavigate: (DesktopRoute) -> Void
    /// Chat overlay busy/streaming — enables Stop during Ask.
    let chatBusy: Bool
    let captureActive: Bool
    let captureAvailable: Bool
    let onToggleCapture: (() -> Void)?

    @Environment(\.desktopTokens) private var tokens
    @FocusState private var omnibarFocused: Bool

    var body: some View {
        HStack(spacing: 10) {
            // Window-controls spacer: the reserved 12/44 traffic-light slot.
            // The host centers the native lights on this 44 pt row; on
            // non-macOS hosts the virtual dots render here instead.
            DesktopTrafficLights()
                .frame(
                    width: DesktopLayout.trafficLightRowWidth,
                    height: DesktopLayout.trafficLightButton
                )

            omnibar

            if captureAvailable, let onToggleCapture {
                ChromeIconButton(
                    label: captureActive ? "Stop screen capture" : "Start screen capture",
                    active: captureActive
                ) {
                    DesktopIcon.monitor
                        .frame(width: 17, height: 17)
                        .foregroundStyle(captureActive ? tokens.red : tokens.ink)
                }
                .onTapGesture(perform: onToggleCapture)
            }

            ChromeIconButton(label: "Settings", active: route == DesktopRoute.settings) {
                DesktopIcon.gear
                    .frame(width: 17, height: 17)
                    .foregroundStyle(tokens.ink)
            }
            .onTapGesture {
                // The gear toggles: it opens Settings and also walks back Home.
                onNavigate(route == DesktopRoute.settings ? DesktopRoute.home : DesktopRoute.settings)
            }
        }
        .frame(height: DesktopLayout.omnibarHeight)
        .accessibilityLabel("Omi desktop chrome")
    }

    private var canStop: Bool {
        mode == OmnibarMode.ask && chatBusy
    }

    private var omnibar: some View {
        HStack(spacing: 8) {
            modeSwitcher
            TextField(
                mode == OmnibarMode.search ? desktopSearchPlaceholder : "Ask about your day…",
                text: Binding(
                    get: { store.searchQuery },
                    set: { store.searchQuery = $0 }
                )
            )
            .textFieldStyle(.plain)
            .font(.system(size: 15))
            .foregroundStyle(tokens.ink)
            .focused($omnibarFocused)
            .onSubmit {
                if mode != OmnibarMode.ask || !store.composerText.trimmingCharacters(in: .whitespaces).isEmpty {
                    onSend()
                }
            }
            .frame(height: 32)
            .accessibilityLabel(mode == OmnibarMode.ask ? "Ask Omi" : "Search Recall")

            sendButton
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .frame(
            maxWidth: DesktopLayout.stageMaxWidth,
            minHeight: DesktopLayout.omnibarHeight
        )
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(tokens.glassStrong)
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .strokeBorder(tokens.line, lineWidth: 1)
                )
        )
    }

    /// Sliding Ask/Search mode pill (Animated pill with navMs smooth-out).
    @ViewBuilder
    private var modeSwitcher: some View {
        HStack(spacing: 2) {
            modeButton(OmnibarMode.ask, icon: DesktopIcon.chatBubble)
            modeButton(OmnibarMode.search, icon: DesktopIcon.search)
        }
    }

    private func modeButton(_ value: OmnibarMode, icon: DesktopIcon) -> some View {
        let selected = mode == value
        return Button {
            onModeChange(value)
        } label: {
            HStack(spacing: 6) {
                icon
                    .frame(width: 15, height: 15)
                    .foregroundStyle(selected ? tokens.ink : tokens.inkMuted)
                Text(value.rawValue)
                    .font(.system(size: 12, weight: selected ? .semibold : .regular))
                    .foregroundStyle(selected ? tokens.ink : tokens.inkMuted)
            }
            .padding(.horizontal, 10)
            .frame(height: 32)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(selected ? tokens.glassSelected : Color.clear)
            )
        }
        .buttonStyle(GlassPressableStyle())
        .animation(DesktopMotion.navAnimation(reduceMotion), value: mode)
        .accessibilityLabel("Use \(value.rawValue) mode")
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var sendButton: some View {
        let emptyAsk = mode == OmnibarMode.ask
            && store.searchQuery.trimmingCharacters(in: .whitespaces).isEmpty
            && store.composerText.trimmingCharacters(in: .whitespaces).isEmpty
        return Button {
            if canStop {
                onStop()
            } else {
                onSend()
            }
        } label: {
            ZStack {
                Circle().fill(tokens.ink)
                if canStop {
                    DesktopIcon.stop
                        .frame(width: 14, height: 14)
                        .foregroundStyle(tokens.surfaceInk)
                } else if mode == OmnibarMode.ask {
                    DesktopIcon.arrowUp
                        .frame(width: 18, height: 18)
                        .foregroundStyle(tokens.surfaceInk)
                } else {
                    DesktopIcon.search
                        .frame(width: 17, height: 17)
                        .foregroundStyle(tokens.surfaceInk)
                }
            }
            .frame(width: 32, height: 32)
            .opacity((canStop || mode == OmnibarMode.search || !emptyAsk) ? 1 : 0.3)
        }
        .buttonStyle(GlassPressableStyle())
        .disabled(mode == OmnibarMode.ask && !canStop && emptyAsk)
        .animation(DesktopMotion.pressAnimation(reduceMotion), value: canStop)
        .accessibilityLabel(
            canStop ? "Stop" : (mode == OmnibarMode.ask ? "Send" : "Search")
        )
    }
}

/// 34 pt circular icon button used for capture + settings; active shows the
/// selected glass fill + hairline border (`settingsButtonActive`).
struct ChromeIconButton<Icon: View>: View {
    let label: String
    var active = false
    @ViewBuilder let icon: () -> Icon

    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        Button(action: {}) {
            icon()
                .frame(width: 34, height: 34)
                .background(
                    Circle().fill(active ? tokens.glassSelected : Color.clear)
                )
                .overlay(
                    Circle().strokeBorder(active ? tokens.line : Color.clear, lineWidth: 1)
                )
        }
        .buttonStyle(GlassPressableStyle())
        .accessibilityLabel(label)
        .accessibilityAddTraits(active ? .isSelected : [])
    }
}

// MARK: - Row 2 (v5.1): Activity filters + grouping

struct DesktopFilterRow: View {
    let filter: TimelineFilter
    let onFilterChange: (TimelineFilter) -> Void
    let groupBy: TimelineGrouping
    let onGroupByChange: (TimelineGrouping) -> Void

    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        HStack(spacing: 6) {
            ForEach(TimelineFilter.allCases, id: \.self) { candidate in
                let selected = candidate == filter
                Button {
                    onFilterChange(candidate)
                } label: {
                    HStack(spacing: 7) {
                        filterIcon(candidate)
                            .frame(width: 14, height: 14)
                            .foregroundStyle(selected ? tokens.ink : tokens.inkMuted)
                        Text(candidate.label)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(selected ? tokens.ink : tokens.inkMuted)
                    }
                    .padding(.horizontal, 12)
                    .frame(height: 30)
                    .background(
                        Capsule().fill(selected ? tokens.glassSelected : Color.clear)
                    )
                }
                .buttonStyle(GlassPressableStyle())
                .accessibilityLabel("Filter \(candidate.label)")
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
            Spacer(minLength: 0)
            DesktopSegmented(
                options: TimelineGrouping.allCases,
                label: { $0.label },
                selection: groupBy,
                onChange: onGroupByChange
            )
            .accessibilityLabel("Timeline grouping")
        }
        .frame(height: DesktopLayout.filterRowHeight)
        .frame(maxWidth: DesktopLayout.stageMaxWidth)
        .accessibilityLabel("Activity filters")
    }

    @ViewBuilder
    private func filterIcon(_ filter: TimelineFilter) -> some View {
        switch filter {
        case TimelineFilter.all: DesktopIcon.timeline
        case TimelineFilter.conversations: DesktopIcon.chatBubble
        case TimelineFilter.recall: DesktopIcon.history
        case TimelineFilter.tasks: DesktopIcon.checklist
        }
    }
}

// MARK: - Row 2 (v5): pages rail

/// The v5 pages rail: Home / Chat / Conversations / Recall / Tasks with the
/// sliding selection pill (`DesktopChromeV5`). Chat opens the overlay, not a
/// stage route; Conversations and Tasks open the v5 pages.
struct DesktopRailRow: View {
    let activeId: String?
    let onNavigate: (String) -> Void

    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        HStack(spacing: 4) {
            ForEach(DesktopRoute.v5Rail, id: \.self) { id in
                railButton(id)
            }
        }
        .frame(height: DesktopLayout.omnibarHeight)
        .accessibilityLabel("Omi desktop navigation")
    }

    private func railButton(_ id: String) -> some View {
        let label = id == "Rewind" ? "Recall" : id
        let active = activeId == id
        return Button {
            onNavigate(id)
        } label: {
            HStack(spacing: 7) {
                railIcon(id)
                    .frame(width: 14, height: 14)
                    .foregroundStyle(tokens.ink)
                Text(label)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(active ? tokens.ink : tokens.inkMuted)
            }
            .padding(.horizontal, 10)
            .frame(height: 40)
            .background(
                RoundedRectangle(cornerRadius: 14)
                    .fill(active ? tokens.glassSelected : Color.clear)
            )
        }
        .buttonStyle(GlassPressableStyle())
        .animation(DesktopMotion.navAnimation(reduceMotionEnvironment), value: activeId)
        .accessibilityLabel(label)
        .accessibilityAddTraits(active ? .isSelected : [])
    }

    @Environment(\.accessibilityReduceMotion) private var reduceMotionEnvironment

    @ViewBuilder
    private func railIcon(_ id: String) -> some View {
        switch id {
        case "Home": DesktopIcon.home
        case "Chat": DesktopIcon.chatBubble
        case "Conversations": DesktopIcon.chatBubble
        case "Rewind": DesktopIcon.history
        default: DesktopIcon.checklist
        }
    }
}
