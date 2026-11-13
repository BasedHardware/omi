import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// Your number as caller ID: pick the country, type the number, Omi has Twilio call it
/// (Flutter `phone_setup_number_page`).
struct PhoneNumberSetupScreen: View {
    @Environment(PhoneCallStore.self) private var phone
    @Environment(\.dismiss) private var dismiss
    @State private var region = Locale.current.region?.identifier.uppercased() ?? "US"
    @State private var number = ""
    @State private var showsVerify = false
    @FocusState private var focused: Bool

    private var e164: String? {
        PhoneNumberFormat.e164(national: number, region: region)
    }

    var body: some View {
        Form {
            Section {
                NavigationLink { CountryPicker(selection: $region) } label: {
                    LabeledContent(L("nativePhoneCountry"), value: CountryPicker.title(region))
                }
                TextField(L("phoneNumberHint"), text: $number)
                    .keyboardType(.phonePad)
                    .textContentType(.telephoneNumber)
                    .focused($focused)
                    .accessibilityIdentifier("phone.numberField")
            } header: {
                SettingsHeader(L("nativePhoneYourNumberTitle"))
            } footer: {
                if let failure = phone.verificationFailure {
                    Text(PhoneCallWording.failure(failure)).foregroundStyle(DS.Palette.live)
                } else if !number.isEmpty, e164 == nil {
                    Text(L("nativePhoneInvalidNumber"))
                } else {
                    Text(L("nativePhoneCallerIDHint"))
                }
            }
            Section {
                Button {
                    Task { await start() }
                } label: {
                    HStack {
                        Text(L("phoneContinue")).font(DS.Typography.button)
                        if phone.isStartingVerification { Spacer(); ProgressView() }
                    }
                }
                .disabled(e164 == nil || phone.isStartingVerification)
                .accessibilityIdentifier("phone.continue")
            }
        }
        .omiPage(L("nativePhoneYourNumberTitle"))
        .onAppear { focused = true }
        .navigationDestination(isPresented: $showsVerify) {
            PhoneVerifyScreen(onDone: { dismiss() })
        }
    }

    private func start() async {
        guard let e164 else { return }
        guard await phone.startVerification(e164) else { return }
        if phone.verification?.status == .verified {
            dismiss()
        } else {
            showsVerify = true
        }
    }
}

/// Twilio is calling: answer, type the code (Flutter `phone_setup_verify_page`). Polls while shown.
struct PhoneVerifyScreen: View {
    @Environment(PhoneCallStore.self) private var phone
    let onDone: () -> Void

    var body: some View {
        SettingsList {
            Section {
                status
                LabeledContent(L("nativePhoneAnswerCallFrom"), value: PhoneCallStore.verificationCallerID)
                codeRow
            } footer: {
                Text(PhoneNumberFormat.display(phone.verification?.phoneNumber ?? ""))
            }
            if [.missed, .timedOut].contains(phone.verification?.status) {
                Section {
                    Button(L("phoneTryAgain")) { Task { await phone.retryVerification() } }
                        .disabled(phone.isStartingVerification)
                }
            }
        }
        .omiPage(L("nativePhoneSetupStep1Title"))
        .task { await phone.pollVerification() }
        .onChange(of: phone.verification?.status) { _, status in
            guard status == .verified else { return }
            DSHaptics.success()
            Task {
                try? await Task.sleep(for: .milliseconds(800))
                onDone()
            }
        }
    }

    private struct StatusLook {
        let text: String
        let icon: String
        let tint: Color
    }

    private var look: StatusLook {
        switch phone.verification?.status ?? .calling {
        case .calling: StatusLook(text: L("statusCalling"), icon: "phone.arrow.down.left", tint: DS.Palette.ink)
        case .inProgress: StatusLook(text: L("statusCallInProgress"), icon: "phone.connection", tint: DS.Palette.ink)
        case .missed: StatusLook(text: L("statusCallMissed"), icon: "phone.down", tint: DS.Palette.warning)
        case .verified: StatusLook(text: L("statusVerifiedLabel"), icon: "checkmark.circle.fill", tint: DS.Palette.success)
        case .timedOut: StatusLook(text: L("statusTimedOut"), icon: "exclamationmark.circle", tint: DS.Palette.live)
        }
    }

    private var status: some View {
        Label(look.text, systemImage: look.icon)
            .foregroundStyle(look.tint)
            .symbolEffect(.pulse, isActive: [.calling, .inProgress].contains(phone.verification?.status))
            .accessibilityAddTraits(.updatesFrequently)
    }

    @ViewBuilder
    private var codeRow: some View {
        if let code = phone.verification?.code {
            VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                Text(L("nativePhoneEnterCodeOnCall")).foregroundStyle(DS.Palette.inkSecondary)
                Text(code.map(String.init).joined(separator: " "))
                    .font(.largeTitle.weight(.bold).monospacedDigit())
                    .textSelection(.enabled)
                    .accessibilityLabel(code.map(String.init).joined(separator: ", "))
            }
            .padding(.vertical, DS.Spacing.xs)
        } else {
            Text(L("nativePhoneFollowVoice"))
        }
    }
}

/// Every region with a calling code, searchable, in the user's language.
struct CountryPicker: View {
    @Binding var selection: String
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""

    static func title(_ region: String) -> String {
        let name = Locale.current.localizedString(forRegionCode: region) ?? region
        return CallingCodes.byRegion[region].map { "\(name) (+\($0))" } ?? name
    }

    private var regions: [String] {
        CallingCodes.byRegion.keys
            .filter { query.isEmpty || Self.title($0).localizedCaseInsensitiveContains(query) }
            .sorted { Self.title($0).localizedStandardCompare(Self.title($1)) == .orderedAscending }
    }

    var body: some View {
        List(regions, id: \.self) { region in
            Button {
                selection = region
                dismiss()
            } label: {
                HStack {
                    Text(Self.title(region)).foregroundStyle(DS.Palette.ink)
                    Spacer()
                    if region == selection { Image(systemName: "checkmark").foregroundStyle(DS.Palette.ink) }
                }
            }
        }
        .searchable(text: $query, prompt: L("searchCountries"))
        .omiPage(L("phoneSelectCountryTitle"))
    }
}
