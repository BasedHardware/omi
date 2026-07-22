import SwiftUI

/// The chat tab: the SAME timeline as the main chat window, rendered by the
/// shared ChatMessagesView over ChatProvider.mainInstance (INV-6: the notch is
/// an I/O device over the one kernel transcript, never a second store). Also
/// owns the height measure loop that lets the panel grow to fit the answer.
struct NotchChatView: View {
  @ObservedObject var chatProvider: ChatProvider
  @EnvironmentObject var barState: FloatingControlBarState
  /// Reports the transcript's measured content height; NotchView filters
  /// sub-4pt jitter before writing it into the view model.
  let onBodyHeightChange: (CGFloat) -> Void

  @State private var transcriptHeight: CGFloat = 0
  @State private var liveStripHeight: CGFloat = 0

  var body: some View {
    VStack(spacing: 0) {
      ChatMessagesView(
        messages: chatProvider.messages,
        isSending: chatProvider.isSending,
        hasMoreMessages: chatProvider.hasMoreMessages,
        isLoadingMoreMessages: chatProvider.isLoadingMoreMessages,
        isLoadingInitial: (chatProvider.isLoading || chatProvider.isLoadingSessions)
          && !chatProvider.isClearing,
        app: nil,
        onLoadMore: { await chatProvider.loadMoreMessages() },
        onRate: { messageId, rating in
          Task { await chatProvider.rateMessage(messageId, rating: rating) }
        },
        localSendToken: chatProvider.localSendToken,
        onCancelTurn: { [weak chatProvider] in chatProvider?.stopAgent(owner: .mainChat) },
        onOpenAgent: { agentID, completion in
          FloatingControlBarManager.shared.openAgentChatFromTimeline(agentID: agentID, completion: completion)
        },
        onOpenAgentRef: { ref, completion in
          FloatingControlBarManager.shared.openAgentChatFromTimeline(ref: ref, completion: completion)
        },
        horizontalContentPadding: 10,
        onContentHeightChange: { height in
          transcriptHeight = height
          onBodyHeightChange(height + liveStripHeight)
        },
        welcomeContent: { welcome }
      )

      if showsLiveVoiceTurn {
        liveVoiceStrip
          .onGeometryChange(for: CGFloat.self) { proxy in
            proxy.size.height
          } action: { height in
            liveStripHeight = height
            onBodyHeightChange(transcriptHeight + height)
          }
      }
    }
    .onChange(of: showsLiveVoiceTurn) { _, shows in
      if !shows {
        liveStripHeight = 0
        onBodyHeightChange(transcriptHeight)
      }
    }
  }

  // MARK: - Live voice turn

  /// Hub voice turns journal their exchange only at turn end; this strip
  /// renders the in-flight question + streaming reply until the journaled
  /// pair lands on the shared timeline.
  private var showsLiveVoiceTurn: Bool {
    guard barState.isVoicePresentationActive else { return false }
    guard !barState.liveVoiceUserText.isEmpty || !barState.liveVoiceAssistantText.isEmpty else {
      return false
    }
    // Once the journaled pair is on the timeline, the strip would duplicate it.
    if let lastUser = chatProvider.messages.last(where: { $0.sender == .user }),
      lastUser.text == barState.liveVoiceUserText
    {
      return false
    }
    return true
  }

  private var liveVoiceStrip: some View {
    VStack(alignment: .leading, spacing: 8) {
      if !barState.liveVoiceUserText.isEmpty {
        HStack {
          Spacer(minLength: 40)
          Text(barState.liveVoiceUserText)
            .font(.system(size: 12))
            .foregroundStyle(.white.opacity(0.92))
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(Capsule().fill(Color.white.opacity(0.14)))
        }
      }
      HStack(alignment: .top, spacing: 8) {
        if barState.liveVoiceAssistantText.isEmpty {
          OmiThinkingMark()
            .frame(width: 16, height: 16)
          Text(barState.isVoiceListening ? "Listening…" : "Thinking…")
            .font(.system(size: 12))
            .foregroundStyle(.white.opacity(0.5))
        } else {
          Text(barState.liveVoiceAssistantText)
            .font(.system(size: 12.5))
            .foregroundStyle(.white.opacity(0.92))
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer(minLength: 0)
      }
    }
    .padding(.horizontal, 12)
    .padding(.vertical, 8)
    .transition(.opacity)
  }

  private var welcome: some View {
    VStack(spacing: 6) {
      Text("Ask Omi anything")
        .font(.system(size: 13, weight: .semibold))
        .foregroundStyle(.white.opacity(0.9))
      Text("Your conversation continues in the main window")
        .font(.system(size: 11))
        .foregroundStyle(.white.opacity(0.5))
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, 18)
  }
}
