import OmiDesign
import OmiService
import SwiftUI

/// "Conversation deleted · Undo" while a delete waits out its undo window. The app shell shows it
/// above every screen, so a delete from the detail page can be undone back on Home.
public struct UndoDeleteToast: View {
    @Environment(ConversationsStore.self) private var conversations

    public init() {}

    public var body: some View {
        Group {
            if let pending = conversations.pendingDeletion {
                OmiToast(
                    text: pending.ids.count == 1 ? L("conversationDeleted") : L("nativeConversationsDeleted", String(pending.ids.count)),
                    systemImage: "trash",
                    actionTitle: L("undo")
                ) {
                    DSHaptics.tap()
                    withAnimation(DS.Motion.standard) { conversations.undoDelete() }
                }
                .id(pending.ids)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(DS.Motion.standard, value: conversations.pendingDeletion)
    }
}

/// A short message capsule with an optional action, Omi's snackbar.
public struct OmiToast: View {
    let text: String
    let systemImage: String
    let actionTitle: String?
    let action: (() -> Void)?

    public init(text: String, systemImage: String, actionTitle: String? = nil, action: (() -> Void)? = nil) {
        self.text = text
        self.systemImage = systemImage
        self.actionTitle = actionTitle
        self.action = action
    }

    public var body: some View {
        HStack(spacing: DS.Spacing.md) {
            Image(systemName: systemImage).foregroundStyle(DS.Palette.inkSecondary).accessibilityHidden(true)
            Text(text).font(DS.Typography.callout.weight(.medium)).lineLimit(2)
            Spacer(minLength: 0)
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .font(DS.Typography.callout.weight(.semibold))
                    .foregroundStyle(DS.Palette.agent)
                    .accessibilityIdentifier("toast.action")
            }
        }
        .padding(.horizontal, DS.Spacing.lg)
        .frame(minHeight: 48)
        .omiSurface(Capsule())
        .shadow(color: .black.opacity(0.12), radius: 12, y: 4)
        .padding(.horizontal, DS.Spacing.lg)
        .accessibilityElement(children: .combine)
    }
}
