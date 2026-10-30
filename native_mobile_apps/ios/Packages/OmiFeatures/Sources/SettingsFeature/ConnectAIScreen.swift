import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Connections › Connect your AI (docs/VISION.md, "Die Brücke zur eigenen KI"): Claude, ChatGPT or
/// any other MCP client reads what Omi knows. Claude and ChatGPT sign in to Omi themselves (no key
/// to copy); other assistants get their own MCP key, created right here. The raw API and MCP keys
/// stay in Developer.
struct ConnectAIScreen: View {
    @Environment(DeveloperStore.self) private var developer
    @Environment(\.openURL) private var openURL
    /// `-omiConnectAITarget claude|chatGPT|other` (Debug) opens on that assistant.
    @State private var target = DebugLaunch.string("omiConnectAITarget").flatMap(Target.init(rawValue:)) ?? .claude
    @State private var copied: String?
    @State private var isCreating = false
    @State private var createFailed = false

    enum Target: String, CaseIterable, Identifiable {
        case claude, chatGPT, other
        var id: String { rawValue }

        var title: String {
            switch self {
            case .claude: "Claude"
            case .chatGPT: "ChatGPT"
            case .other: L("nativeConnectAIOther")
            }
        }
    }

    var body: some View {
        SettingsList {
            Section {
                Text(L("nativeConnectAIIntro"))
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .plainSettingsRow(inset: DS.Spacing.lg)
                Picker(L("nativeConnectAI"), selection: $target) {
                    ForEach(Target.allCases) { Text($0.title).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .plainSettingsRow()
                .padding(.top, DS.Spacing.lg)
                .accessibilityIdentifier("connectAI.target")
            }
            Section {
                steps
            } header: {
                SettingsHeader(L("nativeConnectAISteps"))
            } footer: {
                if target == .other { Text(L("nativeConnectAIKeyFooter")) }
            }
            Section {
                primaryAction.plainSettingsRow()
            }
        }
        .omiPage(L("nativeConnectAI"))
        .animation(DS.Motion.gentle, value: target)
        .onChange(of: target) { _, _ in copied = nil }
        // The secret is shown once: it does not stay in memory after the screen.
        .onDisappear { if developer.createdKeyKind == .mcp { developer.createdKey = nil } }
        .alert(L("nativeConnectAIFailed"), isPresented: $createFailed) {
            Button(L("ok"), role: .cancel) {}
        }
        .task {
            // -omiConnectAICreateKey YES (Debug, with the "other" target): creates the key right away.
            guard DebugLaunch.flag("omiConnectAICreateKey"), target == .other, createdSecret == nil else { return }
            await createKey()
        }
    }

    private func createKey() async {
        isCreating = true
        createFailed = !(await developer.createKey(.mcp, name: L("nativeConnectAIKeyName")))
        isCreating = false
    }

    /// The MCP key just created here (its secret, once).
    private var createdSecret: String? {
        developer.createdKeyKind == .mcp ? developer.createdKey?.secret : nil
    }

    private var address: String {
        developer.mcpServerURL.absoluteString
    }

    @ViewBuilder
    private var steps: some View {
        switch target {
        case .claude:
            step(1, L("nativeConnectAIClaudeStep1"))
            copyRow(L("nativeConnectAIAddress"), value: address, id: "address")
            step(2, L("nativeConnectAIClaudeStep2"))
            step(3, L("nativeConnectAIClaudeStep3"))
        case .chatGPT:
            step(1, L("nativeConnectAIChatGPTStep1"))
            step(2, L("nativeConnectAIChatGPTStep2"))
            step(3, L("nativeConnectAIChatGPTStep3"))
        case .other:
            step(1, L("nativeConnectAIOtherStep1"))
            if let secret = createdSecret {
                copyRow(L("nativeConnectAIKey"), value: secret, id: "key")
            }
            step(2, L("nativeConnectAIOtherStep2"))
            copyRow(L("nativeConnectAIAddress"), value: address, id: "address")
            if let secret = createdSecret {
                copyRow(L("nativeConnectAISetup"), value: developer.mcpConfig(key: secret), id: "config", shown: "JSON")
            }
        }
    }

    /// The screen's one action: open the assistant, or create the key (then copy its setup).
    @ViewBuilder
    private var primaryAction: some View {
        switch target {
        case .claude:
            Button(L("nativeConnectAIOpenClaude")) { openURL(Self.claudeURL) }
                .buttonStyle(.omiPrimary)
                .accessibilityIdentifier("connectAI.open")
        case .chatGPT:
            Button(L("nativeConnectAIOpenChatGPT")) { openURL(Self.chatGPTURL) }
                .buttonStyle(.omiPrimary)
                .accessibilityIdentifier("connectAI.open")
        case .other:
            if let secret = createdSecret {
                Button(copied == "config" ? L("copied") : L("nativeConnectAICopySetup")) {
                    copy(developer.mcpConfig(key: secret), id: "config")
                }
                .buttonStyle(.omiPrimary)
            } else {
                Button {
                    Task { await createKey() }
                } label: {
                    if isCreating { ProgressView() } else { Text(L("nativeConnectAICreateKey")) }
                }
                .buttonStyle(.omiPrimary)
                .disabled(isCreating)
                .accessibilityIdentifier("connectAI.createKey")
            }
        }
    }

    /// A numbered step: the number in quiet gray, then one sentence.
    private func step(_ number: Int, _ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
            Text(verbatim: "\(number)")
                .font(DS.Typography.body.monospacedDigit())
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(width: 18, alignment: .leading)
            Text(text)
                .font(DS.Typography.body)
                .foregroundStyle(DS.Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, DS.Spacing.xxs)
        .accessibilityElement(children: .combine)
    }

    /// A value to copy: its name, the value (shortened in the middle) and a copy glyph.
    private func copyRow(_ title: String, value: String, id: String, shown: String? = nil) -> some View {
        Button { copy(value, id: id) } label: {
            HStack(spacing: DS.Spacing.md) {
                Text(title).foregroundStyle(DS.Palette.ink)
                Spacer(minLength: DS.Spacing.sm)
                Text(shown ?? value)
                    .font(DS.Typography.callout.monospaced())
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Image(systemName: copied == id ? "checkmark" : "doc.on.doc")
                    .font(.system(size: 15, weight: .regular))
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .contentTransition(.symbolEffect(.replace))
            }
            .padding(.leading, 18 + DS.Spacing.md)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(copied == id ? L("copied") : "\(L("copy")) \(title)")
        .accessibilityIdentifier("connectAI.copy.\(id)")
    }

    private func copy(_ text: String, id: String) {
        UIPasteboard.general.string = text
        DSHaptics.success()
        copied = id
    }

    /// Claude's connector settings (the app opens it when installed).
    static let claudeURL = URL(string: "https://claude.ai/settings/connectors")!
    /// ChatGPT's apps settings.
    static let chatGPTURL = URL(string: "https://chatgpt.com/#settings/Connectors")!
}
