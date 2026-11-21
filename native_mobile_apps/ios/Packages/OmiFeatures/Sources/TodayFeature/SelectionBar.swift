import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// While selecting conversations: how many, then move, merge, delete, done.
struct SelectionBar: View {
    @Environment(ConversationsStore.self) private var conversations
    @Binding var selection: Set<String>?
    @State private var moving: MoveRequest?
    @State private var confirmsMerge = false
    @State private var message: String?

    var body: some View {
        VStack(spacing: DS.Spacing.sm) {
            if let message {
                OmiToast(text: message, systemImage: "arrow.triangle.merge").transition(.opacity)
            }
            HStack(spacing: DS.Spacing.lg) {
                Text(L("selectedCount", String(ids.count)))
                    .font(DS.Typography.callout.weight(.semibold))
                    .monospacedDigit()
                Spacer(minLength: 0)
                icon("folder", L("moveToFolder")) { moving = MoveRequest(ids: ids) }
                icon("arrow.triangle.merge", L("merge")) { confirmsMerge = true }
                icon("trash", L("deleteSelected"), tint: DS.Palette.live) {
                    DSHaptics.tap(.medium)
                    withAnimation(DS.Motion.standard) { conversations.deleteWithUndo(ids) }
                    selection = nil
                }
                Button(L("done")) { withAnimation(DS.Motion.standard) { selection = nil } }
                    .font(DS.Typography.callout.weight(.semibold))
                    .accessibilityIdentifier("selection.done")
            }
            .padding(.horizontal, DS.Spacing.lg)
            .frame(minHeight: 52)
            .omiSurface(Capsule())
            .padding(.horizontal, DS.Spacing.lg)
        }
        .padding(.bottom, DS.Spacing.sm)
        .animation(DS.Motion.standard, value: message)
        .sheet(item: $moving) { request in
            MoveToFolderSheet(ids: request.ids) { selection = nil }.presentationDetents([.medium, .large])
        }
        .confirmationDialog(
            L("mergeConversations"), isPresented: $confirmsMerge, titleVisibility: .visible
        ) {
            Button(L("merge")) { Task { await merge() } }
        } message: {
            Text(L("mergeConversationsMessage", String(ids.count)))
        }
    }

    /// Oldest first, the order the merged transcript reads in.
    private var ids: [String] {
        let chosen = selection ?? []
        return conversations.visible.filter { chosen.contains($0.id) }.sorted { $0.date < $1.date }.map(\.id)
    }

    private func icon(_ systemImage: String, _ label: String, tint: Color = DS.Palette.ink, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(ids.isEmpty ? DS.Palette.inkDisabled : tint)
        }
        .disabled(ids.isEmpty)
        .accessibilityLabel(label)
    }

    private func merge() async {
        switch await conversations.merge(ids) {
        case let .started(warning):
            DSHaptics.success()
            // The rows now say "Merging"; the bar stays for the message, then leaves.
            selection = []
            await show(warning ?? L("nativeMergeStarted"))
            if selection?.isEmpty == true { selection = nil }
        case .needsTwo: await show(L("nativeMergeNeedsTwo"))
        case .notReady: await show(L("nativeMergeNotReady"))
        case .failed: await show(L("nativeMergeFailed"))
        }
    }

    private func show(_ text: String) async {
        message = text
        try? await Task.sleep(for: .seconds(3))
        if message == text { message = nil }
    }
}
