import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// "Recordings of this conversation": the same moment recorded by other devices (Flutter
/// `capture_recordings`). Tap one to open it; "Separate…" makes it its own conversation for good.
struct CaptureRecordingsSheet: View {
    let store: ConversationDetailStore
    let onOpen: (CaptureRecording) -> Void
    @Environment(ConversationsStore.self) private var conversations
    @Environment(\.dismiss) private var dismiss
    @State private var separating: CaptureRecording?
    @State private var working: String?
    @State private var failed: String?

    var body: some View {
        NavigationStack {
            List {
                ForEach(store.detail?.recordings ?? []) { recording in
                    row(recording)
                }
            }
            .navigationTitle(L("captureRecordingsSheetTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("done")) { dismiss() } } }
            .alert(
                L("captureRecordingSeparateTitle"),
                isPresented: Binding(get: { separating != nil }, set: { if !$0 { separating = nil } }),
                presenting: separating
            ) { recording in
                Button(L("cancel"), role: .cancel) {}
                Button(L("captureRecordingSeparateConfirm"), role: .destructive) { separate(recording) }
            } message: { recording in
                Text(L("captureRecordingSeparateMessage", Self.label(recording)))
            }
        }
    }

    private func row(_ recording: CaptureRecording) -> some View {
        Button {
            if !recording.isCurrent { onOpen(recording) }
        } label: {
            HStack(spacing: DS.Spacing.md) {
                Image(systemName: Self.symbol(recording.source)).foregroundStyle(DS.Palette.inkSecondary).frame(width: 24)
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    Text(Self.label(recording)).font(DS.Typography.cardTitle).foregroundStyle(DS.Palette.ink)
                    if recording.isCurrent {
                        Text(L("captureRecordingViewing")).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                    } else if failed == recording.id {
                        Text(L("captureRecordingSeparateFailed")).font(DS.Typography.caption).foregroundStyle(DS.Palette.live)
                    }
                }
                Spacer(minLength: 0)
                if recording.isCurrent {
                    Image(systemName: "checkmark").foregroundStyle(DS.Palette.agent)
                } else if working == recording.id {
                    ProgressView().controlSize(.small)
                } else {
                    Button(L("captureRecordingSeparate")) { separating = recording }
                        .buttonStyle(.omiPillSubtle)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(working != nil)
    }

    private func separate(_ recording: CaptureRecording) {
        working = recording.id
        failed = nil
        Task {
            if await store.separate(recording, in: conversations) {
                dismiss()
            } else {
                failed = recording.id
            }
            working = nil
        }
    }

    /// "Desktop · 13:57 – 14:59".
    static func label(_ recording: CaptureRecording) -> String {
        var time = recording.start?.formatted(date: .omitted, time: .shortened) ?? ""
        if let end = recording.end, recording.start != nil { time += " – \(end.formatted(date: .omitted, time: .shortened))" }
        return [source(recording.source), time].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    static func source(_ source: String?) -> String {
        switch source {
        case "phone", "phone_call": "iPhone"
        case "apple_watch": "Apple Watch"
        case "desktop", "screenpipe": "Desktop"
        case nil, "": "Omi"
        case let other?: other.prefix(1).uppercased() + other.dropFirst().replacingOccurrences(of: "_", with: " ")
        }
    }

    static func symbol(_ source: String?) -> String {
        switch source {
        case "phone", "phone_call": "iphone"
        case "apple_watch": "applewatch"
        case "desktop", "screenpipe": "desktopcomputer"
        default: "waveform"
        }
    }
}

/// Developer › "Test a Conversation Prompt": runs a prompt over this transcript once and shows
/// the result; nothing is saved (Flutter `test_prompts.dart`).
struct TestPromptSheet: View {
    let store: ConversationDetailStore
    @Environment(\.dismiss) private var dismiss
    @State private var prompt = ""
    @State private var result: String?
    @State private var running = false
    @State private var failed = false
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: DS.Spacing.lg) {
                    TextField(L("prompt"), text: $prompt, axis: .vertical)
                        .lineLimit(4 ... 12)
                        .focused($focused)
                        .omiField()
                        .accessibilityIdentifier("testPrompt.field")
                    if failed {
                        Text(L("somethingWentWrong")).font(DS.Typography.callout).foregroundStyle(DS.Palette.live)
                    }
                    if let result, !result.isEmpty {
                        Text(L("result")).font(DS.Typography.sectionTitle)
                        Text(result).font(DS.Typography.body).textSelection(.enabled)
                    }
                }
                .padding(DS.Spacing.gutter)
            }
            .background(DS.Palette.background)
            .navigationTitle(L("testConversationPrompt"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    if running {
                        ProgressView()
                    } else {
                        Button { run() } label: { Image(systemName: "paperplane.fill") }
                            .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            .accessibilityLabel(L("send"))
                            .accessibilityIdentifier("testPrompt.send")
                    }
                }
            }
            .onAppear { focused = true }
        }
    }

    private func run() {
        running = true
        failed = false
        focused = false
        Task {
            let summary = await store.testPrompt(prompt)
            result = summary
            failed = summary == nil
            running = false
        }
    }
}
