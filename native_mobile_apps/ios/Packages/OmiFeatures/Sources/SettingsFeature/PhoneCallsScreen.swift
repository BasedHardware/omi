import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Settings › Phone Calls, the whole phone surface (Flutter `phone_calls_page`, `phone_setup_intro_page`,
/// `phone_call_settings_page`): set up a caller ID, start a call (keypad or a contact), your number
/// with delete, and past calls (the conversations they became).
struct PhoneScreen: View {
    @Environment(PhoneCallStore.self) private var phone
    @Environment(\.openURL) private var openURL
    @State private var showsDialer = false
    /// The dialer sheet is fully gone; only then can the call screen come up from here.
    @State private var dialerGone = true
    @State private var deleting: VerifiedPhoneNumber?
    @State private var deleteFailed = false

    var body: some View {
        SettingsList {
            if let unavailable = phone.unavailable {
                lockedSections(unavailable)
            } else if !phone.numbersLoaded {
                Section { ProgressView().frame(maxWidth: .infinity) }
            } else if phone.numbers.isEmpty {
                PhoneIntroSections()
            } else {
                callSection
                numbersSection
                historySection
            }
        }
        .omiPage(L("nativeSettingsPhoneCalls"))
        .task { await phone.load() }
        .refreshable { await phone.load() }
        .sheet(isPresented: $showsDialer, onDismiss: { dialerGone = true }, content: { PhoneDialerScreen() })
        .fullScreenCover(isPresented: callScreenBinding) { ActiveCallScreen() }
        .confirmationDialog(
            deleting.map { L("nativePhoneDeleteNumberTitle", PhoneNumberFormat.display($0.phoneNumber)) } ?? "",
            isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }),
            titleVisibility: .visible, presenting: deleting
        ) { number in
            Button(L("delete"), role: .destructive) { Task { deleteFailed = !(await phone.deleteNumber(number.id)) } }
        } message: { _ in
            Text(L("nativePhoneDeleteNumberMessage"))
        }
        .alert(L("phoneDeleteNumberFailed"), isPresented: $deleteFailed) { Button(L("ok")) {} }
    }

    /// Calls are not available on this plan (or the free calls are used up): what calling with Omi
    /// is, why it is locked, and the way to the plans.
    @ViewBuilder
    private func lockedSections(_ unavailable: PhoneCallErrorDetail) -> some View {
        Section {
            SettingsHero(systemImage: "phone.bubble", title: L("phoneCallsWithOmi"), message: L("phoneCallsSubtitle"))
                .plainSettingsRow()
        }
        Section {
            Label(PhoneCallWording.unavailable(unavailable), systemImage: "lock")
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.inkSecondary)
            NavigationLink(value: SettingsTopic.planUsage) {
                Text(L("nativeSettingsSeePlans")).font(DS.Typography.button).foregroundStyle(DS.Palette.ink)
            }
            .accessibilityIdentifier("phone.seePlans")
        }
    }

    /// The call screen comes up here while Settings is open; elsewhere the app shell shows it.
    private var callScreenBinding: Binding<Bool> {
        Binding(
            get: { phone.showsCallScreen && dialerGone && phone.phase != .idle },
            set: { phone.showsCallScreen = $0 }
        )
    }

    private var callSection: some View {
        Section {
            if phone.isInProgress, !phone.showsCallScreen {
                Button { phone.showsCallScreen = true } label: {
                    Label(L("nativePhoneReturnToCall"), systemImage: "phone.connection").foregroundStyle(DS.Palette.success)
                }
            } else {
                Button {
                    dialerGone = false
                    showsDialer = true
                } label: {
                    SettingsRowLabel(title: L("nativePhoneNewCall"), systemImage: "phone")
                }
                .disabled(phone.quota.map { !$0.hasAccess } ?? false)
                .accessibilityIdentifier("phone.newCall")
            }
        } footer: {
            if let text = PhoneCallWording.quota(phone.quota) { Text(text) }
        }
    }

    private var numbersSection: some View {
        Section {
            ForEach(phone.numbers) { number in
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    Text(PhoneNumberFormat.display(number.phoneNumber)).font(DS.Typography.cardTitle)
                    Text(PhoneCallWording.verified(number.verifiedAt))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
                .swipeActions {
                    Button(L("delete"), role: .destructive) { deleting = number }
                }
                .contextMenu {
                    Button(L("delete"), systemImage: "trash", role: .destructive) { deleting = number }
                }
            }
        } header: {
            SettingsHeader(L("nativeYourNumbers"))
        } footer: {
            Text(L("nativePhoneCallerIDFooter"))
        }
    }

    private var historySection: some View {
        Section(L("nativePhoneRecentCalls")) {
            if phone.history.isEmpty {
                Text(L("nativePhoneNoCallsYet")).foregroundStyle(DS.Palette.inkSecondary)
            }
            ForEach(phone.history) { conversation in
                Button { openURL(DeepLink.conversation(id: conversation.id).url) } label: { ConversationRow(conversation) }
                    .buttonStyle(.plain)
                    .listRowInsets(EdgeInsets(top: DS.Spacing.xs, leading: DS.Spacing.sm, bottom: DS.Spacing.xs, trailing: DS.Spacing.sm))
            }
        }
    }
}

/// No number yet: what calling with Omi is, three steps, then number setup.
private struct PhoneIntroSections: View {
    var body: some View {
        Section {
            SettingsHero(systemImage: "phone.bubble", title: L("phoneCallsWithOmi"), message: L("phoneCallsSubtitle"))
                .plainSettingsRow()
        }
        Section {
            step(1, "checkmark.shield", L("nativePhoneSetupStep1Title"), L("nativePhoneSetupStep1Subtitle"))
            step(2, "circle.grid.3x3", L("nativePhoneSetupStep2Title"), L("nativePhoneSetupStep2Subtitle"))
            step(3, "waveform", L("nativePhoneSetupStep3Title"), L("phoneSetupStep3Subtitle"))
        } footer: {
            Text(L("nativeCallRecordingConsent"))
        }
        Section {
            NavigationLink { PhoneNumberSetupScreen() } label: {
                Text(L("phoneGetStarted")).font(DS.Typography.button)
            }
            .accessibilityIdentifier("phone.getStarted")
        }
    }

    private func step(_ number: Int, _ icon: String, _ title: String, _ subtitle: String) -> some View {
        Label {
            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                Text(title)
                Text(subtitle).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
            }
        } icon: {
            SettingsIcon(systemImage: icon)
        }
        .accessibilityElement(children: .combine)
        .accessibilitySortPriority(Double(-number))
    }
}

/// How the phone screens word store states.
enum PhoneCallWording {
    static func failure(_ failure: PhoneCallFailure) -> String {
        switch failure {
        case .alreadyInProgress: L("callAlreadyInProgress")
        case .microphonePermission: L("nativePhoneMicrophoneNeeded")
        case .noVerifiedNumber: L("nativePhoneSetupStep1Title")
        case let .server(detail): detail.map(unavailable) ?? L("failedToStartCall")
        case let .engine(message): message
        }
    }

    static func unavailable(_ detail: PhoneCallErrorDetail) -> String {
        switch detail {
        case .quotaExceeded: L("phoneFreeCallLimitReached")
        case let .message(text) where text.localizedCaseInsensitiveContains("paid subscription"): L("nativePhoneCallsNeedPlan")
        case let .message(text): text
        }
    }

    /// Free plans: calls left this month (and their length); nothing on unlimited plans.
    static func quota(_ quota: PhoneCallQuota?) -> String? {
        guard let quota, !quota.isPaid, let limit = quota.monthlyLimit, limit > 0 else { return nil }
        let remaining = quota.remaining ?? (limit - quota.monthlyUsed)
        if remaining <= 0 { return L("phoneFreeCallLimitReached") }
        let minutes = (quota.maxDurationSeconds ?? 0) / 60
        return minutes > 0
            ? L("phoneFreeCallsRemainingWithMax", String(remaining), String(limit), String(minutes))
            : L("phoneFreeCallsRemaining", String(remaining), String(limit))
    }

    static func verified(_ date: Date?) -> String {
        guard let date else { return L("statusVerifiedLabel") }
        return L("nativePhoneVerifiedAgo", date.formatted(.relative(presentation: .named)))
    }
}
