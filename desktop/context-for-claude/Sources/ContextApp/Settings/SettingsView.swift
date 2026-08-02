import AppKit
import ContextCore
import SwiftUI

/// The six panes, in sidebar order.
enum SettingsPane: String, CaseIterable, Identifiable, Sendable {
    case general
    case agents
    case appearance
    case capture
    case storage
    case exclusions

    var id: String { rawValue }

    var title: String {
        switch self {
        case .general: "General"
        case .agents: "Agents"
        case .appearance: "Appearance"
        case .capture: "Capture"
        case .storage: "Storage"
        case .exclusions: "Exclusions"
        }
    }

    /// The symbols named in `docs/rewind-and-settings.md` § Part 2.
    var symbol: String {
        switch self {
        case .general: "gearshape"
        case .agents: "terminal"
        case .appearance: "circle.lefthalf.filled"
        case .capture: "record.circle"
        case .storage: "internaldrive"
        case .exclusions: "eye.slash"
        }
    }
}

/// Which pane is showing.
///
/// An object rather than `@State` so `SettingsWindow.present(pane:)` can move an already-open window to
/// a pane — with `@State` the caller would have no way to reach it, and a second window would be the
/// only way to land somewhere specific.
@MainActor
final class SettingsSelection: ObservableObject {
    @Published var pane: SettingsPane

    init(pane: SettingsPane = .general) {
        self.pane = pane
    }
}

/// The settings window's content: a sidebar with rounded selection, a header reading "Settings" with
/// the current pane name beneath it, and the pane.
struct SettingsView: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var exclusions: ExclusionsObserver
    let shortcuts: ShortcutBindingProvider
    @ObservedObject var selection: SettingsSelection

    private var pane: SettingsPane { selection.pane }

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider()
            VStack(alignment: .leading, spacing: 0) {
                header
                Divider()
                paneContent
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .background(Ink.surface)
        // The accent choice takes effect the moment it is picked, everywhere in this window: toggles,
        // radio fills, the selected-tile ring and the preview all read `.tint`.
        .tint(store.accentColor)
        .frame(minWidth: SettingsMetrics.minimumSize.width, minHeight: SettingsMetrics.minimumSize.height)
    }

    // MARK: - Sidebar

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(SettingsPane.allCases) { item in
                SettingsSidebarRow(pane: item, isSelected: pane == item) {
                    guard pane != item else { return }
                    Sound.effect(.click)
                    selection.pane = item
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 8)
        .padding(.top, 14)
        .frame(width: SettingsMetrics.sidebarWidth)
        .background(.regularMaterial)
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("Settings")
                .font(.openRunde(17, .semiBold))
                .foregroundStyle(Ink.primary)
            Text(pane.title)
                .font(.system(size: 11))
                .foregroundStyle(Ink.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, SettingsMetrics.paneHorizontalPadding)
        .padding(.top, 10)
        .padding(.bottom, 12)
    }

    @ViewBuilder
    private var paneContent: some View {
        switch pane {
        case .general:
            SettingsGeneralPane(store: store, shortcuts: shortcuts, exclusions: exclusions)
        case .agents:
            SettingsAgentsPane(store: store)
        case .appearance:
            SettingsAppearancePane(store: store)
        case .capture:
            SettingsCapturePane(store: store)
        case .storage:
            SettingsStoragePane(store: store)
        case .exclusions:
            // Owns its own chrome (segmented control, search field) above a scroll view, so it is not
            // wrapped in the shared one.
            SettingsExclusionsPane(exclusions: exclusions)
        }
    }
}

struct SettingsSidebarRow: View {
    let pane: SettingsPane
    let isSelected: Bool
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: pane.symbol)
                    .font(.system(size: 12, weight: .medium))
                    .frame(width: 16)
                Text(pane.title)
                    .font(.system(size: 13))
                Spacer(minLength: 0)
            }
            .foregroundStyle(isSelected ? Ink.surface : Ink.primary)
            .padding(.horizontal, 9)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(
                        isSelected
                            ? AnyShapeStyle(Ink.accent)
                            : AnyShapeStyle(isHovering ? Ink.rowHover : Color.clear))
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityAddTraits(isSelected ? [.isSelected, .isButton] : .isButton)
    }
}

/// The scroll container every pane except Exclusions uses, so their paddings cannot drift apart.
struct SettingsPaneScroll<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: SettingsMetrics.sectionSpacing) {
                content()
            }
            .padding(.horizontal, SettingsMetrics.paneHorizontalPadding)
            .padding(.top, SettingsMetrics.paneTopPadding)
            .padding(.bottom, 26)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
