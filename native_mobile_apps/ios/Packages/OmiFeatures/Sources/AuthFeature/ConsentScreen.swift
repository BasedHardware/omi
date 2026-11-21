import OmiDesign
import OmiService
import SwiftUI

/// Data & AI consent, before any AI processing (Flutter `ai_consent_widget.dart`, same ARB copy).
/// Local only, like Flutter's `aiConsentGiven`; shown again after every sign-in.
public struct ConsentScreen: View {
    @Environment(SessionStore.self) private var session

    public init() {}

    public var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.lg) {
            Spacer()
            Image(systemName: "lock.shield.fill")
                .font(.system(size: 40))
                .foregroundStyle(DS.Palette.agent)
            Text(L("dataAndPrivacy")).font(.title.weight(.bold))
            Text(L("consentDataMessage"))
                .font(DS.Typography.body)
                .foregroundStyle(DS.Palette.inkSecondary)
            Text(.init(
                L("yourDataIsProtected") + "[\(L("privacyPolicy"))](https://www.omi.me/pages/privacy)" + L("and")
                    + "[\(L("termsOfService"))](https://www.omi.me/pages/terms-of-service)."
            ))
            .font(DS.Typography.caption)
            .foregroundStyle(DS.Palette.inkTertiary)
            .tint(DS.Palette.ink)
            Spacer()
            Button(L("agreeAndContinue")) {
                DSHaptics.success()
                session.giveConsent()
            }
            .buttonStyle(.omiPrimary)
            .padding(.top, DS.Spacing.sm)
            .accessibilityIdentifier("consent.agree")
            Button(L("useDifferentAccount")) { session.signOut() }
                .font(.callout.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 40)
                .foregroundStyle(DS.Palette.ink)
        }
        .padding(DS.Spacing.gutter)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AuroraBackground())
    }
}
