import OmiKit
import SwiftUI

// Settings page, ported from `react-native/src/pages/Settings.tsx`: the
// Account / Privacy / Developer tabs over the store's account snapshot, the
// backend-plane and live-voice developer rows with their exact copy, sign
// in/out, retry, and the device permissions + policy link rows.

public struct SettingsPage: View {
    public var onOpenApps: (() -> Void)? = nil
    public var signingIn: Bool = false

    @EnvironmentObject private var store: AppStore
    @Environment(\.openURL) private var openURL
    @State private var section: String = "Account"
    @State private var actionError: String?

    private let sections = ["Account", "Privacy", "Developer"]

    public init(onOpenApps: (() -> Void)? = nil, signingIn: Bool = false) {
        self.onOpenApps = onOpenApps
        self.signingIn = signingIn
    }

    private var snapshot: AccountSettingsSnapshot? { store.accountSettings }
    private var loading: Bool { store.cloudLoading && snapshot == nil }
    private var signedOut: Bool { store.authState == .signedOut }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                if onOpenApps != nil {
                    SettingRow(
                        title: "Apps",
                        copy: "Manage your apps and connected services.",
                        actionLabel: "Open apps",
                        action: { onOpenApps?() }
                    )
                }
                tabs
                if section == "Developer" {
                    developerGroup
                }
                sectionGroup
                linksGroup
            }
            .padding(.top, 4)
            .padding(.bottom, 24)
        }
    }

    private var tabs: some View {
        HStack(spacing: 8) {
            ForEach(sections, id: \.self) { label in
                let isSelected = section == label
                Button(action: { section = label }) {
                    Text(label)
                        .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                        .foregroundColor(
                            isSelected ? OmiColor.hex(0xEEEEEE) : OmiColor.hex(0xA0A0A0)
                        )
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(
                            RoundedRectangle(cornerRadius: Radius.md)
                                .fill(
                                    isSelected ? Palette.primary : Color.clear
                                )
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Radius.md)
                                .strokeBorder(Palette.line, lineWidth: Borders.width)
                        )
                }
                .buttonStyle(KitPressableStyle())
                .animation(KitMotion.slide, value: section)
                .accessibilityLabel("\(label) settings")
                .accessibilityAddTraits(isSelected ? [.isSelected] : [])
            }
        }
    }

    private func group<Content: View>(
        _ title: String, @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: Space.md) {
            Text(title)
                .font(TypeStyle(size: 18, lineHeight: 24, weight: .semibold).font)
                .foregroundColor(Color.white)
            content()
        }
        .padding(Space.lg)
        .background(MobilePalette.surface)
        .overlay(
            RoundedRectangle(cornerRadius: 22)
                .strokeBorder(MobilePalette.border, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: 22))
    }

    // MARK: Developer (backend plane + live voice)

    private var developerGroup: some View {
        group("AI & connection") {
            BackendPlaneRow()
            LiveVoiceRow()
        }
    }

    // MARK: Selected section

    private var sectionGroup: some View {
        group(section) {
            if loading {
                HStack(spacing: 12) {
                    ProgressView().tint(OmiColor.hex(0x888888))
                    Text("Loading account…")
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                }
            } else if signedOut {
                VStack(alignment: .leading, spacing: 12) {
                    Text(desktopBackendUnauthorizedCopy)
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                    Button(action: { Task { await store.startSignIn() } }) {
                        Text(signingIn ? "Signing in…" : "Sign in")
                            .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                            .foregroundColor(Color.white)
                            .frame(minHeight: 44)
                            .padding(.horizontal, Space.md)
                            .background(Palette.primary)
                            .clipShape(RoundedRectangle(cornerRadius: Radius.md))
                    }
                    .buttonStyle(KitPressableStyle())
                    .disabled(signingIn)
                    .accessibilityLabel("Sign in")
                }
            } else if store.authState == .onboarding {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Finish setting up your Omi account to load account settings.")
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                    Button(action: { Task { await store.completeOnboarding() } }) {
                        Text("Continue")
                            .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                            .foregroundColor(Color.white)
                            .frame(minHeight: 44)
                            .padding(.horizontal, Space.md)
                            .background(Palette.primary)
                            .clipShape(RoundedRectangle(cornerRadius: Radius.md))
                    }
                    .buttonStyle(KitPressableStyle())
                    .accessibilityLabel("Continue")
                }
            } else if section == "Account" {
                accountSection
            } else if section == "Privacy" {
                privacySection
            } else {
                developerSection
            }
            if let actionError {
                Text(actionError)
                    .font(TypeStyle(size: 13, lineHeight: 18, weight: .regular).font)
                    .foregroundColor(Palette.danger)
            }
        }
    }

    @ViewBuilder
    private var accountSection: some View {
        if let snapshot {
            if let profile = snapshot.profile {
                SettingRow(
                    title: "Name",
                    copy: profile.name ?? "Name not set on this account."
                )
                SettingRow(
                    title: "Email",
                    copy: profile.email ?? "Email not set on this account."
                )
                SettingRow(title: "Account id", copy: profile.uid)
                if let company = profile.company {
                    SettingRow(title: "Company", copy: company)
                }
                if let job = profile.job {
                    SettingRow(title: "Job", copy: job)
                }
                if let dataProtectionLevel = profile.dataProtectionLevel {
                    SettingRow(title: "Data protection", copy: dataProtectionLevel)
                }
            } else {
                Text(snapshot.profileError ?? "Account profile is unavailable.")
                    .font(Typography.caption.font)
                    .foregroundColor(Palette.textMuted)
            }
            if let subscription = snapshot.subscription {
                SettingRow(title: "Plan", copy: planCopy(subscription))
            } else {
                Text(snapshot.subscriptionError ?? "Plan is unavailable.")
                    .font(Typography.caption.font)
                    .foregroundColor(Palette.textMuted)
            }
            SettingRow(
                title: "Sign out",
                copy: "Leave this app's cloud session. Your Omi account stays in the cloud.",
                actionLabel: "Sign out",
                action: { Task { await store.signOut() } }
            )
        }
    }

    private func planCopy(_ subscription: CloudSubscription) -> String {
        var parts = [subscription.plan, subscription.status]
        if let used = subscription.transcriptionSecondsUsed,
            let limit = subscription.transcriptionSecondsLimit
        {
            parts.append("\(used) / \(limit) transcribed seconds")
        }
        return parts.joined(separator: " · ")
    }

    @ViewBuilder
    private var privacySection: some View {
        if let snapshot {
            if let storePermission = snapshot.storeRecordingPermission {
                SettingRow(
                    title: "Recording storage",
                    copy: storePermission
                        ? "Cloud recording storage is on."
                        : "Cloud recording storage is off.",
                    actionLabel: storePermission
                        ? "Turn off recording storage" : "Turn on recording storage",
                    action: {
                        Task { await store.setStoreRecordingPermission(!storePermission) }
                    }
                )
            } else {
                Text(
                    snapshot.storeRecordingError
                        ?? "Recording storage permission is unavailable."
                )
                .font(Typography.caption.font)
                .foregroundColor(Palette.textMuted)
            }
            if let trainingOptedIn = snapshot.trainingOptedIn {
                SettingRow(
                    title: "Training data",
                    copy: trainingOptedIn
                        ? "This account has opted in to training data. The API does not expose an opt-out from here."
                        : "This account has not opted in to training data.",
                    actionLabel: trainingOptedIn ? nil : "Opt in",
                    action: trainingOptedIn ? nil : {
                        Task { await store.optInTrainingData() }
                    }
                )
            } else {
                Text(snapshot.trainingError ?? "Training opt-in is unavailable.")
                    .font(Typography.caption.font)
                    .foregroundColor(Palette.textMuted)
            }
            if let sync = snapshot.privateCloudSync {
                SettingRow(
                    title: "Private cloud sync",
                    copy: sync ? "Private cloud sync is on." : "Private cloud sync is off.",
                    actionLabel: sync
                        ? "Turn off private cloud sync" : "Turn on private cloud sync",
                    action: { Task { await store.setPrivateCloudSync(!sync) } }
                )
            } else {
                Text(
                    snapshot.privateCloudSyncError
                        ?? "Private cloud sync is unavailable."
                )
                .font(Typography.caption.font)
                .foregroundColor(Palette.textMuted)
            }
        }
    }

    @ViewBuilder
    private var developerSection: some View {
        if let snapshot {
            if let webhooks = snapshot.webhooks {
                if webhooks.isEmpty {
                    Text("No developer webhooks were returned.")
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                } else {
                    ForEach(webhooks, id: \.type) { webhook in
                        SettingRow(
                            title: webhook.type,
                            copy: webhookCopy(webhook)
                        )
                    }
                }
            } else {
                Text(snapshot.webhooksError ?? "Developer webhook status is unavailable.")
                    .font(Typography.caption.font)
                    .foregroundColor(Palette.textMuted)
            }
        }
    }

    private func webhookCopy(_ webhook: CloudWebhookStatus) -> String {
        var parts: [String] = []
        if webhook.enabled == nil {
            parts.append("Status unknown")
        } else if webhook.enabled == true {
            parts.append("Enabled")
        } else {
            parts.append("Disabled")
        }
        if let url = webhook.url {
            parts.append(url)
        }
        return parts.joined(separator: " · ")
    }

    // MARK: Links

    private var linksGroup: some View {
        group("About") {
            SettingRow(
                title: "App permissions",
                copy: "Review permissions for Omi in your device settings.",
                actionLabel: "Open app permissions",
                action: { Task { await store.requestPermission(PermissionKind.microphone) } }
            )
            SettingRow(
                title: "Privacy policy",
                copy: "How Omi handles your information.",
                actionLabel: "Read privacy policy",
                action: { openPolicy(urlString: "https://www.omi.me/pages/privacy") }
            )
            SettingRow(
                title: "Terms of service",
                copy: "Terms for using Omi.",
                actionLabel: "Read terms of service",
                action: { openPolicy(urlString: "https://www.omi.me/pages/terms-of-service") }
            )
        }
    }

    private func openPolicy(urlString: String) {
        guard let url = URL(string: urlString) else {
            actionError = "The privacy policy could not be opened."
            return
        }
        actionError = nil
        openURL(url)
    }
}

// MARK: - Rows

public struct SettingRow: View {
    public let title: String
    public let copy: String
    public let actionLabel: String?
    public let action: (() -> Void)?

    public init(
        title: String, copy: String, actionLabel: String? = nil,
        action: (() -> Void)? = nil
    ) {
        self.title = title
        self.copy = copy
        self.actionLabel = actionLabel
        self.action = action
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(TypeStyle(size: 14, lineHeight: 18, weight: .semibold).font)
                        .foregroundColor(OmiColor.hex(0xEEEEEE))
                    Text(copy)
                        .font(TypeStyle(size: 12, lineHeight: 17, weight: .regular).font)
                        .foregroundColor(OmiColor.hex(0x888888))
                }
                .frame(minWidth: 160, maxWidth: .infinity, alignment: .leading)
                if let actionLabel, action != nil {
                    rowButton(actionLabel)
                }
            }
        }
        .padding(.top, Space.lg)
        .overlay(alignment: .top) {
            Rectangle()
                .fill(MobilePalette.border.opacity(0.5))
                .frame(height: 0.5)
        }
    }

    private func rowButton(_ label: String) -> some View {
        Button(action: { action?() }) {
            Text(label)
                .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                .foregroundColor(Color.white)
                .frame(minHeight: 44)
                .padding(.horizontal, Space.md)
                .background(Palette.input)
                .overlay(
                    RoundedRectangle(cornerRadius: Radius.md)
                        .strokeBorder(Palette.line, lineWidth: Borders.width)
                )
                .clipShape(RoundedRectangle(cornerRadius: Radius.md))
        }
        .buttonStyle(KitPressableStyle())
        .accessibilityLabel(label)
    }
}

/// Backend plane choice (Developer tab): old production api.omi.me versus the
/// stamped v5 origin. Copy is exact from `Settings.tsx`.
public struct BackendPlaneRow: View {
    @EnvironmentObject private var store: AppStore

    public init() {}

    private var plane: SoftwarePlane { store.preferences.softwarePlane }
    private var stampedOrigin: String? { store.preferences.stampedV5Origin }

    private var copy: String {
        if plane == .new {
            if stampedOrigin != nil {
                return "New sends v5 chat, capture, conversations, memories, and tasks to the stamped origin. Account, apps, privacy, and native Settings still use production api.omi.me."
            }
            return "New is selected, but no valid stamped v5 origin is configured."
        }
        return "Old backend uses your existing Omi account and api.omi.me."
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Backend")
                .font(TypeStyle(size: 14, lineHeight: 18, weight: .semibold).font)
                .foregroundColor(OmiColor.hex(0xEEEEEE))
            Text(copy)
                .font(TypeStyle(size: 12, lineHeight: 17, weight: .regular).font)
                .foregroundColor(OmiColor.hex(0x888888))
            HStack(spacing: 8) {
                choice("Old backend", label: "Use Old backend", value: .old)
                choice("New backend", label: "Use New backend", value: .new)
            }
        }
        .padding(.top, Space.lg)
    }

    private func choice(
        _ title: String, label: String, value: SoftwarePlane
    ) -> some View {
        let isSelected = plane == value
        return Button(action: {
            Task { await store.setPreference("softwarePlane", PreferenceValue.string(value.rawValue)) }
        }) {
            Text(title)
                .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                .foregroundColor(Color.white)
                .frame(minHeight: 44)
                .padding(.horizontal, Space.md)
                .background(isSelected ? MobilePalette.surfaceRaised : Palette.input)
                .overlay(
                    RoundedRectangle(cornerRadius: Radius.md)
                        .strokeBorder(
                            isSelected ? MobilePalette.textMuted : Palette.line,
                            lineWidth: Borders.width
                        )
                )
                .clipShape(RoundedRectangle(cornerRadius: Radius.md))
        }
        .buttonStyle(KitPressableStyle())
        .accessibilityLabel(label)
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }
}

/// Live voice provider choice (Developer tab). Copy is exact from
/// `Settings.tsx`.
public struct LiveVoiceRow: View {
    @EnvironmentObject private var store: AppStore

    public init() {}

    private var provider: LiveVoiceProvider { store.preferences.liveVoiceProvider }

    private var copy: String {
        provider == .geminiLive
            ? "Uses models/gemini-3.1-flash-live-preview over Gemini Live. Fails closed if GEMINI_API_KEY is missing on the server."
            : "Uses gpt-live-1 over OpenAI WebRTC. Fails closed if OPENAI_API_KEY is missing on the server."
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Live voice")
                .font(TypeStyle(size: 14, lineHeight: 18, weight: .semibold).font)
                .foregroundColor(OmiColor.hex(0xEEEEEE))
            Text(copy)
                .font(TypeStyle(size: 12, lineHeight: 17, weight: .regular).font)
                .foregroundColor(OmiColor.hex(0x888888))
            HStack(spacing: 8) {
                choice("GPT Live 1", value: .gptLive)
                choice("Gemini Live", value: .geminiLive)
            }
        }
        .padding(.top, Space.lg)
    }

    private func choice(_ label: String, value: LiveVoiceProvider) -> some View {
        let isSelected = provider == value
        return Button(action: {
            Task { await store.setPreference("liveVoiceProvider", PreferenceValue.string(value.rawValue)) }
        }) {
            Text(label)
                .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                .foregroundColor(Color.white)
                .frame(minHeight: 44)
                .padding(.horizontal, Space.md)
                .background(isSelected ? MobilePalette.surfaceRaised : Palette.input)
                .overlay(
                    RoundedRectangle(cornerRadius: Radius.md)
                        .strokeBorder(
                            isSelected ? MobilePalette.textMuted : Palette.line,
                            lineWidth: Borders.width
                        )
                )
                .clipShape(RoundedRectangle(cornerRadius: Radius.md))
        }
        .buttonStyle(KitPressableStyle())
        .accessibilityLabel("Use \(label)")
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }
}
