import OmiComponents
import OmiDesign
import SwiftUI

/// The glyph in front of a settings row: one quiet symbol in a fixed-width column, no tile and no
/// per-row colors, so the list reads calm and the titles line up.
struct SettingsIcon: View {
    let systemImage: String
    var tint: Color = DS.Palette.inkSecondary

    var body: some View {
        Image(systemName: systemImage)
            .font(DS.Typography.body)
            .foregroundStyle(tint)
            .frame(width: 28)
            .accessibilityHidden(true)
    }
}

/// One settings row: icon, title, and an optional short value on the right (the current choice).
struct SettingsRowLabel: View {
    let title: String
    let systemImage: String
    var value: String?
    var tint: Color = DS.Palette.inkSecondary

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            SettingsIcon(systemImage: systemImage, tint: tint)
            Text(title).foregroundStyle(DS.Palette.ink)
            if let value {
                Spacer(minLength: DS.Spacing.sm)
                Text(value)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .lineLimit(1)
            }
        }
    }
}

/// A round monogram from a name ("Alice Moore" → "AM"): the profile header, people, apps without
/// an icon. A hairline ring, no fill.
struct Monogram: View {
    let name: String
    var size: CGFloat = 56

    var body: some View {
        Text(Self.initials(name))
            .font(size >= 44 ? DS.Typography.sectionTitle : DS.Typography.micro)
            .foregroundStyle(DS.Palette.ink)
            .frame(width: size, height: size)
            .overlay(Circle().strokeBorder(DS.Palette.hairline, lineWidth: 1))
            .accessibilityHidden(true)
    }

    static func initials(_ name: String) -> String {
        let words = name.split(whereSeparator: { $0 == " " || $0 == "@" || $0 == "." }).prefix(2)
        let letters = words.compactMap(\.first).map { String($0).uppercased() }.joined()
        return letters.isEmpty ? "?" : letters
    }
}

/// The calm hero on top of a few screens (referral, phone calls locked, connect your AI): one thin
/// line glyph, one title line, one short line under it.
struct SettingsHero: View {
    let systemImage: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: DS.Spacing.md) {
            Image(systemName: systemImage)
                .font(.system(size: 34, weight: .light))
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(height: 44)
                .accessibilityHidden(true)
            Text(title)
                .font(DS.Typography.title)
                .foregroundStyle(DS.Palette.ink)
                .multilineTextAlignment(.center)
            Text(message)
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.inkSecondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, DS.Spacing.xl)
        .accessibilityElement(children: .combine)
    }
}

/// A Settings list in the spirit of the ChatGPT app's settings: rounded groups on the plain page,
/// rows divided by hairlines, quiet gray section labels (`OmiGroupedList`).
typealias SettingsList<Content: View> = OmiGroupedList<Content>

/// A section label in a settings list: small, gray, sentence case (as on Home).
typealias SettingsHeader = OmiSectionLabel

extension Section where Parent == OmiSectionLabel, Content: View, Footer == EmptyView {
    /// `Section(L("…")) { … }` in a settings list: the title as a quiet section label.
    init(_ title: String, @ViewBuilder content: () -> Content) {
        self.init(content: content, header: { OmiSectionLabel(title) })
    }
}

extension View {
    /// A row that sits on the page instead of a group (heroes, big buttons, the page title).
    func plainSettingsRow(inset: CGFloat = 0) -> some View {
        omiPlainRow(inset: inset)
    }
}
