import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// "Summary template": which app summarizes this conversation. Tap an app to summarize again
/// with it; swipe (or long-press) to make it the default for future conversations; "Create custom
/// template" writes a new one (Flutter `summarized_apps_sheet`, `create_template_bottom_sheet`).
struct SummaryTemplateSheet: View {
    let templates: SummaryTemplatesStore
    let detail: ConversationDetailStore
    @Environment(ConversationsStore.self) private var conversations
    @Environment(\.dismiss) private var dismiss
    @State private var makingDefault: OmiApp?
    @State var creating = false

    var body: some View {
        NavigationStack {
            List {
                if templates.phase == .loading {
                    Section { ForEach(0 ..< 3, id: \.self) { _ in SkeletonBlock(height: 44).listRowBackground(Color.clear) } }
                } else {
                    if !templates.suggested.isEmpty {
                        Section(L("suggestedTemplates")) { ForEach(templates.suggested) { row($0) } }
                    }
                    if !templates.apps.isEmpty {
                        Section(templates.suggested.isEmpty ? L("availableTemplates") : L("otherTemplates")) {
                            ForEach(templates.apps) { row($0) }
                        }
                    }
                    Section(L("getCreative")) {
                        Button { creating = true } label: { Label(L("createCustomTemplate"), systemImage: "plus.circle") }
                            .accessibilityIdentifier("templates.create")
                    }
                }
            }
            .navigationTitle(L("summaryTemplate"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } } }
            .navigationDestination(isPresented: $creating) {
                CreateTemplateForm(templates: templates) { creating = false }
            }
            .task { if templates.phase == .loading { await templates.load(conversationID: detail.conversation.id) } }
            .alert(L("setDefaultApp"), isPresented: Binding(get: { makingDefault != nil }, set: { if !$0 { makingDefault = nil } })) {
                Button(L("cancel"), role: .cancel) {}
                Button(L("setDefaultButton")) {
                    if let app = makingDefault { Task { await templates.setDefault(app) } }
                }
            } message: {
                Text(L("setDefaultAppContent", makingDefault?.name ?? ""))
            }
            .alert(failureTitle, isPresented: Binding(get: { templates.failure != nil }, set: { if !$0 { templates.failure = nil } })) {
                Button(L("ok"), role: .cancel) {}
            }
        }
    }

    private func row(_ app: OmiApp) -> some View {
        Button {
            DSHaptics.tap()
            Task { if await templates.summarize(detail, with: app, in: conversations) { dismiss() } }
        } label: {
            HStack(spacing: DS.Spacing.md) {
                AppIcon(app: app)
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    HStack(spacing: DS.Spacing.xs) {
                        Text(app.name).font(DS.Typography.cardTitle).foregroundStyle(DS.Palette.ink)
                        if app.id == templates.defaultAppID {
                            tag(L("defaultLabel"), systemImage: "star.fill")
                        } else if app.id == templates.lastUsedAppID {
                            tag(L("lastUsedLabel"), systemImage: "clock")
                        }
                    }
                    if !app.description.isEmpty {
                        Text(app.description).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary).lineLimit(2)
                    }
                }
                Spacer(minLength: 0)
                if templates.working == app.id {
                    ProgressView().controlSize(.small)
                } else if app.id == detail.detail?.summaryAppID {
                    Image(systemName: "checkmark").foregroundStyle(DS.Palette.agent).accessibilityLabel(L("nativeSelected"))
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(templates.working != nil)
        .swipeActions(edge: .trailing) { defaultAction(app) }
        .swipeActions(edge: .leading) { defaultAction(app) }
        .contextMenu { defaultAction(app) }
    }

    @ViewBuilder
    private func defaultAction(_ app: OmiApp) -> some View {
        if app.id != templates.defaultAppID, templates.apps.contains(where: { $0.id == app.id }) {
            Button { makingDefault = app } label: { Label(L("setDefaultButton"), systemImage: "star") }.tint(DS.Palette.warning)
        }
    }

    private func tag(_ title: String, systemImage: String) -> some View {
        Label(title, systemImage: systemImage)
            .font(DS.Typography.micro)
            .foregroundStyle(DS.Palette.agent)
            .padding(.horizontal, DS.Spacing.xs + 2)
            .padding(.vertical, 2)
            .background(DS.Palette.agentSoft, in: Capsule())
    }

    private var failureTitle: String {
        switch templates.failure {
        case let .install(name): L("failedToInstallApp", name)
        case .saveDefault: L("failedToSaveCheckConnection")
        case .create: L("failedToCreateApp")
        case .reprocess, nil: L("nativeSummaryFailed")
        }
    }
}

/// An app's picture, or its initial on a tinted square.
struct AppIcon: View {
    let app: OmiApp

    var body: some View {
        Group {
            if let url = app.imageURL {
                AsyncImage(url: url) { image in image.resizable().scaledToFill() } placeholder: { placeholder }
            } else {
                placeholder
            }
        }
        .frame(width: 36, height: 36)
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        .accessibilityHidden(true)
    }

    private var placeholder: some View {
        Text(String(app.name.prefix(1)).uppercased())
            .font(.headline)
            .foregroundStyle(DS.Palette.agent)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(DS.Palette.agentSoft)
    }
}

/// "Create custom template": a name and the prompt the app runs on each conversation, private
/// unless made public. Omi picks the description and icon; the app is installed right away.
struct CreateTemplateForm: View {
    let templates: SummaryTemplatesStore
    let onDone: () -> Void
    @State private var draft = SummaryTemplateDraft(name: "", prompt: "")
    @State private var tried = false

    var body: some View {
        Form {
            Section {
                TextField(L("templateNameHint"), text: $draft.name)
                    .accessibilityIdentifier("template.name")
            } header: { Text(L("templateName")) } footer: { problemText(for: [.nameMissing, .nameTooShort]) }
            Section {
                TextField(L("conversationPromptHint"), text: $draft.prompt, axis: .vertical)
                    .lineLimit(4 ... 8)
                    .accessibilityIdentifier("template.prompt")
            } header: { Text(L("conversationPrompt")) } footer: { problemText(for: [.promptMissing, .promptTooShort]) }
            Section {
                Toggle(isOn: $draft.isPublic) {
                    VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                        Text(L("makePublic"))
                        Text(draft.isPublic ? L("anyoneCanDiscoverTemplate") : L("onlyYouCanUseTemplate"))
                            .font(DS.Typography.caption)
                            .foregroundStyle(DS.Palette.inkSecondary)
                    }
                }
            }
        }
        .navigationTitle(L("createCustomTemplate"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                if let step = templates.creationStep {
                    HStack(spacing: DS.Spacing.xs) {
                        ProgressView().controlSize(.small)
                        Text(stepText(step)).font(DS.Typography.caption)
                    }
                } else {
                    Button(L("createApp")) { create() }.accessibilityIdentifier("template.save")
                }
            }
        }
    }

    @ViewBuilder
    private func problemText(for problems: [SummaryTemplateDraft.Problem]) -> some View {
        if tried, let problem = draft.problem, problems.contains(problem) {
            Text(text(problem)).foregroundStyle(DS.Palette.live)
        }
    }

    private func create() {
        tried = true
        guard draft.problem == nil else { return }
        Task {
            if await templates.create(draft, icon: Self.icon) != nil { onDone() }
        }
    }

    private func text(_ problem: SummaryTemplateDraft.Problem) -> String {
        switch problem {
        case .nameMissing: L("pleaseEnterAppName")
        case .nameTooShort: L("nameMustBeAtLeast3Characters")
        case .promptMissing: L("pleaseEnterAppPrompt")
        case .promptTooShort: L("promptMustBeAtLeast10Characters")
        }
    }

    private func stepText(_ step: SummaryTemplatesStore.CreationStep) -> String {
        switch step {
        case .describing: L("generatingDescription")
        case .creating: L("creatingYourApp")
        case .installing: L("installingApp")
        }
    }

    /// The emoji on white, 256 points square, as the app's icon (Flutter draws the same).
    @MainActor
    static func icon(_ emoji: String) -> Data? {
        let renderer = ImageRenderer(
            content: Text(emoji).font(.system(size: 160)).frame(width: 256, height: 256).background(Color.white)
        )
        renderer.scale = 1
        #if canImport(UIKit)
            return renderer.uiImage?.pngData()
        #else
            return nil
        #endif
    }
}
