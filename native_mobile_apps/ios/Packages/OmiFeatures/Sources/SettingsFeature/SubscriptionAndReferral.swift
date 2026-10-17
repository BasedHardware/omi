import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Cancel the plan in the app (Flutter `cancel_subscription_sheet`): why, anything to add, then
/// confirm. Stripe keeps the plan until the end of the billing period.
struct CancelSubscriptionSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var store: ProfileStore
    @State private var reason: String?
    @State private var details = ""
    @State private var isCancelling = false
    @State private var failed = false

    /// Flutter's reason codes, stored with the cancellation.
    static var reasons: [(code: String, title: String)] {
        [
            ("too_expensive", L("cancelReasonTooExpensive")), ("not_using_enough", L("cancelReasonNotUsing")),
            ("missing_features", L("cancelReasonMissingFeatures")), ("audio_quality", L("cancelReasonAudioQuality")),
            ("battery_drain", L("cancelReasonBatteryDrain")), ("found_alternative", L("cancelReasonFoundAlternative")),
            ("other", L("cancelReasonOther")),
        ]
    }

    init(store: ProfileStore) {
        _store = State(initialValue: store)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    ForEach(Self.reasons, id: \.code) { item in
                        Button {
                            DSHaptics.selection()
                            reason = item.code
                        } label: {
                            HStack {
                                Text(item.title).foregroundStyle(DS.Palette.ink)
                                Spacer()
                                if reason == item.code { Image(systemName: "checkmark").foregroundStyle(DS.Palette.ink) }
                            }
                        }
                    }
                } header: {
                    SettingsHeader(L("whyAreYouCanceling"))
                } footer: {
                    Text(L("cancelReasonSubtitle"))
                }
                Section(L("tellUsMore")) {
                    TextField(L("cancelReasonDetailHint"), text: $details, axis: .vertical).lineLimit(2 ... 5)
                }
                Section {
                    Text(L("nativeCancelAtPeriodEnd")).font(DS.Typography.callout)
                    if failed {
                        Text(L("nativeCancelFailed")).font(DS.Typography.caption).foregroundStyle(DS.Palette.live)
                    }
                    Button(L("cancelSubscription"), role: .destructive) { cancel() }
                        .disabled(reason == nil || isCancelling)
                        .accessibilityIdentifier("cancelSubscription.confirm")
                } header: {
                    SettingsHeader(L("justAMoment"))
                }
            }
            .scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(L("cancelSubscription"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("keepSubscription")) { dismiss() } }
            }
        }
    }

    private func cancel() {
        isCancelling = true
        failed = false
        Task {
            if await store.cancelSubscription(reason: reason, details: details) {
                DSHaptics.success()
                dismiss()
            } else {
                failed = true
            }
            isCancelling = false
        }
    }
}

/// Account › Invite friends: one line on what it is, your link with Share and Copy, three short
/// steps. Flutter showed the affiliate page (affiliate.omi.me); it stays one tap away.
struct ReferralScreen: View {
    @State private var store: ProfileStore
    @State private var browser: BrowserItem?
    @State private var copied = false

    init(store: ProfileStore) {
        _store = State(initialValue: store)
    }

    var body: some View {
        SettingsList {
            Section {
                SettingsHero(systemImage: "gift", title: L("nativeReferralTitle"), message: L("nativeReferralHero"))
                    .plainSettingsRow()
            }
            link
            Section {
                step(1, L("nativeReferralStep1"))
                step(2, L("nativeReferralStep2"))
                step(3, L("nativeReferralStep3"))
            } header: {
                SettingsHeader(L("nativeReferralHowItWorks"))
            } footer: {
                Button(L("nativeReferralProgramPage")) { browser = BrowserItem(URL(string: "https://affiliate.omi.me/")!) }
                    .font(DS.Typography.caption)
                    .tint(DS.Palette.inkSecondary)
                    .padding(.top, DS.Spacing.xs)
            }
        }
        .omiPage(L("nativeSettingsInviteFriends"))
        .task { await store.loadReferral() }
        .sheet(item: $browser) { SafariView(url: $0.url) }
    }

    /// Your link with Copy in one group, then Share as the screen's one primary action.
    @ViewBuilder
    private var link: some View {
        if let url = store.referralURL {
            Section {
                Text(url.absoluteString.replacingOccurrences(of: "https://", with: ""))
                    .font(DS.Typography.callout.monospaced())
                    .foregroundStyle(DS.Palette.ink)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .textSelection(.enabled)
                Button {
                    UIPasteboard.general.url = url
                    DSHaptics.success()
                    copied = true
                } label: {
                    SettingsRowLabel(
                        title: copied ? L("copied") : L("nativeReferralCopy"), systemImage: copied ? "checkmark" : "doc.on.doc"
                    )
                }
            }
            Section {
                ShareLink(item: url, message: Text(L("nativeReferralShareMessage"))) {
                    Label(L("nativeReferralShare"), systemImage: "square.and.arrow.up")
                }
                .buttonStyle(.omiPrimary)
                .plainSettingsRow()
                .accessibilityIdentifier("referral.share")
            }
        } else if store.referralFailed {
            Section { retry(L("nativeReferralUnavailable")) { await store.loadReferral() } }
        } else {
            Section { ProgressView().frame(maxWidth: .infinity, minHeight: 120) }
        }
    }

    private func step(_ number: Int, _ text: String) -> some View {
        // As the steps in Connect your AI: the number in quiet gray, then one sentence.
        HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
            Text(String(number))
                .font(DS.Typography.body.monospacedDigit())
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(width: 18, alignment: .leading)
            Text(text).font(DS.Typography.body)
        }
        .padding(.vertical, DS.Spacing.xxs)
        .accessibilityElement(children: .combine)
    }
}
