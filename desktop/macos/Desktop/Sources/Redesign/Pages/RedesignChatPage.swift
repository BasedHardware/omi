import SwiftUI

/// The "Ask omi" screen — mockup `ask.html`, live-wired to the real `ChatProvider`.
///
/// Layout mirrors the mockup: a fixed header (current question + History affordance),
/// a scrolling centered column (max 720) of exchanges — the user's message as an ink
/// `.bubble.out` (ink fill, white text, right-aligned) and omi's answer as plain text
/// with a small source line above — and a fixed footer composer ("Ask a follow-up…").
///
/// Warm-paper light mode, monochrome ink accent, no purple.
struct RedesignChatPage: View {
  @ObservedObject var appProvider: AppProvider
  @ObservedObject var chatProvider: ChatProvider

  @State private var draft: String = ""

  private static let columnWidth: CGFloat = 720

  // MARK: - Exchanges

  /// A user question paired with the omi answer(s) that follow it.
  private struct Exchange: Identifiable {
    let id: String
    var question: ChatMessage?
    var answers: [ChatMessage]
  }

  /// Group the flat `messages` array into question → answer exchanges.
  private var exchanges: [Exchange] {
    var result: [Exchange] = []
    for message in chatProvider.messages {
      if message.sender == .user {
        result.append(Exchange(id: message.id, question: message, answers: []))
      } else {
        if result.isEmpty {
          result.append(Exchange(id: message.id, question: nil, answers: [message]))
        } else {
          result[result.count - 1].answers.append(message)
        }
      }
    }
    return result
  }

  /// The most recent user question — shown in the fixed header (mockup: the `.h3` title).
  private var currentQuestion: String {
    chatProvider.messages.last(where: { $0.sender == .user })?.text ?? "Ask omi anything"
  }

  private var nowLabel: String {
    let f = DateFormatter()
    f.dateFormat = "h:mm"
    return "Today, \(f.string(from: Date()))"
  }

  // MARK: - Body

  var body: some View {
    VStack(spacing: 0) {
      header
      Divider().overlay(Ink.hair)
      thread
      Divider().overlay(Ink.hair)
      footer
    }
    .background(Ink.canvas)
  }

  // MARK: - Header

  private var header: some View {
    HStack(alignment: .center, spacing: 12) {
      Text(currentQuestion)
        .inkH3()
        .lineLimit(1)
        .truncationMode(.tail)
      InkPill(text: nowLabel, systemImage: "clock")
      Spacer(minLength: 12)
      InkButton(title: "History", systemImage: "clock.arrow.circlepath", kind: .ghost, size: .sm) {
        NotificationCenter.default.post(name: .navigateToAIChatSettings, object: nil)
      }
    }
    .padding(.horizontal, 24)
    .padding(.vertical, 16)
    .background(Ink.soft)
  }

  // MARK: - Thread

  private var thread: some View {
    ScrollViewReader { proxy in
      ScrollView {
        VStack(alignment: .leading, spacing: 0) {
          if exchanges.isEmpty {
            emptyState
          } else {
            ForEach(Array(exchanges.enumerated()), id: \.element.id) { index, exchange in
              if index != 0 {
                Rectangle().fill(Ink.hair).frame(height: 1)
                  .padding(.top, 34)
                  .padding(.bottom, 34)
              }
              exchangeView(exchange)
            }
          }
          Color.clear.frame(height: 1).id("thread-bottom")
        }
        .frame(maxWidth: Self.columnWidth, alignment: .leading)
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.horizontal, 24)
        .padding(.top, 36)
        .padding(.bottom, 24)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .background(Ink.canvas)
      .onChange(of: chatProvider.messages.count) {
        withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo("thread-bottom", anchor: .bottom) }
      }
      .onChange(of: chatProvider.localSendToken) {
        withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo("thread-bottom", anchor: .bottom) }
      }
    }
  }

  private func exchangeView(_ exchange: Exchange) -> some View {
    VStack(alignment: .leading, spacing: 20) {
      if let question = exchange.question {
        HStack {
          Spacer(minLength: 60)
          outBubble(question.text)
        }
      }
      ForEach(exchange.answers) { answer in
        answerView(answer)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  /// The ink `.bubble.out` — ink fill, white text, right-aligned, tight bottom-right corner.
  private func outBubble(_ text: String) -> some View {
    Text(text)
      .font(InkFont.sans(13.5))
      .foregroundColor(Ink.accentInk)
      .lineSpacing(2)
      .padding(.horizontal, 13)
      .padding(.vertical, 9)
      .background(
        UnevenRoundedRectangle(
          topLeadingRadius: 16, bottomLeadingRadius: 16,
          bottomTrailingRadius: 5, topTrailingRadius: 16, style: .continuous
        )
        .fill(Ink.accent)
      )
      .frame(maxWidth: Self.columnWidth * 0.74, alignment: .trailing)
      .fixedSize(horizontal: false, vertical: true)
      .textSelection(.enabled)
  }

  @ViewBuilder
  private func answerView(_ answer: ChatMessage) -> some View {
    VStack(alignment: .leading, spacing: 14) {
      sourceLine(for: answer)

      let text = answerText(answer)
      if text.isEmpty && answer.isStreaming {
        ThinkingLine()
      } else {
        Text(text)
          .font(InkFont.sans(15))
          .foregroundColor(Ink.ink)
          .lineSpacing(5)
          .fixedSize(horizontal: false, vertical: true)
          .textSelection(.enabled)
      }

      if !answer.citations.isEmpty {
        FlowRow(spacing: 8) {
          ForEach(answer.citations) { citation in
            citeChip(citation)
          }
        }
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  /// Small muted source line above an omi answer (mockup `.src-line`).
  private func sourceLine(for answer: ChatMessage) -> some View {
    HStack(spacing: 7) {
      Image(systemName: "brain").font(.system(size: 12)).foregroundColor(Ink.muted)
      Text("From your memory, conversations, and screen this week")
        .font(InkFont.sans(13)).foregroundColor(Ink.muted)
    }
  }

  /// A citation chip (mockup `.cite`).
  private func citeChip(_ citation: Citation) -> some View {
    HStack(spacing: 6) {
      Image(systemName: citation.sourceType == .memory ? "sparkles" : "text.bubble")
        .font(.system(size: 11)).foregroundColor(Ink.body)
      Text(citation.title)
        .font(InkFont.sans(12)).foregroundColor(Ink.body)
        .lineLimit(1)
    }
    .padding(.horizontal, 9)
    .frame(height: 24)
    .background(
      RoundedRectangle(cornerRadius: 7, style: .continuous)
        .fill(Ink.surface2)
        .overlay(RoundedRectangle(cornerRadius: 7).strokeBorder(Ink.hair, lineWidth: 1))
    )
  }

  /// Prefer the streamed/persisted `text`; fall back to concatenated text content blocks.
  private func answerText(_ message: ChatMessage) -> String {
    let trimmed = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
    if !trimmed.isEmpty { return trimmed }
    let blockText = message.contentBlocks.compactMap { block -> String? in
      if case .text(_, let t) = block { return t }
      return nil
    }.joined(separator: "\n\n")
    return blockText.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  /// Personalized starter prompts (built from onboarding context), with a
  /// sensible fallback so the chat always offers dynamic suggestions.
  private var suggestions: [String] {
    let dynamic = PostOnboardingPromptSuggestions.suggestions()
    if !dynamic.isEmpty { return Array(dynamic.prefix(4)) }
    return [
      "What should I focus on today to achieve my goals?",
      "What did I spend my time on this week?",
      "What's the highest-leverage thing I can do next?",
      "Who am I overdue to reply to?",
    ]
  }

  private var emptyState: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("What do you want to know?")
        .inkDisplay(28)
      Text("I remember what you saw, said, and did — ask me anything and I'll answer from your own context.")
        .inkSmall()
        .fixedSize(horizontal: false, vertical: true)

      VStack(spacing: 10) {
        ForEach(suggestions, id: \.self) { suggestion in
          Button { sendSuggestion(suggestion) } label: { suggestionRow(suggestion) }
            .buttonStyle(.plain)
        }
      }
      .padding(.top, 10)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.top, 40)
  }

  private func suggestionRow(_ text: String) -> some View {
    HStack(spacing: 12) {
      Image(systemName: "sparkles").font(.system(size: 13)).foregroundColor(Ink.faint)
      Text(text).font(InkFont.sans(14, .medium)).foregroundColor(Ink.ink)
      Spacer()
      Image(systemName: "arrow.up.right").font(.system(size: 12)).foregroundColor(Ink.faint)
    }
    .padding(.horizontal, 16).frame(height: 52)
    .background(
      Capsule().fill(Ink.surface).overlay(Capsule().strokeBorder(Ink.hair, lineWidth: 1)))
    .contentShape(Capsule())
  }

  private func sendSuggestion(_ text: String) {
    guard !chatProvider.isSending else { return }
    AnalyticsManager.shared.chatMessageSent(
      messageLength: text.count, hasContext: false, source: "redesign_suggestion")
    Task { await chatProvider.sendMessage(text) }
  }

  // MARK: - Footer composer

  private var footer: some View {
    HStack(spacing: 10) {
      Image(systemName: "sparkles").font(.system(size: 15)).foregroundColor(Ink.faint)

      TextField("Ask a follow-up…", text: $draft)
        .textFieldStyle(.plain)
        .font(InkFont.sans(15))
        .foregroundColor(Ink.ink)
        .onSubmit(send)
        .disabled(chatProvider.isSending)

      if chatProvider.isSending {
        Button(action: { chatProvider.stopAgent() }) {
          Image(systemName: "stop.fill")
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(Ink.accentInk)
            .frame(width: 30, height: 30)
            .background(Circle().fill(Ink.accent))
        }
        .buttonStyle(.plain)
        .help("Stop")
      } else {
        Button(action: send) {
          Image(systemName: "arrow.up")
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(canSend ? Ink.accentInk : Ink.faint)
            .frame(width: 30, height: 30)
            .background(Circle().fill(canSend ? Ink.accent : Ink.surface2))
        }
        .buttonStyle(.plain)
        .disabled(!canSend)
        .keyboardShortcut(.return, modifiers: [])
        .help("Send")
      }
    }
    .padding(.horizontal, 16)
    .frame(height: 50)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.surface)
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Ink.hair2, lineWidth: 1))
    )
    .frame(maxWidth: Self.columnWidth, alignment: .center)
    .frame(maxWidth: .infinity, alignment: .center)
    .padding(.horizontal, 24)
    .padding(.vertical, 16)
    .background(Ink.soft)
  }

  private var canSend: Bool {
    !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !chatProvider.isSending
  }

  private func send() {
    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty, !chatProvider.isSending else { return }
    draft = ""
    AnalyticsManager.shared.chatMessageSent(
      messageLength: text.count, hasContext: false, source: "redesign_ask")
    Task { await chatProvider.sendMessage(text) }
  }
}

// MARK: - Thinking line (streaming placeholder)

/// A minimal three-dot pulse shown while omi's answer is still empty & streaming.
private struct ThinkingLine: View {
  @State private var phase = 0

  var body: some View {
    HStack(spacing: 5) {
      ForEach(0..<3, id: \.self) { i in
        Circle()
          .fill(Ink.muted)
          .frame(width: 6, height: 6)
          .scaleEffect(phase == i ? 1.15 : 0.7)
          .animation(.easeInOut(duration: 0.45).repeatForever().delay(Double(i) * 0.15), value: phase)
      }
    }
    .onAppear { phase = 1 }
  }
}

// MARK: - Flow layout (wrapping row for citation chips)

/// A simple wrapping HStack for the citation chips (mockup wraps them under the answer).
private struct FlowRow: Layout {
  var spacing: CGFloat = 8

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout Void) -> CGSize {
    let maxWidth = proposal.width ?? .infinity
    var rowWidth: CGFloat = 0
    var rowHeight: CGFloat = 0
    var totalHeight: CGFloat = 0
    for subview in subviews {
      let size = subview.sizeThatFits(.unspecified)
      if rowWidth > 0 && rowWidth + spacing + size.width > maxWidth {
        totalHeight += rowHeight + spacing
        rowWidth = size.width
        rowHeight = size.height
      } else {
        rowWidth += (rowWidth > 0 ? spacing : 0) + size.width
        rowHeight = max(rowHeight, size.height)
      }
    }
    totalHeight += rowHeight
    return CGSize(width: maxWidth == .infinity ? rowWidth : maxWidth, height: totalHeight)
  }

  func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout Void) {
    var x = bounds.minX
    var y = bounds.minY
    var rowHeight: CGFloat = 0
    for subview in subviews {
      let size = subview.sizeThatFits(.unspecified)
      if x > bounds.minX && x + size.width > bounds.maxX {
        x = bounds.minX
        y += rowHeight + spacing
        rowHeight = 0
      }
      subview.place(at: CGPoint(x: x, y: y), anchor: .topLeading, proposal: ProposedViewSize(size))
      x += size.width + spacing
      rowHeight = max(rowHeight, size.height)
    }
  }
}
