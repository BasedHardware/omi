import OmiTheme
import SwiftUI

struct MessagesPage: View {
  @ObservedObject private var registry = MessagingRegistry.shared
  @ObservedObject private var coordinator = WhatsAppReplyCoordinator.shared
  @ObservedObject private var waState = WhatsAppState.shared

  @State private var selectedThreadId: String?
  @State private var threads: [MessageThread] = []
  @State private var messages: [MessageItem] = []
  @State private var isLoadingThreads = false
  @State private var isLoadingMessages = false
  @State private var showSettings = false
  @State private var showConnect = false
  @State private var composeText = ""
  @State private var draftEdits: [String: String] = [:]
  @State private var optimisticMessagesByThread: [String: [MessageItem]] = [:]
  @State private var sendError: String?
  @State private var isSending = false
  @State private var hasCheckedProviderConnection = false
  @State private var isCheckingProviderConnection = false
  @State private var isWhatsAppAuthenticated = false
  @State private var unreadClearBaselines: [String: Int] = [:]

  private var provider: (any MessagingProvider)? {
    registry.selectedProvider
  }

  private var displayedThreads: [MessageThread] {
    guard let provider else { return [] }
    let draftThreadIds = Set(provider.pendingDrafts().map(\.threadId))
    return threads.map { thread in
      MessageThread(
        id: thread.id,
        providerId: thread.providerId,
        title: thread.title,
        subtitle: thread.subtitle,
        lastMessagePreview: thread.lastMessagePreview,
        lastActivity: thread.lastActivity,
        unreadCount: displayedUnreadCount(for: thread),
        isGroup: thread.isGroup,
        hasPendingDraft: draftThreadIds.contains(thread.id)
      )
    }
    .sorted { ($0.lastActivity ?? .distantPast) > ($1.lastActivity ?? .distantPast) }
  }

  private var selectedThread: MessageThread? {
    displayedThreads.first { $0.id == selectedThreadId }
  }

  private var selectedDrafts: [PendingDraftItem] {
    guard let selectedThreadId, let provider else { return [] }
    return provider.pendingDrafts()
      .filter { $0.threadId == selectedThreadId }
      .sorted { $0.createdAt < $1.createdAt }
  }

  private var displayedMessages: [MessageItem] {
    guard let selectedThreadId else { return messages }
    let optimisticMessages = optimisticMessagesByThread[selectedThreadId] ?? []
    guard !optimisticMessages.isEmpty else { return messages }
    return (messages + optimisticMessages)
      .reduce(into: [String: MessageItem]()) { partial, message in
        partial[message.id] = message
      }
      .values
      .sorted { ($0.timestamp ?? .distantPast) < ($1.timestamp ?? .distantPast) }
  }

  private var shouldShowConnectionLoading: Bool {
    guard provider?.id == "whatsapp" else { return false }
    if isCheckingProviderConnection || !hasCheckedProviderConnection {
      return true
    }
    if case .connecting = waState.connectionState {
      return true
    }
    if case .downloading = waState.connectionState {
      return true
    }
    return false
  }

  var body: some View {
    VStack(spacing: 0) {
      header
      Divider()
        .background(OmiColors.border)

      if let provider {
        if provider.isConnected {
          connectedBody
        } else if shouldShowConnectionLoading {
          connectionLoadingBody(provider)
        } else {
          disconnectedBody(provider)
        }
      } else {
        emptyProviderBody
      }
    }
    .background(OmiColors.backgroundPrimary)
    .task {
      await prepareSelectedProvider()
      await refreshThreads()
      await runRefreshLoop()
    }
    .onChange(of: registry.selectedProviderId) { _, _ in
      selectedThreadId = nil
      messages = []
      unreadClearBaselines = [:]
      hasCheckedProviderConnection = false
      isWhatsAppAuthenticated = false
      Task {
        await prepareSelectedProvider()
        await refreshThreads()
      }
    }
    .onChange(of: coordinator.pendingDrafts) { _, _ in
      Task { await refreshThreads(preserveSelection: true) }
    }
    .onChange(of: waState.connectionState) { _, _ in
      Task { await refreshThreads(preserveSelection: true) }
    }
    .onChange(of: waState.lastEventSummary) { _, _ in
      Task { await refreshLiveData() }
    }
    .sheet(isPresented: $showSettings) {
      settingsSheet
    }
    .sheet(isPresented: $showConnect) {
      if let provider {
        provider.connectView {
          showConnect = false
          Task { await refreshThreads() }
        }
        .frame(width: 560, height: 640)
        .background(OmiColors.backgroundPrimary)
      }
    }
  }

  private var header: some View {
    HStack(spacing: 12) {
      providerTabs
      Spacer()
      Button {
        showSettings = true
      } label: {
        Image(systemName: "gearshape")
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)
          .frame(width: 34, height: 34)
          .background(Circle().fill(OmiColors.backgroundTertiary))
      }
      .buttonStyle(.plain)
      .help("Message provider settings")
    }
    .padding(.horizontal, 22)
    .padding(.vertical, 16)
  }

  private var providerTabs: some View {
    HStack(spacing: 8) {
      ForEach(registry.providers, id: \.id) { provider in
        Button {
          registry.selectedProviderId = provider.id
        } label: {
          HStack(spacing: 7) {
            MessagingProviderIcon(provider: provider, size: 12)
            Text(provider.displayName)
              .scaledFont(size: 13, weight: .semibold)
          }
          .foregroundColor(registry.selectedProviderId == provider.id ? .white : OmiColors.textSecondary)
          .padding(.horizontal, 12)
          .padding(.vertical, 8)
          .background(
            Capsule().fill(registry.selectedProviderId == provider.id ? OmiColors.purplePrimary : OmiColors.backgroundTertiary)
          )
        }
        .buttonStyle(.plain)
      }
    }
  }

  private func disconnectedBody(_ provider: any MessagingProvider) -> some View {
    VStack(spacing: 16) {
      MessagingProviderIcon(provider: provider, size: 48)
      VStack(spacing: 6) {
        Text("Connect \(provider.displayName)")
          .scaledFont(size: 20, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("Link your account to see chats, message history, and pending reply drafts here.")
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textTertiary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 380)
      }
      Button("Connect") {
        showConnect = true
      }
      .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private func connectionLoadingBody(_ provider: any MessagingProvider) -> some View {
    VStack(spacing: 16) {
      ProgressView()
        .controlSize(.large)
      VStack(spacing: 6) {
        Text("Checking \(provider.displayName)")
          .scaledFont(size: 20, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(waState.lastEventSummary ?? "Looking for an existing login and syncing recent chats.")
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textTertiary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 420)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private var emptyProviderBody: some View {
    VStack(spacing: 10) {
      Image(systemName: "message")
        .scaledFont(size: 32, weight: .semibold)
        .foregroundColor(OmiColors.textTertiary)
      Text("No messaging providers")
        .scaledFont(size: 18, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
      Text("Messaging providers will appear here as they are added.")
        .scaledFont(size: 13)
        .foregroundColor(OmiColors.textTertiary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private var connectedBody: some View {
    HStack(spacing: 0) {
      threadList
        .frame(width: 310)
      Divider()
        .background(OmiColors.border)
      conversationPane
    }
  }

  private var threadList: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack {
        Text("Threads")
          .scaledFont(size: 14, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        if isLoadingThreads {
          ProgressView()
            .controlSize(.small)
        } else {
          Button {
            Task { await refreshThreads() }
          } label: {
            Image(systemName: "arrow.clockwise")
              .scaledFont(size: 12, weight: .semibold)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
          .help("Refresh threads")
        }
      }
      .padding(.horizontal, 16)
      .padding(.vertical, 12)

      if displayedThreads.isEmpty, !isLoadingThreads {
        VStack(spacing: 8) {
          Image(systemName: "bubble.left.and.bubble.right")
            .scaledFont(size: 24)
            .foregroundColor(OmiColors.textTertiary)
          Text("No chats found")
            .scaledFont(size: 13, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)
          Text("Keep WhatsApp connected while it syncs messages.")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .multilineTextAlignment(.center)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        ScrollView {
          LazyVStack(spacing: 2) {
            ForEach(displayedThreads) { thread in
              ThreadRow(thread: thread, isSelected: selectedThreadId == thread.id) {
                selectThread(thread.id)
              }
            }
          }
          .padding(.horizontal, 8)
          .padding(.bottom, 10)
        }
      }
    }
    .background(OmiColors.backgroundSecondary.opacity(0.35))
  }

  private var conversationPane: some View {
    VStack(spacing: 0) {
      if let selectedThreadId, let selectedThread {
        conversationHeader(selectedThread)
        Divider()
          .background(OmiColors.border)
        messagesScroll(threadId: selectedThreadId)
        draftStack
        composeBar(threadId: selectedThreadId)
      } else {
        VStack(spacing: 10) {
          if let provider {
            MessagingProviderIcon(provider: provider, size: 40)
              .opacity(0.55)
          }
          Text("Select a thread")
            .scaledFont(size: 18, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text("Choose a WhatsApp chat to review messages or send a reply.")
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
  }

  private func conversationHeader(_ thread: MessageThread) -> some View {
    HStack(spacing: 12) {
      AvatarView(title: thread.title, isGroup: thread.isGroup)
      VStack(alignment: .leading, spacing: 3) {
        Text(thread.title)
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)
        if let subtitle = thread.subtitle {
          Text(subtitle)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
            .truncationMode(.middle)
        }
      }
      Spacer()
      if isLoadingMessages {
        ProgressView()
          .controlSize(.small)
      }
    }
    .padding(.horizontal, 18)
    .padding(.vertical, 12)
  }

  private func messagesScroll(threadId: String) -> some View {
    ScrollViewReader { proxy in
      ScrollView {
        LazyVStack(spacing: 10) {
          if displayedMessages.isEmpty, !isLoadingMessages {
            Text("No messages found for this thread yet.")
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textTertiary)
              .padding(.top, 32)
          } else {
            ForEach(displayedMessages) { message in
              MessageBubble(message: message)
                .id(message.id)
            }
          }
          Color.clear
            .frame(height: 1)
            .id("bottom-\(threadId)")
        }
        .padding(18)
      }
      .onChange(of: displayedMessages.count) { _, _ in
        scrollToBottom(proxy, threadId: threadId)
      }
      .onChange(of: selectedDrafts.count) { _, _ in
        scrollToBottom(proxy, threadId: threadId)
      }
    }
  }

  private var draftStack: some View {
    VStack(spacing: 8) {
      ForEach(selectedDrafts) { draft in
        DraftCard(
          draft: draft,
          editText: Binding(
            get: { draftEdits[draft.id] ?? draft.text },
            set: { draftEdits[draft.id] = $0 }
          ),
          onSend: {
            Task {
              _ = await provider?.approveDraft(id: draft.id, editedText: draftEdits[draft.id])
              draftEdits[draft.id] = nil
              await reloadSelectedMessages()
              await refreshThreads(preserveSelection: true)
            }
          },
          onAlwaysAutoReply: {
            Task {
              _ = await provider?.alwaysAutoReply(id: draft.id)
              draftEdits[draft.id] = nil
              await reloadSelectedMessages()
              await refreshThreads(preserveSelection: true)
            }
          },
          onDismiss: {
            provider?.dismissDraft(id: draft.id)
            draftEdits[draft.id] = nil
            Task { await refreshThreads(preserveSelection: true) }
          }
        )
      }
    }
    .padding(.horizontal, selectedDrafts.isEmpty ? 0 : 16)
    .padding(.bottom, selectedDrafts.isEmpty ? 0 : 10)
  }

  private func composeBar(threadId: String) -> some View {
    VStack(spacing: 6) {
      if let sendError {
        Text(sendError)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.warning)
          .frame(maxWidth: .infinity, alignment: .leading)
      }
      HStack(alignment: .bottom, spacing: 10) {
        TextField("Write a message", text: $composeText, axis: .vertical)
          .textFieldStyle(.plain)
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1...4)
          .padding(.horizontal, 12)
          .padding(.vertical, 10)
          .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
              .fill(OmiColors.backgroundTertiary)
          )

        Button {
          Task { await sendCompose(threadId: threadId) }
        } label: {
          if isSending {
            ProgressView()
              .controlSize(.small)
              .frame(width: 36, height: 36)
          } else {
            Image(systemName: "paperplane.fill")
              .scaledFont(size: 14, weight: .semibold)
              .foregroundColor(.white)
              .frame(width: 36, height: 36)
          }
        }
        .buttonStyle(.plain)
        .background(Circle().fill(canSendCompose ? OmiColors.purplePrimary : OmiColors.backgroundTertiary))
        .disabled(!canSendCompose || isSending)
      }
    }
    .padding(16)
    .background(OmiColors.backgroundPrimary)
  }

  private var settingsSheet: some View {
    VStack(spacing: 0) {
      HStack {
        Text("\(provider?.displayName ?? "Provider") Settings")
          .scaledFont(size: 18, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        Button("Close") {
          showSettings = false
        }
        .buttonStyle(.plain)
        .foregroundColor(OmiColors.textSecondary)
      }
      .padding(18)

      Divider()
        .background(OmiColors.border)

      ScrollView {
        if let provider {
          provider.settingsView()
            .padding(20)
        }
      }
    }
    .frame(width: 560, height: 640)
    .background(OmiColors.backgroundPrimary)
  }

  private var canSendCompose: Bool {
    !composeText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  private func prepareSelectedProvider() async {
    guard provider?.id == "whatsapp" else {
      hasCheckedProviderConnection = true
      return
    }
    isCheckingProviderConnection = true
    let health = await WhatsAppService.shared.health()
    isWhatsAppAuthenticated = health.isAuthenticated
    if health.isAuthenticated || health.isConnected {
      await WhatsAppService.shared.resumeIfAuthenticated()
      // Reflect resumed sync in UI state even if doctor JSON is sparse.
      if health.isConnected || WhatsAppState.shared.connectionState.isConnected {
        await MainActor.run {
          WhatsAppState.shared.update(connectionState: .connected)
        }
      }
    }
    hasCheckedProviderConnection = true
    isCheckingProviderConnection = false
  }

  private func refreshThreads(preserveSelection: Bool = false, showLoading: Bool = true) async {
    guard let provider, provider.isConnected else {
      threads = []
      return
    }
    if showLoading {
      isLoadingThreads = true
    }
    let loaded = await provider.loadThreads()
    threads = loaded.sorted { ($0.lastActivity ?? .distantPast) > ($1.lastActivity ?? .distantPast) }
    reconcileUnreadBaselines()
    clearSelectedThreadUnreadBadge()
    if showLoading {
      isLoadingThreads = false
    }

    if preserveSelection, let selectedThreadId, threads.contains(where: { $0.id == selectedThreadId }) {
      return
    }
    if selectedThreadId == nil {
      selectedThreadId = displayedThreads.first { $0.hasPendingDraft }?.id ?? displayedThreads.first?.id
      clearSelectedThreadUnreadBadge()
      await reloadSelectedMessages()
    }
  }

  private func selectThread(_ threadId: String) {
    selectedThreadId = threadId
    sendError = nil
    clearUnreadBadge(for: threadId)
    Task { await reloadSelectedMessages() }
  }

  private func reloadSelectedMessages(showLoading: Bool = true) async {
    guard let provider, let selectedThreadId else { return }
    let loadingThreadId = selectedThreadId
    if showLoading {
      isLoadingMessages = true
    }
    let loaded = await provider.loadMessages(threadId: loadingThreadId)
    guard self.selectedThreadId == loadingThreadId else {
      if showLoading {
        isLoadingMessages = false
      }
      return
    }
    pruneOptimisticMessages(for: loadingThreadId, against: loaded)
    messages = loaded
    if showLoading {
      isLoadingMessages = false
    }
  }

  private func sendCompose(threadId: String) async {
    guard let provider else { return }
    let text = composeText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty else { return }
    let optimisticMessage = MessageItem(
      id: "local-send:\(UUID().uuidString)",
      text: text,
      isFromMe: true,
      senderName: nil,
      timestamp: Date()
    )
    addOptimisticMessage(optimisticMessage, threadId: threadId)
    composeText = ""
    isSending = true
    sendError = nil
    let result = await provider.sendMessage(threadId: threadId, text: text)
    isSending = false
    switch result {
    case .sent:
      await refreshThreads(preserveSelection: true, showLoading: false)
    case .failed(let reason):
      removeOptimisticMessage(optimisticMessage.id, threadId: threadId)
      if composeText.isEmpty {
        composeText = text
      }
      sendError = reason
    }
  }

  private func refreshLiveData() async {
    guard provider?.isConnected == true else { return }
    await refreshThreads(preserveSelection: true, showLoading: false)
    await reloadSelectedMessages(showLoading: false)
  }

  private func runRefreshLoop() async {
    while !Task.isCancelled {
      try? await Task.sleep(nanoseconds: 8_000_000_000)
      await refreshLiveData()
    }
  }

  private func addOptimisticMessage(_ message: MessageItem, threadId: String) {
    var existing = optimisticMessagesByThread[threadId] ?? []
    existing.append(message)
    optimisticMessagesByThread[threadId] = existing
  }

  private func displayedUnreadCount(for thread: MessageThread) -> Int {
    max(0, thread.unreadCount - (unreadClearBaselines[thread.id] ?? 0))
  }

  private func reconcileUnreadBaselines() {
    let unreadCountsByThread = Dictionary(uniqueKeysWithValues: threads.map { ($0.id, $0.unreadCount) })
    var updatedBaselines: [String: Int] = [:]
    for (threadId, baseline) in unreadClearBaselines {
      if let unreadCount = unreadCountsByThread[threadId] {
        updatedBaselines[threadId] = min(baseline, unreadCount)
      }
    }
    unreadClearBaselines = updatedBaselines
  }

  private func clearSelectedThreadUnreadBadge() {
    guard let selectedThreadId else { return }
    clearUnreadBadge(for: selectedThreadId)
  }

  private func clearUnreadBadge(for threadId: String) {
    guard let unreadCount = threads.first(where: { $0.id == threadId })?.unreadCount else { return }
    unreadClearBaselines[threadId] = max(unreadClearBaselines[threadId] ?? 0, unreadCount)
  }

  private func removeOptimisticMessage(_ messageId: String, threadId: String) {
    optimisticMessagesByThread[threadId]?.removeAll { $0.id == messageId }
  }

  private func pruneOptimisticMessages(for threadId: String, against loadedMessages: [MessageItem]) {
    let now = Date()
    optimisticMessagesByThread[threadId]?.removeAll { optimistic in
      if let timestamp = optimistic.timestamp, now.timeIntervalSince(timestamp) > 300 {
        return true
      }
      return loadedMessages.contains { loaded in
        loaded.isFromMe
          && loaded.text == optimistic.text
          && abs((loaded.timestamp ?? now).timeIntervalSince(optimistic.timestamp ?? now)) < 300
      }
    }
  }

  private func scrollToBottom(_ proxy: ScrollViewProxy, threadId: String) {
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
      withAnimation(.easeOut(duration: 0.18)) {
        proxy.scrollTo("bottom-\(threadId)", anchor: .bottom)
      }
    }
  }
}

private struct ThreadRow: View {
  let thread: MessageThread
  let isSelected: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      HStack(spacing: 10) {
        AvatarView(title: thread.title, isGroup: thread.isGroup)
        VStack(alignment: .leading, spacing: 5) {
          HStack(spacing: 8) {
            Text(thread.title)
              .scaledFont(size: 13, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
              .lineLimit(1)
            Spacer()
            if let lastActivity = thread.lastActivity {
              Text(Self.relativeTime(lastActivity))
                .scaledFont(size: 10, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
            }
          }

          HStack(spacing: 6) {
            Text(thread.lastMessagePreview ?? thread.subtitle ?? "No preview")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(1)
            Spacer(minLength: 4)
            if thread.hasPendingDraft {
              badge("Draft", color: OmiColors.purplePrimary)
            }
            if thread.unreadCount > 0 {
              badge("\(thread.unreadCount)", color: OmiColors.warning)
            }
          }
        }
      }
      .padding(.horizontal, 10)
      .padding(.vertical, 9)
      .background(
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .fill(isSelected ? OmiColors.purplePrimary.opacity(0.14) : Color.clear)
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
  }

  private func badge(_ text: String, color: Color) -> some View {
    Text(text)
      .scaledFont(size: 9, weight: .bold)
      .foregroundColor(color)
      .padding(.horizontal, 6)
      .padding(.vertical, 3)
      .background(Capsule().fill(color.opacity(0.14)))
  }

  private static func relativeTime(_ date: Date) -> String {
    let formatter = RelativeDateTimeFormatter()
    formatter.unitsStyle = .abbreviated
    return formatter.localizedString(for: date, relativeTo: Date())
  }
}

private struct MessageBubble: View {
  let message: MessageItem

  var body: some View {
    HStack {
      if message.isFromMe {
        Spacer(minLength: 80)
      }
      VStack(alignment: message.isFromMe ? .trailing : .leading, spacing: 4) {
        if !message.isFromMe, let senderName = message.senderName {
          Text(senderName)
            .scaledFont(size: 10, weight: .semibold)
            .foregroundColor(OmiColors.textTertiary)
        }
        Text(message.text)
          .scaledFont(size: 13)
          .foregroundColor(message.isFromMe ? .white : OmiColors.textPrimary)
          .fixedSize(horizontal: false, vertical: true)
        if let timestamp = message.timestamp {
          Text(timestamp.formatted(date: .omitted, time: .shortened))
            .scaledFont(size: 10)
            .foregroundColor(message.isFromMe ? .white.opacity(0.72) : OmiColors.textTertiary)
        }
      }
      .padding(.horizontal, 12)
      .padding(.vertical, 9)
      .background(
        RoundedRectangle(cornerRadius: 15, style: .continuous)
          .fill(message.isFromMe ? OmiColors.purplePrimary : OmiColors.backgroundTertiary)
      )
      .frame(maxWidth: 520, alignment: message.isFromMe ? .trailing : .leading)
      if !message.isFromMe {
        Spacer(minLength: 80)
      }
    }
  }
}

private struct DraftCard: View {
  let draft: PendingDraftItem
  @Binding var editText: String
  let onSend: () -> Void
  let onAlwaysAutoReply: () -> Void
  let onDismiss: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack {
        Label("Pending draft", systemImage: "sparkles")
          .scaledFont(size: 12, weight: .semibold)
          .foregroundColor(OmiColors.purplePrimary)
        Spacer()
        Text(draft.createdAt.formatted(date: .omitted, time: .shortened))
          .scaledFont(size: 11)
          .foregroundColor(OmiColors.textTertiary)
      }

      Text("Replying to: \(draft.incomingText)")
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
        .lineLimit(2)

      TextField("Draft reply", text: $editText, axis: .vertical)
        .textFieldStyle(.roundedBorder)
        .lineLimit(2...5)

      HStack(spacing: 10) {
        Button("Send", action: onSend)
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
        Button("Always Auto + Send", action: onAlwaysAutoReply)
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
        Button("Dismiss", action: onDismiss)
          .buttonStyle(.plain)
          .foregroundColor(OmiColors.warning)
      }
    }
    .padding(14)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(OmiColors.backgroundTertiary)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .stroke(OmiColors.purplePrimary.opacity(0.28), lineWidth: 1)
        )
    )
  }
}

private struct AvatarView: View {
  let title: String
  let isGroup: Bool

  var body: some View {
    ZStack {
      Circle()
        .fill(isGroup ? OmiColors.purplePrimary.opacity(0.18) : OmiColors.backgroundTertiary)
      Text(initials)
        .scaledFont(size: 12, weight: .bold)
        .foregroundColor(isGroup ? OmiColors.purplePrimary : OmiColors.textSecondary)
    }
    .frame(width: 34, height: 34)
  }

  private var initials: String {
    let words = title.split(separator: " ").prefix(2)
    let letters = words.compactMap(\.first).map(String.init).joined()
    return letters.isEmpty ? "?" : letters.uppercased()
  }
}
