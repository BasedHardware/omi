import OmiDesign
import SwiftUI

/// A list of rounded groups on the plain page, as in the ChatGPT app's settings: each section is
/// one raised card (`DS.Palette.card`) with hairlines between its rows; quiet gray section labels
/// (`OmiSectionLabel`). Settings and My Omi use it. Rows that sit on the page (heroes, big buttons,
/// a page title) opt out with `omiPlainRow()`.
public struct OmiGroupedList<Content: View>: View {
    let content: Content

    public init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    public var body: some View {
        List {
            Group { content }
                .listRowBackground(DS.Palette.card)
                .listRowSeparatorTint(DS.Palette.hairline)
                .listSectionSeparator(.hidden)
        }
        .listStyle(.insetGrouped)
        .listSectionSpacing(DS.Spacing.xl)
        .environment(\.defaultMinListRowHeight, 50)
    }
}

/// A flat list as in the ChatGPT app's settings root: rows sit directly on the page (no card
/// behind them), divided by hairlines that start at the title, with quiet gray section labels. The
/// Settings root and My Omi use it; deeper screens keep `OmiGroupedList`.
public struct OmiFlatList<Content: View>: View {
    let content: Content

    public init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    public var body: some View {
        List {
            Group { content }
                .listRowBackground(Color.clear)
                .listRowSeparatorTint(DS.Palette.hairline)
                .listSectionSeparator(.hidden)
        }
        .listStyle(.insetGrouped)
        .listSectionSpacing(DS.Spacing.lg)
        .environment(\.defaultMinListRowHeight, 50)
    }
}

/// A section label over a group: small, gray, sentence case (as "For you" on Home).
public struct OmiSectionLabel: View {
    let title: String

    public init(_ title: String) {
        self.title = title
    }

    public var body: some View {
        Text(title)
            .font(DS.Typography.sectionLabel)
            .foregroundStyle(DS.Palette.inkSecondary)
            .textCase(nil)
            .accessibilityAddTraits(.isHeader)
    }
}

public extension View {
    /// A row that sits on the page instead of a group (a hero, a big button, the page title): no
    /// card behind it. `inset` 0 lines it up with the groups' edges (buttons, pickers); text uses
    /// `DS.Spacing.lg` to line up with the rows' text and the section labels.
    func omiPlainRow(inset: CGFloat = 0) -> some View {
        listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets(top: 0, leading: inset, bottom: 0, trailing: inset))
            .listRowSeparator(.hidden)
            .listSectionSeparator(.hidden)
    }

    /// A row's leading glyph in a grouped list: thin, monochrome, in a fixed column so titles line up.
    func omiRowGlyph() -> some View {
        font(.system(size: 17, weight: .regular))
            .foregroundStyle(DS.Palette.inkSecondary)
            .frame(width: 28)
            .accessibilityHidden(true)
    }
}
