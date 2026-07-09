import OmiTheme
import SwiftUI

/// Shared metrics for list-page header rows (Conversations, Tasks,
/// Memories): one control height, one shape family (capsule / circle), one
/// fill, and one active treatment — replacing the per-page mix of radius-8
/// squares, 42pt white squares, and assorted chip heights.
enum OmiHeader {
    static let controlHeight: CGFloat = 36
    static let controlSpacing: CGFloat = 8
    static let rowHorizontalPadding: CGFloat = 24
    static let rowTopPadding: CGFloat = 14
    static let rowBottomPadding: CGFloat = 12

    static let fill = OmiColors.backgroundSecondary
    static let stroke = OmiColors.border.opacity(0.18)
    static let activeFill = OmiColors.backgroundRaised
    static let activeStroke = OmiColors.border.opacity(0.6)
}

extension View {
    /// Standard capsule surface for a header control. Content supplies its
    /// own glyphs/text; this fixes the height, padding, fill, and stroke so
    /// every control in a header row reads as one family.
    func omiHeaderControl(isActive: Bool = false) -> some View {
        padding(.horizontal, 14)
            .frame(height: OmiHeader.controlHeight)
            .background(
                Capsule(style: .continuous)
                    .fill(isActive ? OmiHeader.activeFill : OmiHeader.fill)
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(isActive ? OmiHeader.activeStroke : OmiHeader.stroke, lineWidth: 1)
            )
    }
}

/// Capsule search field shared by every list page header.
struct OmiSearchField: View {
    let placeholder: String
    @Binding var text: String
    var isBusy: Bool = false
    /// Custom clear behavior (e.g. cancel an in-flight search); defaults to
    /// emptying the bound text.
    var onClear: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: 8) {
            if isBusy {
                ProgressView()
                    .scaleEffect(0.6)
                    .frame(width: 14, height: 14)
            } else {
                Image(systemName: "magnifyingglass")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textTertiary)
            }

            TextField(placeholder, text: $text)
                .textFieldStyle(.plain)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textPrimary)

            if !text.isEmpty {
                Button {
                    if let onClear {
                        onClear()
                    } else {
                        text = ""
                    }
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
        }
        .omiHeaderControl()
    }
}

/// Circular icon button for header rows. All header actions render at the
/// same quiet weight — native macOS header rows don't shout any single
/// action with an accent fill.
struct OmiHeaderIconButton: View {
    let systemImage: String
    var isActive: Bool = false
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(
                    isActive || isHovering ? OmiColors.textPrimary : OmiColors.textSecondary
                )
                .frame(width: OmiHeader.controlHeight, height: OmiHeader.controlHeight)
                .background(Circle().fill(isActive ? OmiHeader.activeFill : OmiHeader.fill))
                .overlay(
                    Circle().stroke(
                        isActive ? OmiHeader.activeStroke : OmiHeader.stroke, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }
}

/// Label content for a capsule chip: optional glyph + title + optional
/// chevron. Usable directly as a `Menu` label; `OmiHeaderChip` wraps it in a
/// button.
struct OmiHeaderChipLabel: View {
    var systemImage: String? = nil
    let title: String
    var isActive: Bool = false
    var showsChevron: Bool = false
    /// Semantic tint for the glyph in the active state (e.g. amber star);
    /// chrome stays neutral.
    var activeGlyphTint: Color? = nil

    var body: some View {
        HStack(spacing: 6) {
            if let systemImage {
                Image(systemName: systemImage)
                    .scaledFont(size: 12)
                    .foregroundColor(isActive ? (activeGlyphTint ?? OmiColors.textPrimary) : OmiColors.textSecondary)
            }
            Text(title)
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(isActive ? OmiColors.textPrimary : OmiColors.textSecondary)
            if showsChevron {
                Image(systemName: "chevron.down")
                    .scaledFont(size: 10)
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .omiHeaderControl(isActive: isActive)
    }
}

/// Capsule chip button for header filter/action rows.
struct OmiHeaderChip: View {
    var systemImage: String? = nil
    let title: String
    var isActive: Bool = false
    var showsChevron: Bool = false
    var activeGlyphTint: Color? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            OmiHeaderChipLabel(
                systemImage: systemImage,
                title: title,
                isActive: isActive,
                showsChevron: showsChevron,
                activeGlyphTint: activeGlyphTint
            )
        }
        .buttonStyle(.plain)
    }
}
