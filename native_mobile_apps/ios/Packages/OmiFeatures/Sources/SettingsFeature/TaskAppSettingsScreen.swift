import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// One connected task app (Flutter `todoist/asana/clickup/google_tasks_settings_page`): whether new
/// tasks go here, where in it (Asana workspace and project, ClickUp team, space and list), disconnect.
struct TaskAppSettingsScreen: View {
    @Environment(TaskAppSettingsStore.self) private var settings
    @Environment(CapabilitiesStore.self) private var capabilities
    @Environment(\.dismiss) private var dismiss
    let integration: Integration
    @State private var confirmsDisconnect = false

    var body: some View {
        let app = integration.id
        SettingsList {
            Section {
                Toggle(L("nativeTaskAppDefault"), isOn: Binding(
                    get: { settings.defaultApp == app },
                    set: { on in if on { Task { await settings.makeDefault(app) } } }
                ))
                .disabled(settings.defaultApp == app)
            } footer: {
                Text(L("nativeTaskAppDefaultFooter"))
            }
            let levels = TaskAppLevel.levels(for: app)
            if !levels.isEmpty {
                Section {
                    ForEach(levels, id: \.self) { level in
                        picker(app, level: level)
                    }
                } header: {
                    SettingsHeader(L("nativeTaskAppWhere"))
                } footer: {
                    Text(L("nativeTaskAppWhereFooter"))
                }
            } else if app == "google_tasks" {
                Section { Text(L("nativeTaskAppGoogleList")).foregroundStyle(DS.Palette.inkSecondary) }
            }
            Section {
                Button(L("nativeDisconnect"), role: .destructive) { confirmsDisconnect = true }
            }
        }
        .omiPage(CapabilitiesList.name(app))
        .task { await settings.load(app) }
        .confirmationDialog(L("nativeTaskAppDisconnectQuestion", CapabilitiesList.name(app)), isPresented: $confirmsDisconnect,
                            titleVisibility: .visible) {
            Button(L("nativeDisconnect"), role: .destructive) {
                Task {
                    await capabilities.disconnect(integration)
                    settings.forget(app)
                    dismiss()
                }
            }
        }
    }

    @ViewBuilder
    private func picker(_ app: String, level: TaskAppLevel) -> some View {
        let options = settings.options[level] ?? []
        let selected = settings.selection[app]?[level]
        if settings.loading.contains(level) {
            LabeledContent(Self.title(level)) { ProgressView() }
        } else if options.isEmpty, selected == nil {
            LabeledContent(Self.title(level), value: "–")
                .foregroundStyle(DS.Palette.inkTertiary)
        } else {
            Picker(Self.title(level), selection: Binding(
                get: { selected?.id },
                set: { id in
                    let option = options.first { $0.id == id }
                    Task { await settings.select(app, level: level, option: option) }
                }
            )) {
                Text(L("nativeTaskAppNone")).tag(String?.none)
                // A saved choice whose list has not loaded yet still shows by name.
                if let selected, !options.contains(selected) { Text(selected.name).tag(Optional(selected.id)) }
                ForEach(options) { Text($0.name).tag(Optional($0.id)) }
            }
        }
    }

    static func title(_ level: TaskAppLevel) -> String {
        switch level {
        case .asanaWorkspace: L("nativeTaskAppWorkspace")
        case .asanaProject: L("nativeTaskAppProject")
        case .clickupTeam: L("nativeTaskAppTeam")
        case .clickupSpace: L("nativeTaskAppSpace")
        case .clickupList: L("nativeTaskAppList")
        }
    }
}
