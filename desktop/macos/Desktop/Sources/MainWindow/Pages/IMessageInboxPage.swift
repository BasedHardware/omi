import SwiftUI

/// Replies inbox: recent iMessage threads awaiting a reply. Omi drafts a suggested
/// reply the user reviews, edits, and sends — nothing is ever sent automatically.
struct IMessageInboxPage: View {
  @StateObject private var store = IMessageInboxStore()

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      header

      if store.permissionNeeded {
        permissionCard
      } else if store.isLoading && store.threads.isEmpty {
        loadingState
      } else if let error = store.errorMessage {
        messageCard(
          title: "Couldn't read Messages", detail: error, systemImage: "exclamationmark.triangle"
        ) { EmptyView() }
      } else if store.threads.isEmpty {
        messageCard(
          title: "You're all caught up",
          detail: "No recent messages are waiting on a reply.",
          systemImage: "checkmark.circle"
        ) { EmptyView() }
      } else {
        ScrollView {
          LazyVStack(spacing: 12) {
            ForEach(store.threads) { thread in
              InboxRow(thread: thread)
            }
          }
          .padding(20)
        }
      }

      Spacer(minLength: 0)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(OmiColors.backgroundPrimary)
    .task { await store.load() }
  }

  private var header: some View {
    HStack {
      VStack(alignment: .leading, spacing: 2) {
        Text("Replies")
          .scaledFont(size: 22, weight: .bold)
          .foregroundColor(OmiColors.textPrimary)
        Text("Omi drafts a reply — you review and send.")
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)
      }
      Spacer()
      Button {
        Task { await store.load() }
      } label: {
        Image(systemName: "arrow.clockwise")
          .foregroundColor(OmiColors.textSecondary)
      }
      .buttonStyle(.plain)
      .disabled(store.isLoading)
    }
    .padding(20)
  }

  private var loadingState: some View {
    HStack(spacing: 10) {
      ProgressView().controlSize(.small)
      Text("Reading recent messages…")
        .scaledFont(size: 13)
        .foregroundColor(OmiColors.textSecondary)
    }
    .padding(24)
  }

  private var permissionCard: some View {
    messageCard(
      title: "Grant Full Disk Access",
      detail:
        "Omi needs Full Disk Access to read Messages. Turn it on in System Settings → Privacy & Security → Full Disk Access, then quit and reopen Omi.",
      systemImage: "lock.shield"
    ) {
      Button("Open System Settings") {
        IMessagePermissionPolicy.openFullDiskAccessSettings()
      }
      .buttonStyle(.borderedProminent)
      .tint(.white)
      .foregroundColor(.black)
    }
  }

  private func messageCard<Action: View>(
    title: String, detail: String, systemImage: String,
    @ViewBuilder action: () -> Action
  ) -> some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack(spacing: 8) {
        Image(systemName: systemImage)
          .foregroundColor(OmiColors.textSecondary)
        Text(title)
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
      }
      Text(detail)
        .scaledFont(size: 13)
        .foregroundColor(OmiColors.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
      action()
    }
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(OmiColors.backgroundSecondary)
    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    .padding(20)
  }
}

/// A single thread row with inline draft-and-send.
private struct InboxRow: View {
  let thread: IMessageInboxThread

  @State private var draft = ""
  @State private var isDrafting = false
  @State private var isSending = false
  @State private var sent = false
  @State private var errorText: String?

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(alignment: .top, spacing: 10) {
        ConnectorBrandIcon(brand: .imessage, size: 32, cornerRadius: 9)
        VStack(alignment: .leading, spacing: 3) {
          Text(thread.displayName)
            .scaledFont(size: 15, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text(thread.lastMessage)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textSecondary)
            .lineLimit(3)
        }
        Spacer()
      }

      if sent {
        Label("Sent", systemImage: "checkmark.circle.fill")
          .scaledFont(size: 13, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)
      } else if draft.isEmpty {
        Button {
          Task { await generateDraft() }
        } label: {
          HStack(spacing: 6) {
            if isDrafting { ProgressView().controlSize(.small) }
            Text(isDrafting ? "Drafting…" : "Draft with Omi")
          }
        }
        .buttonStyle(.bordered)
        .disabled(isDrafting)
      } else {
        TextEditor(text: $draft)
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textPrimary)
          .frame(minHeight: 60, maxHeight: 140)
          .padding(8)
          .background(OmiColors.backgroundPrimary)
          .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

        HStack(spacing: 10) {
          Button {
            Task { await sendReply() }
          } label: {
            HStack(spacing: 6) {
              if isSending { ProgressView().controlSize(.small) }
              Text(isSending ? "Sending…" : "Send")
            }
          }
          .buttonStyle(.borderedProminent)
          .tint(.white)
          .foregroundColor(.black)
          .disabled(isSending || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

          Button("Discard") {
            draft = ""
            errorText = nil
          }
          .buttonStyle(.plain)
          .foregroundColor(OmiColors.textSecondary)
        }
      }

      if let errorText {
        Text(errorText)
          .scaledFont(size: 12)
          .foregroundColor(.orange)
      }
    }
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(OmiColors.backgroundSecondary)
    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
  }

  private func generateDraft() async {
    isDrafting = true
    errorText = nil
    defer { isDrafting = false }
    do {
      let text = try await APIClient.shared.imessageDraftReply(
        person: thread.personRef, thread: thread.context, intent: nil)
      draft = text
    } catch {
      errorText = "Couldn't draft a reply: \(error.localizedDescription)"
    }
  }

  private func sendReply() async {
    isSending = true
    errorText = nil
    defer { isSending = false }
    do {
      try IMessageSenderService.send(text: draft, toChatGUID: thread.chatGUID)
      sent = true
    } catch {
      errorText = error.localizedDescription
    }
  }
}
