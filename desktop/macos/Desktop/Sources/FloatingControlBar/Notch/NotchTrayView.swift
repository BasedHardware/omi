import SwiftUI
import UniformTypeIdentifiers

/// The floating glass pill below the notch body. One slot, two contents: the
/// composer (attach + growing text field + send) and the Stop pill while a
/// response streams. Bound to the shared provider: one draft, one timeline.
struct NotchTrayView: View {
  @ObservedObject var chatProvider: ChatProvider
  @EnvironmentObject var barState: FloatingControlBarState

  @FocusState private var inputFocused: Bool
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @State private var stopDimmed = false

  var body: some View {
    Group {
      if barState.isVoiceListening {
        listeningPill
      } else if chatProvider.isSending {
        stopPill
      } else {
        composer
      }
    }
    .frame(maxWidth: .infinity)
    .animation(.snappy, value: chatProvider.isSending)
    .animation(.snappy, value: barState.isVoiceListening)
  }

  // MARK: - Listening (the composer becomes the live waveform during PTT)

  private var listeningPill: some View {
    HStack(spacing: 10) {
      VoiceWaveformBars(isActive: true)
      Text(barState.liveVoiceUserText.isEmpty ? "Listening…" : barState.liveVoiceUserText)
        .font(.system(size: 12))
        .foregroundStyle(.white.opacity(barState.liveVoiceUserText.isEmpty ? 0.5 : 0.85))
        .lineLimit(1)
        .truncationMode(.head)
      Spacer(minLength: 0)
      Image(systemName: "mic.fill")
        .font(.system(size: 12, weight: .medium))
        .foregroundStyle(Color(red: 1.0, green: 0.45, blue: 0.45))
      Button(action: { PushToTalkManager.shared.cancelListening() }) {
        Image(systemName: "stop.fill")
          .font(.system(size: 11, weight: .semibold))
          .foregroundStyle(.black)
          .frame(width: 26, height: 26)
          .background(Circle().fill(.white))
      }
      .buttonStyle(.plain)
      .help("Stop listening")
      .accessibilityLabel("Stop listening")
    }
    .padding(.leading, 16)
    .padding(.trailing, 6)
    .padding(.vertical, 9)
    .trayGlass()
  }

  // MARK: - Composer

  private var composer: some View {
    VStack(spacing: 6) {
      if !chatProvider.pendingAttachments.isEmpty {
        attachmentChips
      }

      HStack(spacing: 10) {
        Button(action: pickAttachments) {
          Image(systemName: "paperclip")
            .font(.system(size: 13, weight: .medium))
            .foregroundStyle(.secondary)
            .frame(width: 26, height: 26)
        }
        .buttonStyle(.plain)
        .help("Attach files")
        .accessibilityLabel("Attach files")

        TextField(
          "",
          text: $chatProvider.draftText,
          prompt: Text("Ask Omi…").foregroundStyle(.secondary),
          axis: .vertical
        )
        .textFieldStyle(.plain)
        .font(.system(size: 13))
        .lineLimit(1...3)
        .focused($inputFocused)
        // Return sends; Shift+Return inserts a newline (the field grows).
        // No .onSubmit — it would also fire on Shift+Return and send.
        .onKeyPress(.return) {
          if NSEvent.modifierFlags.contains(.shift) { return .ignored }
          send()
          return .handled
        }
        .frame(maxWidth: .infinity)

        Button(action: send) {
          Image(systemName: "arrow.up")
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(.black)
            .frame(width: 26, height: 26)
            .background(Circle().fill(canSend ? .white : .white.opacity(0.3)))
        }
        .buttonStyle(.plain)
        .disabled(!canSend)
        .accessibilityLabel("Send message")
      }
    }
    .padding(.leading, 16)
    .padding(.trailing, 6)
    .padding(.vertical, 6)
    .trayGlass()
    .onAppear { inputFocused = true }
    .onDrop(of: [UTType.fileURL], isTargeted: nil) { providers in
      handleDrop(providers)
    }
  }

  private var canSend: Bool {
    !chatProvider.draftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      || !chatProvider.pendingAttachments.isEmpty
  }

  private func send() {
    let text = chatProvider.draftText
    guard canSend else { return }
    AnalyticsManager.shared.chatMessageSent(
      messageLength: text.count, hasSelectedAppContext: false, source: "notch_chat")
    // Empty the field in this run loop so it repaints immediately; sendMainDraft
    // restores the text if the send never enters the timeline.
    chatProvider.draftText = ""
    inputFocused = true
    Task { await chatProvider.sendMainDraft(text) }
  }

  // MARK: - Attachments

  private var attachmentChips: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: 6) {
        ForEach(chatProvider.pendingAttachments, id: \.id) { attachment in
          HStack(spacing: 4) {
            Image(systemName: "doc.fill")
              .font(.system(size: 9))
            Text(attachment.fileName)
              .font(.system(size: 10, weight: .medium))
              .lineLimit(1)
              .truncationMode(.middle)
              .frame(maxWidth: 120)
            Button {
              chatProvider.removePendingAttachment(id: attachment.id)
            } label: {
              Image(systemName: "xmark")
                .font(.system(size: 8, weight: .bold))
            }
            .buttonStyle(.plain)
          }
          .foregroundStyle(.white.opacity(0.8))
          .padding(.horizontal, 8)
          .padding(.vertical, 4)
          .background(Capsule().fill(Color.white.opacity(0.12)))
        }
      }
    }
    .padding(.top, 4)
  }

  private func pickAttachments() {
    let panel = NSOpenPanel()
    panel.allowsMultipleSelection = true
    panel.canChooseDirectories = false
    panel.begin { response in
      guard response == .OK else { return }
      let attachments = panel.urls.compactMap { ChatAttachment.from(url: $0) }
      Task { @MainActor in chatProvider.addAttachments(attachments) }
    }
  }

  private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
    var handled = false
    for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
      handled = true
      _ = provider.loadObject(ofClass: URL.self) { url, _ in
        guard let url, let attachment = ChatAttachment.from(url: url) else { return }
        Task { @MainActor in chatProvider.addAttachments([attachment]) }
      }
    }
    return handled
  }

  // MARK: - Stop

  private var stopPill: some View {
    Button {
      chatProvider.stopAgent(owner: .mainChat)
    } label: {
      HStack(spacing: 6) {
        Image(systemName: "stop.fill")
          .font(.system(size: 10, weight: .semibold))
        Text("Stop")
          .font(.system(size: 11, weight: .medium))
      }
      .foregroundStyle(.white.opacity(0.9))
      .padding(.horizontal, 16)
      .padding(.vertical, 8)
      .trayGlass()
      .opacity(stopDimmed ? 0.6 : 1)
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .accessibilityLabel("Stop response")
    .onAppear {
      guard !reduceMotion else { return }
      withAnimation(.easeInOut(duration: 1).repeatForever(autoreverses: true)) {
        stopDimmed = true
      }
    }
  }
}

extension View {
  /// Liquid-Glass capsule with a crisp rim + soft float shadow so the pill
  /// reads clearly over any desktop; HUD blur below macOS 26.
  @ViewBuilder
  fileprivate func trayGlass() -> some View {
    if #available(macOS 26.0, *) {
      glassEffect(.regular, in: .capsule)
        .overlay(Capsule().strokeBorder(.white.opacity(0.22), lineWidth: 0.75))
        .shadow(color: .black.opacity(0.32), radius: 12, y: 5)
    } else {
      background(
        VisualEffectView(material: .hudWindow, blendingMode: .behindWindow, alphaValue: 1)
          .clipShape(Capsule())
      )
      .background(Capsule().fill(Color.black.opacity(0.3)))
      .overlay(Capsule().strokeBorder(.white.opacity(0.22), lineWidth: 0.75))
      .shadow(color: .black.opacity(0.32), radius: 12, y: 5)
    }
  }
}
