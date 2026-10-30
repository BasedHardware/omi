import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Developer API keys or MCP keys: the list (prefix and date), create, revoke; a new key's secret is
/// shown once, with the MCP config to copy.
struct DeveloperKeysSection: View {
    @Environment(DeveloperStore.self) private var developer
    let kind: DeveloperKey.Kind
    @State private var naming = false
    @State private var name = ""
    @State private var fullAccess = false
    @State private var revoking: DeveloperKey?

    var body: some View {
        let keys = kind == .api ? developer.apiKeys : developer.mcpKeys
        Section {
            if kind == .mcp {
                LabeledContent(L("nativeDevMCPServer")) {
                    Button(developer.mcpServerURL.absoluteString) { UIPasteboard.general.string = developer.mcpServerURL.absoluteString }
                        .font(DS.Typography.caption)
                        .lineLimit(1)
                }
            }
            ForEach(keys) { key in
                VStack(alignment: .leading, spacing: 2) {
                    Text(key.name).font(DS.Typography.body)
                    Text("\(key.prefix) · \(key.createdAt?.formatted(date: .abbreviated, time: .omitted) ?? "")")
                        .font(DS.Typography.caption.monospaced())
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
                .swipeActions {
                    Button(L("nativeDevRevoke"), role: .destructive) { revoking = key }
                }
                .contextMenu {
                    Button(L("nativeDevRevoke"), systemImage: "trash", role: .destructive) { revoking = key }
                }
            }
            Button(kind == .api ? L("nativeDevNewAPIKey") : L("nativeDevNewMCPKey")) {
                name = ""
                fullAccess = false
                naming = true
            }
            .accessibilityIdentifier("developer.newKey.\(kind.rawValue)")
        } header: {
            SettingsHeader(kind == .api ? L("nativeDevAPIKeys") : L("nativeDevMCP"))
        } footer: {
            Text(kind == .api ? L("nativeDevAPIKeysFooter") : L("nativeDevMCPFooter"))
        }
        .sheet(isPresented: $naming) { createSheet }
        .sheet(item: Binding(
            get: { developer.createdKeyKind == kind ? developer.createdKey : nil },
            set: { if $0 == nil { developer.createdKey = nil } }
        )) { key in CreatedKeySheet(key: key, kind: kind) }
        .confirmationDialog(
            L("nativeDevRevokeQuestion", revoking?.name ?? ""),
            isPresented: Binding(get: { revoking != nil }, set: { if !$0 { revoking = nil } }),
            titleVisibility: .visible
        ) {
            Button(L("nativeDevRevoke"), role: .destructive) {
                if let key = revoking { Task { await developer.revoke(kind, id: key.id) } }
            }
        } message: {
            Text(L("nativeDevRevokeWarning"))
        }
    }

    private var createSheet: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(L("nativeDevKeyName"), text: $name)
                        .accessibilityIdentifier("developer.keyName")
                    if kind == .api {
                        Toggle(L("nativeDevFullAccess"), isOn: $fullAccess)
                    }
                } footer: {
                    Text(kind == .api ? L("nativeDevFullAccessFooter") : L("nativeDevMCPKeyFooter"))
                }
            }
            .navigationTitle(kind == .api ? L("nativeDevNewAPIKey") : L("nativeDevNewMCPKey"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { naming = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("nativeDevCreate")) {
                        Task {
                            if await developer.createKey(kind, name: name, fullAccess: fullAccess) { naming = false }
                        }
                    }
                    .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }
}

/// The secret, once: copy it (and for MCP the client config).
private struct CreatedKeySheet: View {
    @Environment(DeveloperStore.self) private var developer
    @Environment(\.dismiss) private var dismiss
    let key: DeveloperKey
    let kind: DeveloperKey.Kind
    @State private var copied: String?

    var body: some View {
        NavigationStack {
            SettingsList {
                Section {
                    Text(key.secret ?? key.prefix)
                        .font(DS.Typography.callout.monospaced())
                        .textSelection(.enabled)
                    copyButton(L("nativeDevCopyKey"), text: key.secret ?? "", id: "key")
                } footer: {
                    Text(L("nativeDevKeyShownOnce"))
                }
                if kind == .mcp, let secret = key.secret {
                    Section {
                        Text(developer.mcpConfig(key: secret))
                            .font(DS.Typography.caption.monospaced())
                            .textSelection(.enabled)
                        copyButton(L("nativeDevCopyConfig"), text: developer.mcpConfig(key: secret), id: "config")
                    } header: {
                        SettingsHeader(L("nativeDevMCPConfig"))
                    } footer: {
                        Text(L("nativeDevMCPConfigFooter"))
                    }
                }
            }
            .navigationTitle(key.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button(L("done")) { dismiss() } }
            }
        }
        .interactiveDismissDisabled()
    }

    private func copyButton(_ title: String, text: String, id: String) -> some View {
        Button {
            UIPasteboard.general.string = text
            copied = id
        } label: {
            Label(copied == id ? L("copied") : title, systemImage: copied == id ? "checkmark" : "doc.on.doc")
        }
    }
}
