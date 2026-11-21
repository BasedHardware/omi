import OmiComponents
import OmiDesign
import SwiftUI

/// App › Appearance: System, Light or Dark as three small previews, and the app's language (iOS'
/// per-app language, Settings › Omi › Language).
struct AppearanceScreen: View {
    @Environment(\.openURL) private var openURL
    /// Read by the app root (`OmiApp`); the key matches Flutter's so an upgrade keeps the choice.
    @AppStorage("flutter.appearanceMode") private var appearance = "dark"

    static let modes = ["system", "light", "dark"]

    var body: some View {
        SettingsList {
            Section {
                HStack(spacing: DS.Spacing.md) {
                    ForEach(Self.modes, id: \.self) { mode in
                        ModeChoice(mode: mode, isSelected: appearance == mode) {
                            DSHaptics.selection()
                            appearance = mode
                        }
                    }
                }
                .padding(.vertical, DS.Spacing.sm)
            } header: {
                SettingsHeader(L("nativeSettingsTheme"))
            }
            Section {
                Button {
                    if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                } label: {
                    HStack {
                        SettingsRowLabel(title: L("nativeAppLanguage"), systemImage: "globe", value: Self.appLanguage)
                        Image(systemName: "arrow.up.right")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(DS.Palette.inkTertiary)
                    }
                }
                .accessibilityIdentifier("appearance.language")
            } footer: {
                Text(L("nativeAppLanguageHint"))
            }
        }
        .omiPage(L("appearance"))
    }

    static func title(_ mode: String) -> String {
        switch mode {
        case "light": L("nativeAppearanceLight")
        case "system": L("nativeAppearanceSystem")
        default: L("nativeAppearanceDark")
        }
    }

    /// The language the app shows, in that language's own words ("Deutsch").
    static var appLanguage: String {
        let code = Bundle.main.preferredLocalizations.first ?? Locale.current.language.languageCode?.identifier ?? "en"
        let locale = Locale(identifier: code)
        return locale.localizedString(forIdentifier: code)?.localizedCapitalized ?? code
    }
}

/// One appearance option: a tiny screen in that look, its name and a check.
private struct ModeChoice: View {
    let mode: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: DS.Spacing.sm) {
                preview
                    .frame(height: 96)
                    .clipShape(RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous)
                            .strokeBorder(isSelected ? DS.Palette.ink : DS.Palette.hairline, lineWidth: isSelected ? 2 : 1)
                    }
                Text(AppearanceScreen.title(mode))
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.ink)
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(isSelected ? DS.Palette.ink : DS.Palette.inkTertiary)
            }
            .frame(maxWidth: .infinity)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(AppearanceScreen.title(mode))
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
        .accessibilityIdentifier("appearance.\(mode)")
    }

    @ViewBuilder
    private var preview: some View {
        switch mode {
        case "light": MiniScreen(scheme: .light)
        case "dark": MiniScreen(scheme: .dark)
        default:
            // Light on the left half, dark on the right: "follows the iPhone".
            ZStack {
                MiniScreen(scheme: .light)
                MiniScreen(scheme: .dark)
                    .mask(alignment: .trailing) {
                        GeometryReader { geometry in
                            Rectangle().frame(width: geometry.size.width / 2).frame(maxWidth: .infinity, alignment: .trailing)
                        }
                    }
            }
        }
    }
}

/// A sketch of an Omi screen in one color scheme: page, a title bar and two cards. The palette's
/// own tokens, resolved for that scheme.
private struct MiniScreen: View {
    let scheme: ColorScheme

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Capsule().fill(DS.Palette.ink).frame(width: 30, height: 5)
            ForEach(0 ..< 2, id: \.self) { _ in
                VStack(alignment: .leading, spacing: 4) {
                    Capsule().fill(DS.Palette.ink.opacity(0.8)).frame(height: 4)
                    Capsule().fill(DS.Palette.inkTertiary).frame(width: 24, height: 4)
                }
                .padding(6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: 5, style: .continuous))
            }
            Spacer(minLength: 0)
        }
        .padding(8)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(DS.Palette.background)
        .environment(\.colorScheme, scheme)
    }
}
