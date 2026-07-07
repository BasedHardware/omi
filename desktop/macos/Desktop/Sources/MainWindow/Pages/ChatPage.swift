import AppKit
import SwiftUI
import OmiTheme

struct ChatPage: View {
  @ObservedObject var appProvider: AppProvider
  @ObservedObject var chatProvider: ChatProvider
  @State private var showAppPicker = false
  @State private var showHistoryPopover = false
  @State private var selectedCitation: Citation?
  @State private var citedConversation: ServerConversation?
  @State private var isLoadingCitation = false
  @State private var copied = false

  var selectedApp: OmiApp? {
    guard let appId = chatProvider.selectedAppId else { return nil }
    return appProvider.chatApps.first { $0.id == appId }
  }

  var body: some View {
    VStack(spacing: 0) {
      // Header with app picker
      chatHeader
        .padding(.horizontal, 24)
        .padding(.top, 24)
        .padding(.bottom, 18)

      Divider()
        .background(OmiColors.border.opacity(0.4))

      // Messages area
      messagesView

      // Structured ChatErrorCard for mappable BridgeError cases.
      // Renders ABOVE the legacy errorMessage banner so its primary
      // CTA gets the prominent slot. Only one of {card, banner} is
      // ever active per turn — sendMessage's catch block clears the
      // other when setting one.
      if let cardState = chatProvider.currentError {
        ChatErrorCard(
          state: cardState,
          onRecover: {
            Task { await chatProvider.recoverFromError() }
          },
          onDismiss: {
            chatProvider.dismissCurrentError()
          }
        )
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
      }

      // Legacy error banner — fallback for unmappable BridgeError
      // cases (encodingError, quotaExceeded, free-form .agentError
      // messages). Stays so no error path becomes invisible.
      if let error = chatProvider.errorMessage {
        HStack(spacing: 8) {
          Image(systemName: "exclamationmark.triangle.fill")
            .foregroundColor(OmiColors.warning)
            .scaledFont(size: 14)
          Text(error)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textSecondary)
          Spacer()
          Button {
            chatProvider.errorMessage = nil
          } label: {
            Image(systemName: "xmark")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(OmiColors.backgroundSecondary)
      }

      // Input area
      inputArea
        .padding(.horizontal, 24)
        .padding(.top, 16)
        .padding(.bottom, 24)
    }
    .background(OmiColors.backgroundPrimary)
    .sheet(item: $citedConversation) { conversation in
      ConversationDetailView(
        conversation: conversation,
        onBack: {
          citedConversation = nil
          selectedCitation = nil
        }
      )
      .frame(minWidth: 500, minHeight: 500)
    }
    .sheet(isPresented: $chatProvider.needsBrowserExtensionSetup) {
      BrowserExtensionSetup(
        onComplete: {
          chatProvider.needsBrowserExtensionSetup = false
        },
        onDismiss: {
          chatProvider.needsBrowserExtensionSetup = false
        },
        chatProvider: chatProvider
      )
      .fixedSize()
    }
    .sheet(isPresented: $chatProvider.isClaudeAuthRequired) {
      ClaudeAuthSheet(
        onConnect: {
          if let url = URL(string: "https://omi.me/pricing") {
            NSWorkspace.shared.open(url)
          }
          chatProvider.isClaudeAuthRequired = false
          Task {
            await chatProvider.switchBridgeMode(to: ChatProvider.BridgeMode.piMono)
          }
        },
        onCancel: {
          chatProvider.isClaudeAuthRequired = false
          // Switch back to Omi AI (pi-mono) if auth cancelled
          Task {
            await chatProvider.switchBridgeMode(to: ChatProvider.BridgeMode.piMono)
          }
        }
      )
    }
    .alert("Upgrade Required", isPresented: $chatProvider.showOmiThresholdAlert) {
      Button("Upgrade to Omi Pro") {
        chatProvider.showOmiThresholdAlert = false
        if let url = URL(string: "https://omi.me/pricing") {
          NSWorkspace.shared.open(url)
        }
      }
      Button("Later", role: .cancel) {
        chatProvider.showOmiThresholdAlert = false
      }
    } message: {
      Text("Upgrade to Omi Pro for $199/month to continue chatting.")
    }
    .overlay {
      // Loading overlay when fetching citation
      if isLoadingCitation {
        ZStack {
          Color.black.opacity(0.3)
          VStack(spacing: 12) {
            ProgressView()
            Text("Loading source...")
              .scaledFont(size: 13)
              .foregroundColor(.white)
          }
          .padding(20)
          .background(OmiColors.backgroundSecondary)
          .cornerRadius(12)
        }
      }
    }
  }

  // MARK: - Header

  private var chatHeader: some View {
    HStack {
      // Multi-chat mode controls
      if chatProvider.multiChatEnabled {
        // Default Chat indicator or button
        if chatProvider.isInDefaultChat {
          // Show indicator that we're in default chat
          HStack(spacing: 6) {
            Image(systemName: "icloud")
              .scaledFont(size: 11)
            Text("Synced Chat")
              .scaledFont(size: 11, weight: .medium)
          }
          .foregroundColor(OmiColors.success)
          .padding(.horizontal, 8)
          .padding(.vertical, 4)
          .background(OmiColors.success.opacity(0.15))
          .cornerRadius(6)
          .help("This chat syncs with your mobile app")
        } else {
          // Show button to switch back to default chat
          Button(action: {
            Task {
              await chatProvider.switchToDefaultChat()
            }
          }) {
            HStack(spacing: 6) {
              Image(systemName: "icloud")
                .scaledFont(size: 11)
              Text("Synced")
                .scaledFont(size: 11, weight: .medium)
            }
            .foregroundColor(OmiColors.textTertiary)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(6)
          }
          .buttonStyle(.plain)
          .help("Switch to synced chat (shares messages with mobile)")

          // Current session indicator
          if let session = chatProvider.currentSession {
            Text(session.title)
              .scaledFont(size: 12, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
              .lineLimit(1)
          }
        }

        // New chat button
        Button(action: {
          Task {
            _ = await chatProvider.createNewSession()
          }
        }) {
          Image(systemName: "plus")
            .scaledFont(size: 14, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
        .help("New chat session")
      }

      // App selector
      Button(action: { showAppPicker.toggle() }) {
        HStack(spacing: 10) {
          if let app = selectedApp {
            // Show selected app
            AsyncImage(url: URL(string: app.image)) { phase in
              switch phase {
              case .success(let image):
                image
                  .resizable()
                  .aspectRatio(contentMode: .fill)
              default:
                Circle()
                  .fill(OmiColors.backgroundTertiary)
              }
            }
            .frame(width: 32, height: 32)
            .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
              Text(app.name)
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              Text("Chat App")
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
            }
          } else {
            // Default OMI assistant
            Text("omi")
              .scaledFont(size: 14, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)
          }

          if !appProvider.chatApps.isEmpty {
            Image(systemName: "chevron.down")
              .scaledFont(size: 10)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .omiControlSurface(fill: OmiColors.backgroundTertiary, radius: 18)
      }
      .buttonStyle(.plain)
      .disabled(appProvider.chatApps.isEmpty)
      .popover(isPresented: $showAppPicker, arrowEdge: .bottom) {
        AppPickerPopover(
          apps: appProvider.chatApps,
          selectedAppId: Binding(
            get: { chatProvider.selectedAppId },
            set: { newAppId in
              Task {
                await chatProvider.selectApp(newAppId)
              }
            }
          ),
          onSelect: { showAppPicker = false }
        )
      }

      Spacer()

      // Model indicator
      Text(chatProvider.currentModel)
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textTertiary)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .omiControlSurface(fill: OmiColors.backgroundTertiary.opacity(0.9), radius: 12)

      // Copy conversation button
      if !chatProvider.messages.isEmpty {
        Button(action: {
          copyConversation()
        }) {
          Image(systemName: copied ? "checkmark" : "doc.on.doc")
            .scaledFont(size: 14)
            .foregroundColor(copied ? OmiColors.success : OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
        .help("Copy conversation")
      }

      // Clear chat button
      if !chatProvider.messages.isEmpty || chatProvider.isClearing {
        Button(action: {
          Task {
            await chatProvider.clearChat()
          }
        }) {
          if chatProvider.isClearing {
            ProgressView()
              .scaleEffect(0.5)
              .frame(width: 14, height: 14)
          } else {
            Image(systemName: "trash")
              .scaledFont(size: 14)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
        .buttonStyle(.plain)
        .help("Clear chat history")
        .disabled(chatProvider.isLoading || chatProvider.isClearing)
      }

      // History button (only in multi-chat mode)
      if chatProvider.multiChatEnabled {
        Button(action: { showHistoryPopover.toggle() }) {
          Image(systemName: "clock.arrow.circlepath")
            .scaledFont(size: 14)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
        .help("Chat history")
        .popover(isPresented: $showHistoryPopover, arrowEdge: .bottom) {
          ChatHistoryPopover(
            chatProvider: chatProvider,
            onSelect: { showHistoryPopover = false }
          )
        }
      }

      // Advanced AI settings button
      Button(action: {
        NotificationCenter.default.post(name: .navigateToAIChatSettings, object: nil)
      }) {
        Image(systemName: "gear")
          .scaledFont(size: 14)
          .foregroundColor(OmiColors.textTertiary)
      }
      .buttonStyle(.plain)
      .help("Advanced AI settings")
    }
  }

  // MARK: - Messages

  private var messagesView: some View {
    ChatMessagesView(
      messages: chatProvider.messages,
      isSending: chatProvider.isSending,
      hasMoreMessages: chatProvider.hasMoreMessages,
      isLoadingMoreMessages: chatProvider.isLoadingMoreMessages,
      isLoadingInitial: (chatProvider.isLoading || chatProvider.isLoadingSessions)
        && !chatProvider.isClearing,
      app: selectedApp,
      onLoadMore: { await chatProvider.loadMoreMessages() },
      onRate: { messageId, rating in
        Task { await chatProvider.rateMessage(messageId, rating: rating) }
      },
      onCitationTap: { citation in
        handleCitationTap(citation)
      },
      sessionsLoadError: chatProvider.sessionsLoadError,
      onRetry: { Task { await chatProvider.retryLoad() } },
      localSendToken: chatProvider.localSendToken,
      onCancelTurn: { [weak chatProvider] in chatProvider?.stopAgent(owner: .mainChat) },
      welcomeContent: { welcomeMessage }
    )
  }

  private var welcomeMessage: some View {
    VStack(spacing: 18) {
      if let app = selectedApp {
        AsyncImage(url: URL(string: app.image)) { phase in
          switch phase {
          case .success(let image):
            image
              .resizable()
              .aspectRatio(contentMode: .fill)
          default:
            Circle()
              .fill(OmiColors.backgroundTertiary)
          }
        }
        .frame(width: 64, height: 64)
        .clipShape(Circle())

        Text("Chat with \(app.name)")
          .scaledFont(size: 18, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Text(app.description)
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)
          .multilineTextAlignment(.center)
          .lineLimit(3)
          .padding(.horizontal, 40)
      } else {
        // Default OMI assistant
        if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
          let logoImage = NSImage(contentsOf: logoURL)
        {
          Image(nsImage: logoImage)
            .resizable()
            .scaledToFit()
            .frame(width: 48, height: 48)
        }

        Text("Chat with omi")
          .scaledFont(size: 18, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Text("Your personal AI assistant that knows you through your memories and conversations")
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)
          .multilineTextAlignment(.center)
          .padding(.horizontal, 40)
      }
    }
    .frame(maxWidth: .infinity)
    .padding(.horizontal, 24)
    .padding(.vertical, 84)
    .frame(maxWidth: 640)
    .omiPanel(
      fill: OmiColors.backgroundSecondary.opacity(0.82), radius: 28,
      stroke: OmiColors.border.opacity(0.18), shadowOpacity: 0.12, shadowRadius: 14, shadowY: 8)
  }

  // MARK: - Input Area

  private var inputArea: some View {
    ChatInputView(
      onSend: { text in
        AnalyticsManager.shared.chatMessageSent(
          messageLength: text.count, hasContext: selectedApp != nil, source: "main_chat")
        Task { await chatProvider.sendMessage(text) }
      },
      onFollowUp: { text in
        Task { await chatProvider.sendFollowUp(text) }
      },
      onStop: {
        chatProvider.stopAgent(owner: .mainChat)
      },
      isSending: chatProvider.isSending,
      isStopping: chatProvider.isStopping,
      mode: $chatProvider.chatMode,
      inputText: $chatProvider.draftText,
      attachments: $chatProvider.pendingAttachments,
      onAttachmentsAdded: { urls in
        let toAdd = urls.compactMap { ChatAttachment.from(url: $0) }
        chatProvider.addAttachments(toAdd)
      },
      onAttachmentRemoved: { id in
        chatProvider.removePendingAttachment(id: id)
      }
    )
  }

  /// Copy the entire conversation to clipboard
  private func copyConversation() {
    let text: String = chatProvider.messages.map { message in
      let sender = message.sender == .user ? "You" : (selectedApp?.name ?? "omi")
      return "\(sender): \(message.text)"
    }.joined(separator: "\n\n")

    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(text, forType: .string)

    copied = true
    DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
      copied = false
    }
  }

  /// Handle tapping on a citation card
  private func handleCitationTap(_ citation: Citation) {
    guard citation.sourceType == .conversation else {
      // Memories don't have a detail view yet
      log("Citation tapped: \(citation.title) (memory - no detail view)")
      return
    }

    selectedCitation = citation
    isLoadingCitation = true

    // Fetch the full conversation
    Task {
      do {
        let conversation = try await APIClient.shared.getConversation(id: citation.id)
        await MainActor.run {
          citedConversation = conversation
          isLoadingCitation = false
        }
      } catch {
        logError("Failed to fetch cited conversation", error: error)
        await MainActor.run {
          isLoadingCitation = false
          selectedCitation = nil
        }
      }
    }
  }
}

// MARK: - App Picker Popover

struct AppPickerPopover: View {
  let apps: [OmiApp]
  @Binding var selectedAppId: String?
  let onSelect: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Text("Select Assistant")
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
        .padding(.horizontal, 12)
        .padding(.top, 12)
        .padding(.bottom, 8)

      ScrollView {
        VStack(spacing: 2) {
          // Default OMI option
          DefaultOmiRow(isSelected: selectedAppId == nil) {
            selectedAppId = nil
            AnalyticsManager.shared.chatAppSelected(appId: nil, appName: "OMI")
            onSelect()
          }

          if !apps.isEmpty {
            Divider()
              .padding(.vertical, 4)
              .padding(.horizontal, 12)

            ForEach(apps) { app in
              AppPickerRow(
                app: app,
                isSelected: selectedAppId == app.id
              ) {
                selectedAppId = app.id
                AnalyticsManager.shared.chatAppSelected(appId: app.id, appName: app.name)
                onSelect()
              }
            }
          }
        }
      }
      .frame(maxHeight: 300)
    }
    .frame(width: 250)
    .background(OmiColors.backgroundPrimary)
  }
}

struct DefaultOmiRow: View {
  let isSelected: Bool
  let onSelect: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onSelect) {
      HStack(spacing: 10) {
        if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
          let logoImage = NSImage(contentsOf: logoURL)
        {
          Image(nsImage: logoImage)
            .resizable()
            .scaledToFit()
            .frame(width: 22, height: 22)
            .frame(width: 36, height: 36)
            .background(OmiColors.backgroundTertiary)
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }

        Text("omi")
          .scaledFont(size: 13, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        if isSelected {
          Image(systemName: "checkmark")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.purplePrimary)
        }
      }
      .padding(.horizontal, 12)
      .padding(.vertical, 8)
      .background(isSelected || isHovering ? OmiColors.backgroundSecondary : Color.clear)
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }
}

struct AppPickerRow: View {
  let app: OmiApp
  let isSelected: Bool
  let onSelect: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onSelect) {
      HStack(spacing: 10) {
        AsyncImage(url: URL(string: app.image)) { phase in
          switch phase {
          case .success(let image):
            image
              .resizable()
              .aspectRatio(contentMode: .fill)
          default:
            Circle()
              .fill(OmiColors.backgroundTertiary)
          }
        }
        .frame(width: 36, height: 36)
        .clipShape(RoundedRectangle(cornerRadius: 8))

        VStack(alignment: .leading, spacing: 2) {
          Text(app.name)
            .scaledFont(size: 13, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)

          Text(app.author)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
        }

        Spacer()

        if isSelected {
          Image(systemName: "checkmark")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.purplePrimary)
        }
      }
      .padding(.horizontal, 12)
      .padding(.vertical, 8)
      .background(isSelected || isHovering ? OmiColors.backgroundSecondary : Color.clear)
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }
}

// MARK: - Chat History Popover

struct ChatHistoryPopover: View {
  @ObservedObject var chatProvider: ChatProvider
  let onSelect: () -> Void

  @State private var isTogglingStarred = false

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Header
      HStack {
        Text("Chat History")
          .scaledFont(size: 14, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        // Starred filter button
        Button(action: {
          Task {
            isTogglingStarred = true
            await chatProvider.toggleStarredFilter()
            isTogglingStarred = false
          }
        }) {
          if isTogglingStarred {
            ProgressView()
              .scaleEffect(0.5)
              .frame(width: 14, height: 14)
          } else {
            Image(systemName: chatProvider.showStarredOnly ? "star.fill" : "star")
              .scaledFont(size: 12)
              .foregroundColor(
                chatProvider.showStarredOnly ? OmiColors.amber : OmiColors.textTertiary)
          }
        }
        .buttonStyle(.plain)
        .help(chatProvider.showStarredOnly ? "Show all chats" : "Show starred only")

        // New chat button in header
        Button(action: {
          Task {
            _ = await chatProvider.createNewSession()
            onSelect()
          }
        }) {
          Image(systemName: "plus")
            .scaledFont(size: 12, weight: .medium)
            .foregroundColor(OmiColors.purplePrimary)
        }
        .buttonStyle(.plain)
        .help("New chat")
      }
      .padding(.horizontal, 16)
      .padding(.vertical, 12)

      // Search field
      HStack(spacing: 8) {
        Image(systemName: "magnifyingglass")
          .scaledFont(size: 11)
          .foregroundColor(OmiColors.textTertiary)

        TextField("Search chats...", text: $chatProvider.searchQuery)
          .textFieldStyle(.plain)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textPrimary)

        if !chatProvider.searchQuery.isEmpty {
          Button(action: { chatProvider.searchQuery = "" }) {
            Image(systemName: "xmark.circle.fill")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }
      }
      .padding(.horizontal, 10)
      .padding(.vertical, 6)
      .background(OmiColors.backgroundSecondary)
      .cornerRadius(6)
      .padding(.horizontal, 16)
      .padding(.bottom, 12)

      Divider()

      // Sessions list
      if chatProvider.isLoadingSessions {
        VStack {
          Spacer()
          ProgressView()
            .scaleEffect(0.8)
          Text("Loading...")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .padding(.top, 8)
          Spacer()
        }
        .frame(height: 200)
      } else if chatProvider.filteredSessions.isEmpty {
        VStack(spacing: 8) {
          Spacer()
          Image(systemName: emptyStateIcon)
            .scaledFont(size: 24)
            .foregroundColor(OmiColors.textTertiary)
          Text(emptyStateTitle)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textSecondary)
          Text(emptyStateSubtitle)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
          Spacer()
        }
        .frame(height: 200)
      } else {
        ScrollView {
          LazyVStack(alignment: .leading, spacing: 0) {
            ForEach(chatProvider.groupedSessions, id: \.0) { group, sessions in
              // Group header
              Text(group)
                .scaledFont(size: 11, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 6)

              // Sessions in group
              ForEach(sessions) { session in
                HistorySessionRow(
                  session: session,
                  isSelected: chatProvider.currentSession?.id == session.id,
                  isDeleting: chatProvider.deletingSessionIds.contains(session.id),
                  onSelect: {
                    Task {
                      await chatProvider.selectSession(session)
                      onSelect()
                    }
                  },
                  onDelete: {
                    Task {
                      await chatProvider.deleteSession(session)
                    }
                  },
                  onToggleStar: {
                    Task {
                      await chatProvider.toggleStarred(session)
                    }
                  },
                  onRename: { newTitle in
                    Task {
                      await chatProvider.updateSessionTitle(session, title: newTitle)
                    }
                  }
                )
              }
            }
          }
          .padding(.bottom, 12)
        }
        .frame(maxHeight: 400)
      }
    }
    .frame(width: 320)
    .background(OmiColors.backgroundPrimary)
  }

  private var emptyStateIcon: String {
    if !chatProvider.searchQuery.isEmpty {
      return "magnifyingglass"
    } else if chatProvider.showStarredOnly {
      return "star"
    } else {
      return "bubble.left.and.bubble.right"
    }
  }

  private var emptyStateTitle: String {
    if !chatProvider.searchQuery.isEmpty {
      return "No results"
    } else if chatProvider.showStarredOnly {
      return "No starred chats"
    } else {
      return "No chats yet"
    }
  }

  private var emptyStateSubtitle: String {
    if !chatProvider.searchQuery.isEmpty {
      return "Try a different search"
    } else if chatProvider.showStarredOnly {
      return "Star a chat to see it here"
    } else {
      return "Start a conversation"
    }
  }
}

// MARK: - History Session Row

struct HistorySessionRow: View {
  let session: ChatSession
  let isSelected: Bool
  var isDeleting: Bool = false
  let onSelect: () -> Void
  let onDelete: () -> Void
  let onToggleStar: () -> Void
  let onRename: (String) -> Void

  @State private var isHovering = false
  @State private var showDeleteConfirm = false
  @State private var isEditing = false
  @State private var editedTitle = ""
  @FocusState private var isTitleFocused: Bool

  var body: some View {
    Button(action: {
      if !isEditing {
        onSelect()
      }
    }) {
      HStack(spacing: 8) {
        // Star indicator
        if session.starred {
          Image(systemName: "star.fill")
            .scaledFont(size: 10)
            .foregroundColor(.yellow)
        }

        VStack(alignment: .leading, spacing: 2) {
          if isEditing {
            TextField("Chat title", text: $editedTitle)
              .textFieldStyle(.plain)
              .scaledFont(size: 13, weight: isSelected ? .semibold : .regular)
              .foregroundColor(isSelected ? OmiColors.purplePrimary : OmiColors.textPrimary)
              .focused($isTitleFocused)
              .onSubmit { saveTitle() }
              .onExitCommand { cancelEditing() }
          } else {
            Text(session.title)
              .scaledFont(size: 13, weight: isSelected ? .semibold : .regular)
              .foregroundColor(isSelected ? OmiColors.purplePrimary : OmiColors.textPrimary)
              .lineLimit(1)
          }

          if !isEditing {
            HStack(spacing: 4) {
              if let preview = session.preview, !preview.isEmpty,
                !preview.hasPrefix("[Protected"), !preview.hasPrefix("[Encrypted")
              {
                Text(preview)
                  .lineLimit(1)
              }
              Text("·")
              Text(session.createdAt, style: .relative)
            }
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
          }
        }

        Spacer()

        if isDeleting {
          ProgressView()
            .scaleEffect(0.5)
            .frame(width: 14, height: 14)
        }

        // Action buttons on hover
        if isHovering && !isEditing && !isDeleting {
          HStack(spacing: 6) {
            // Rename button
            Button(action: startEditing) {
              Image(systemName: "pencil")
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
            }
            .buttonStyle(.plain)

            // Star button
            Button(action: onToggleStar) {
              Image(systemName: session.starred ? "star.fill" : "star")
                .scaledFont(size: 11)
                .foregroundColor(session.starred ? .yellow : OmiColors.textTertiary)
            }
            .buttonStyle(.plain)

            // Delete button
            Button(action: { showDeleteConfirm = true }) {
              Image(systemName: "trash")
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
          }
        }
      }
      .padding(.horizontal, 16)
      .padding(.vertical, 8)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        isSelected
          ? OmiColors.backgroundSecondary
          : (isHovering ? OmiColors.backgroundSecondary.opacity(0.5) : Color.clear)
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .onTapGesture(count: 2) { startEditing() }
    .alert("Delete Chat?", isPresented: $showDeleteConfirm) {
      Button("Cancel", role: .cancel) {}
      Button("Delete", role: .destructive) {
        onDelete()
      }
    } message: {
      Text("This will permanently delete this chat and all its messages.")
    }
  }

  private func startEditing() {
    editedTitle = session.title
    isEditing = true
    isTitleFocused = true
  }

  private func saveTitle() {
    let trimmed = editedTitle.trimmingCharacters(in: .whitespacesAndNewlines)
    if !trimmed.isEmpty && trimmed != session.title {
      onRename(trimmed)
    }
    isEditing = false
  }

  private func cancelEditing() {
    isEditing = false
    editedTitle = session.title
  }
}

#if canImport(PreviewsMacros)
#Preview {
  ChatPage(appProvider: AppProvider(), chatProvider: ChatProvider())
    .frame(width: 600, height: 700)
}
#endif
