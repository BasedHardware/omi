import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// The chat header's "Talk to…" menu (Flutter `chat_apps_drawer`): Omi, or one of the enabled apps
/// that can chat. Each keeps its own history; switching waits until an answer has finished.
struct ChatAppPicker: View {
    @Environment(ChatStore.self) private var chat

    var body: some View {
        Menu {
            Section(L("nativeTalkTo")) {
                Button { Task { await chat.talk(to: nil) } } label: {
                    if chat.chatApp == nil { Label("Omi", systemImage: "checkmark") } else { Text("Omi") }
                }
                ForEach(chat.chatApps) { app in
                    Button { Task { await chat.talk(to: app) } } label: {
                        if chat.chatApp?.id == app.id { Label(app.name, systemImage: "checkmark") } else { Text(app.name) }
                    }
                }
            }
            if chat.chatApps.isEmpty {
                Text(L("nativeNoChatApps"))
            }
        } label: {
            HStack(spacing: DS.Spacing.xs) {
                if let app = chat.chatApp {
                    AsyncImage(url: app.imageURL) { $0.resizable().scaledToFill() } placeholder: { DS.Palette.fill }
                        .frame(width: 22, height: 22)
                        .clipShape(Circle())
                }
                // As the device pill on Home: the name and a small chevron, no capsule.
                Text(chat.chatApp?.name ?? "Omi").font(.body.weight(.medium)).lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(DS.Palette.inkTertiary)
            }
            .foregroundStyle(DS.Palette.ink)
            .padding(.horizontal, DS.Spacing.sm)
            .frame(minHeight: DS.Size.headerButton)
            .contentShape(Rectangle())
        }
        .disabled(chat.isStreaming)
        .accessibilityLabel(L("nativeTalkTo"))
        .accessibilityValue(chat.chatApp?.name ?? "Omi")
        .accessibilityIdentifier("chat.apps")
        .task { await chat.loadChatApps() }
    }
}
