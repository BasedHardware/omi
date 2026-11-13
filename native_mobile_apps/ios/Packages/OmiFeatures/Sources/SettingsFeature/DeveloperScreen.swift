import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Settings › Developer (Flutter `developer.dart`): your user ID, webhooks, API and MCP keys, the
/// experimental switches, logs and docs. Shown once Developer mode is on in Help.
struct DeveloperScreen: View {
    @Environment(DeveloperStore.self) private var developer
    @Environment(SessionStore.self) private var session
    @State private var copiedID = false

    var body: some View {
        @Bindable var developer = developer
        SettingsList {
            if let uid = session.userID {
                Section {
                    Button {
                        UIPasteboard.general.string = uid
                        DSHaptics.success()
                        copiedID = true
                    } label: {
                        LabeledContent(L("userId")) {
                            HStack(spacing: DS.Spacing.xs) {
                                Text(Self.shortened(uid)).monospaced()
                                Image(systemName: copiedID ? "checkmark" : "doc.on.doc")
                            }
                            .foregroundStyle(DS.Palette.inkSecondary)
                        }
                        .foregroundStyle(DS.Palette.ink)
                    }
                    .accessibilityLabel(L("nativeCopyUserID"))
                    .accessibilityIdentifier("account.copyUserID")
                }
            }
            Section {
                NavigationLink { WebhooksScreen() } label: {
                    SettingsRowLabel(
                        title: L("nativeDevWebhooks"), systemImage: "arrow.triangle.branch",
                        value: enabledWebhooks == 0 ? nil : String(enabledWebhooks)
                    )
                }
                .accessibilityIdentifier("developer.webhooks")
                NavigationLink { DeveloperKeysScreen(kind: .api) } label: {
                    SettingsRowLabel(
                        title: L("nativeDevAPIKeys"), systemImage: "key",
                        value: developer.apiKeys.isEmpty ? nil : String(developer.apiKeys.count)
                    )
                }
                .accessibilityIdentifier("developer.apiKeys")
                NavigationLink { DeveloperKeysScreen(kind: .mcp) } label: {
                    SettingsRowLabel(
                        title: L("nativeDevMCP"), systemImage: "server.rack",
                        value: developer.mcpKeys.isEmpty ? nil : String(developer.mcpKeys.count)
                    )
                }
                .accessibilityIdentifier("developer.mcp")
            }
            Section {
                Toggle(L("nativeDevConversationTools"), isOn: $developer.showsConversationTools)
                Toggle(L("nativeDevVADGate"), isOn: $developer.vadGate)
            } header: {
                SettingsHeader(L("nativeDevExperimental"))
            } footer: {
                Text(L("nativeDevExperimentalFooter"))
            }
            Section {
                NavigationLink { DeveloperLogsScreen() } label: {
                    SettingsRowLabel(title: L("nativeDevLogs"), systemImage: "list.bullet.rectangle")
                }
                Link(L("nativeDevAppsDocs"), destination: URL(string: "https://docs.omi.me/doc/developer/apps/Introduction")!)
                Link(L("nativeDevMCPDocs"), destination: URL(string: "https://docs.omi.me/doc/developer/MCP")!)
            }
        }
        .omiPage(L("nativeDeveloper"))
        .task { await developer.load() }
    }

    private var enabledWebhooks: Int {
        developer.webhooks.values.count(where: \.isEnabled)
    }

    /// `abc•••••xyz`, as Flutter shows it; the full id is copied.
    static func shortened(_ uid: String) -> String {
        uid.count > 10 ? "\(uid.prefix(3))•••••\(uid.suffix(3))" : uid
    }

    static func title(_ hook: DeveloperWebhook) -> String {
        switch hook {
        case .conversationCreated: L("nativeDevHookConversation")
        case .realtimeTranscript: L("nativeDevHookTranscript")
        case .audioBytes: L("nativeDevHookAudio")
        case .daySummary: L("nativeDevHookDaySummary")
        }
    }
}

/// Developer › Webhooks: the four webhooks; edits are saved together (or discarded on the way out).
struct WebhooksScreen: View {
    @Environment(DeveloperStore.self) private var developer
    @Environment(\.dismiss) private var dismiss
    @State private var confirmsDiscard = false

    var body: some View {
        SettingsList {
            Section {
                ForEach(DeveloperWebhook.allCases) { hook in
                    WebhookRow(hook: hook)
                }
            } footer: {
                Text(L("nativeDevWebhooksFooter"))
            }
        }
        .omiPage(L("nativeDevWebhooks"))
        .navigationBarBackButtonHidden(developer.hasUnsavedWebhooks)
        .toolbar {
            if developer.hasUnsavedWebhooks {
                ToolbarItem(placement: .topBarLeading) {
                    Button(L("cancel")) { confirmsDiscard = true }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("save")) { Task { await developer.saveWebhooks() } }
                        .disabled(developer.isSaving)
                        .accessibilityIdentifier("developer.save")
                }
            }
        }
        .confirmationDialog(L("nativeDevDiscardQuestion"), isPresented: $confirmsDiscard, titleVisibility: .visible) {
            Button(L("nativeDevDiscard"), role: .destructive) {
                developer.discardWebhookEdits()
                dismiss()
            }
            Button(L("cancel"), role: .cancel) {}
        }
        .alert(failureText ?? "", isPresented: Binding(get: { developer.failure != nil }, set: { if !$0 { developer.failure = nil } })) {
            Button(L("ok"), role: .cancel) {}
        }
    }

    private var failureText: String? {
        switch developer.failure {
        case let .invalidURL(hook): L("nativeDevInvalidURL", DeveloperScreen.title(hook))
        case .couldNotSave: L("nativeDevCouldNotSave")
        case .couldNotLoad: L("nativeDevCouldNotLoad")
        case nil: nil
        }
    }
}

/// Developer › API keys or MCP: the keys of one kind.
private struct DeveloperKeysScreen: View {
    let kind: DeveloperKey.Kind

    var body: some View {
        SettingsList {
            DeveloperKeysSection(kind: kind)
        }
        .omiPage(kind == .api ? L("nativeDevAPIKeys") : L("nativeDevMCP"))
    }
}

/// Developer › Logs: writing the log to a file, sharing it, the recent events, clearing.
struct DeveloperLogsScreen: View {
    @Environment(DebugLog.self) private var log

    var body: some View {
        @Bindable var log = log
        SettingsList {
            Section {
                Toggle(L("nativeDevLogToFile"), isOn: $log.writesToFile)
                if let file = log.files.first {
                    ShareLink(item: file) { Label(L("nativeDevShareLog"), systemImage: "square.and.arrow.up") }
                }
                NavigationLink(L("nativeDevRecentEvents")) { DebugLogScreen(source: nil) }
            } footer: {
                Text(L("nativeDevLogsFooter"))
            }
            Section {
                Button(L("nativeDevClearLog"), role: .destructive) { log.clear() }
                    .disabled(log.entries.isEmpty && log.files.isEmpty)
            }
        }
        .omiPage(L("nativeDevLogs"))
    }
}

/// One webhook: its switch (once a URL is saved), the URL, and for audio the interval.
private struct WebhookRow: View {
    @Environment(DeveloperStore.self) private var developer
    let hook: DeveloperWebhook

    var body: some View {
        let webhook = developer.webhooks[hook] ?? .init()
        VStack(alignment: .leading, spacing: DS.Spacing.xs) {
            Toggle(DeveloperScreen.title(hook), isOn: Binding(
                get: { webhook.isEnabled },
                set: { value in Task { await developer.setEnabled(hook, value) } }
            ))
            .disabled(webhook.savedURL.isEmpty)
            TextField("https://", text: Binding(get: { webhook.url }, set: { developer.edit(hook, url: $0) }))
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.URL)
                .font(DS.Typography.callout)
                .accessibilityIdentifier("developer.webhook.\(hook.rawValue)")
            if hook == .audioBytes {
                Stepper(
                    L("nativeDevAudioInterval", String(webhook.seconds)),
                    value: Binding(get: { webhook.seconds }, set: { developer.edit(hook, seconds: $0) }),
                    in: 1 ... 300
                )
                .font(DS.Typography.callout)
            }
        }
        .padding(.vertical, DS.Spacing.xxs)
    }
}

/// The recent log entries, newest first; `source` narrows it (the transcription log).
struct DebugLogScreen: View {
    @Environment(DebugLog.self) private var log
    let source: String?

    var body: some View {
        let entries = (source.map { log.entries(from: $0) } ?? log.entries).reversed()
        List(Array(entries)) { entry in
            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                HStack {
                    Text(entry.level.rawValue)
                        .font(DS.Typography.caption.weight(.semibold))
                        .foregroundStyle(entry.level == .info ? DS.Palette.inkSecondary : DS.Palette.live)
                    Text(entry.source).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkTertiary)
                    Spacer()
                    Text(entry.date.formatted(date: .omitted, time: .standard))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                }
                Text(entry.message).font(DS.Typography.callout).textSelection(.enabled)
            }
        }
        .overlay {
            if entries.isEmpty { ContentUnavailableView(L("nativeDevNoEvents"), systemImage: "list.bullet.rectangle") }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(L("copy")) { UIPasteboard.general.string = DebugLog.text(Array(entries.reversed())) }
                    .disabled(entries.isEmpty)
            }
        }
        .omiPage(source == "stt" ? L("nativeTranscriptionLog") : L("nativeDevRecentEvents"))
    }
}
