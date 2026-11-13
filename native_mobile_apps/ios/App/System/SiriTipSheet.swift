import AppIntents
import OmiDesign
import SwiftUI

/// Flutter's onboarding "Siri hint", opened once from Home's For you row: what to say to Siri,
/// and the app's shortcuts in the Shortcuts app.
struct SiriTipSheet: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: DS.Spacing.lg) {
                    Text(L("nativeHomeSiriBody"))
                        .font(DS.Typography.body)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    VStack(alignment: .leading, spacing: 0) {
                        phrase("bubble.left.and.text.bubble.right", L("nativeHomeSiriPhraseAsk"))
                        OmiHairline(leading: 28 + DS.Spacing.md)
                        phrase("brain.head.profile", L("nativeHomeSiriPhraseRemember"))
                        OmiHairline(leading: 28 + DS.Spacing.md)
                        phrase("plus.circle", L("nativeHomeSiriPhraseTask"))
                    }
                    .omiCard(padding: DS.Spacing.md)
                    ShortcutsLink()
                        .shortcutsLinkStyle(.automaticOutline)
                        .frame(maxWidth: .infinity)
                }
                .padding(DS.Spacing.gutter)
            }
            .background(DS.Palette.background)
            .navigationTitle(L("nativeHomeSiriTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button(L("done")) { dismiss() } }
            }
        }
        .presentationDetents([.medium, .large])
        .presentationBackground(DS.Palette.background)
        .accessibilityIdentifier("home.siriTip")
    }

    private func phrase(_ symbol: String, _ text: String) -> some View {
        HStack(spacing: DS.Spacing.md) {
            // A thin gray line glyph, no circle behind it (text-first rows).
            Image(systemName: symbol)
                .font(.system(size: 17, weight: .regular))
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(width: 28)
                .accessibilityHidden(true)
            Text(text).font(DS.Typography.body).foregroundStyle(DS.Palette.ink)
            Spacer(minLength: 0)
        }
        .padding(.vertical, DS.Spacing.md)
    }
}
