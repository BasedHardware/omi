import SwiftUI

// List interactions render in list mode only, never in reader or chat. Selection, order, swipe and
// bottom-bar commands return to the existing Dart owner; collapsing a section is presentation only.

/// Hierarchy depth with a quiet rule; the rule overlays the row, so its height is unchanged.
@available(iOS 16.0, *)
struct NativeIndent: ViewModifier {
    let level: Int

    @ViewBuilder func body(content: Content) -> some View {
        if level > 0 {
            content.padding(.leading, CGFloat(level) * 20)
                .overlay(alignment: .leading) {
                    Capsule().fill(.quaternary).frame(width: 1.5)
                        .padding(.vertical, 2)
                        .padding(.leading, CGFloat(level) * 20 - 10)
                        .accessibilityHidden(true)
                }
        } else { content }
    }
}

/// Swipe actions repeat options of the row's context menu and send the same option id.
@available(iOS 16.0, *)
struct NativeSwipeActions: ViewModifier {
    let row: NativeSurfaceRow
    let enabled: Bool
    let send: (String) -> Void

    @ViewBuilder func body(content: Content) -> some View {
        if enabled && (!(row.swipeLeading ?? []).isEmpty || !(row.swipeTrailing ?? []).isEmpty) {
            content
                .swipeActions(edge: .leading, allowsFullSwipe: true) { buttons(row.swipeLeading ?? []) }
                .swipeActions(edge: .trailing, allowsFullSwipe: true) { buttons(row.swipeTrailing ?? []) }
        } else { content }
    }

    private func buttons(_ ids: [String]) -> some View {
        ForEach(ids.compactMap { id in row.options.first { $0.id == id } }) { option in
            Button(role: option.id == "delete" ? .destructive : nil) { send(option.id) } label: {
                if let symbol = Self.symbol(option.id) { Label(option.title, systemImage: symbol) }
                else { Text(option.title) }
            }
            .tint(Self.tint(option.id))
            .accessibilityIdentifier("\(row.id)_swipe_\(option.id)")
        }
    }

    /// Only well-known option ids carry a symbol; anything else shows its title alone.
    static func symbol(_ id: String) -> String? {
        switch id {
        case "delete": return "trash"
        case "complete": return "checkmark.circle"
        case "reopen": return "arrow.uturn.backward.circle"
        case "pin": return "pin"
        case "unpin": return "pin.slash"
        case "star": return "star"
        case "unstar": return "star.slash"
        case "review_right": return "hand.thumbsup"
        case "review_wrong": return "hand.thumbsdown"
        default: return nil
        }
    }

    private static func tint(_ id: String) -> Color {
        switch id {
        case "delete": return .red
        case "complete", "review_right": return .green
        case "reopen": return .blue
        case "pin", "unpin", "review_wrong": return .orange
        case "star", "unstar": return .yellow
        default: return .gray
        }
    }
}

/// A row that is not selectable keeps its own control while the list selects.
@available(iOS 16.0, *)
struct NativeSelectionDisabled: ViewModifier {
    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 17.0, *) { content.selectionDisabled(true) }
        else { content.disabled(true) }
    }
}

/// A titled section header that expands and collapses its rows locally.
@available(iOS 16.0, *)
struct NativeCollapsibleHeader: View {
    let title: String
    let collapsed: Bool
    let expandLabel: String
    let collapseLabel: String
    let toggle: () -> Void

    var body: some View {
        Button(action: toggle) {
            HStack(spacing: 8) {
                Text(title)
                Spacer(minLength: 8)
                Image(systemName: collapsed ? "chevron.down" : "chevron.up")
                    .font(.caption.weight(.semibold)).accessibilityHidden(true)
            }.frame(minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(.isHeader)
        .accessibilityHint(collapsed ? expandLabel : collapseLabel)
    }
}

/// Actions for the current selection (or list), pinned above the bottom safe area and any tab bar.
/// Large text moves the buttons below the label instead of truncating them.
@available(iOS 16.0, *)
struct NativeBottomBar<Caption: View, Buttons: View>: View {
    @ViewBuilder let label: () -> Caption
    @ViewBuilder let buttons: () -> Buttons

    var body: some View {
        NativeGlassControls {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) { label(); Spacer(minLength: 8); buttons() }
                VStack(alignment: .leading, spacing: 8) { label(); HStack(spacing: 12) { buttons() } }
                VStack(alignment: .leading, spacing: 8) { label(); buttons() }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity)
        .background(.bar)
    }
}
