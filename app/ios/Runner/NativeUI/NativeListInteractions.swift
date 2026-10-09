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

/// A selectable row shows its selection by the accent checkmark alone, as Mail and Photos do: the plain
/// cell background replaces the system's grey selected fill, and the row's own content stays monochrome.
@available(iOS 16.0, *)
struct NativeSelectableRow: ViewModifier {
    let selectable: Bool

    @ViewBuilder func body(content: Content) -> some View {
        if selectable {
            content.listRowBackground(Color(uiColor: .secondarySystemGroupedBackground))
        } else { content }
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
                // One glyph that turns, pointing down to expand and up to collapse; symmetric in RTL.
                Image(systemName: "chevron.down")
                    .font(.caption.weight(.semibold))
                    .rotationEffect(.degrees(collapsed ? 0 : 180))
                    .accessibilityHidden(true)
            }.frame(minHeight: NativeMetrics.rowHeight).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(.isHeader)
        .accessibilityHint(collapsed ? expandLabel : collapseLabel)
    }
}

/// A dashboard section title with a trailing action such as "View All". Home's recaps and conversations
/// share it; date groups and surface sections keep the system header.
@available(iOS 16.0, *)
struct NativeSectionHeader<Trailing: View>: View {
    let title: String
    @ViewBuilder let trailing: () -> Trailing

    var body: some View {
        // Large text stacks the action under the title instead of breaking the title mid-word.
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .center, spacing: 8) {
                titleText
                Spacer(minLength: 8)
                trailing()
            }
            VStack(alignment: .leading, spacing: 2) {
                titleText
                trailing()
            }
        }
        .frame(maxWidth: .infinity, minHeight: NativeMetrics.rowHeight, alignment: .leading)
        .textCase(nil)
        .contentShape(Rectangle())
    }

    /// A Color, not the hierarchical style, which a list header maps to its secondary grey.
    private var titleText: some View {
        Text(title).font(.title3.weight(.semibold)).foregroundStyle(Color.primary)
    }
}

/// The trailing action of a section header. The chevron is decoration; the label is the title alone.
@available(iOS 16.0, *)
struct NativeSectionAction: View {
    let title: String

    var body: some View {
        HStack(spacing: 3) {
            Text(title)
            Image(systemName: "chevron.forward").imageScale(.small).accessibilityHidden(true)
        }
        .font(.subheadline.weight(.medium))
        .foregroundStyle(Color.secondary)
        .textCase(nil)
    }
}

/// Snapshot copy for a list with nothing to show, centred with a symbol like the system's empty states.
/// The title keeps the caller's accessibility identifier.
@available(iOS 16.0, *)
struct NativeEmptyState: View {
    let title: String
    let symbol: String
    var identifier: String?

    var body: some View {
        if #available(iOS 17.0, *) {
            ContentUnavailableView {
                Label { titleText } icon: { Image(systemName: symbol) }
            }
        } else {
            VStack(spacing: 12) {
                Image(systemName: symbol).font(.system(size: 44)).foregroundStyle(.secondary)
                    .accessibilityHidden(true)
                titleText.font(.title3.weight(.semibold))
            }
            .multilineTextAlignment(.center)
            .padding(.horizontal, 32).padding(.vertical, 40)
            .frame(maxWidth: .infinity)
        }
    }

    @ViewBuilder private var titleText: some View {
        if let identifier { Text(title).accessibilityIdentifier(identifier) } else { Text(title) }
    }
}

/// A short status tag ("NEW", "BETA") drawn as a small tinted capsule. Only a subtitle that is already such
/// a tag becomes one, so ordinary subtitles and translations without letter case stay plain text.
@available(iOS 16.0, *)
struct NativeBadge: View {
    let text: String

    static func accepts(_ text: String) -> Bool {
        (1...6).contains(text.count) && !text.contains(where: \.isWhitespace)
            && text.contains(where: \.isUppercase) && !text.contains(where: \.isLowercase)
    }

    var body: some View {
        Text(text)
            .font(.caption2.weight(.bold))
            .foregroundStyle(NativeMetrics.accent)
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(NativeMetrics.accent.opacity(0.16), in: Capsule())
            .fixedSize()
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
