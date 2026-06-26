import SwiftUI

// MARK: - AI Clone Page

struct AIClonePage: View {
  @StateObject private var service = AICloneService.shared
  @State private var showTelegramSetup = false
  @State private var telegramTokenDraft = ""
  @State private var editingMessageId: String? = nil
  @State private var editText = ""

  var body: some View {
    VStack(spacing: 0) {
      // Header
      pageHeader

      Divider().opacity(0.2)

      if service.pendingMessages.isEmpty && !service.isEnabled {
        // Empty state — not enabled yet
        emptyState
      } else {
        HStack(alignment: .top, spacing: 0) {
          // Left: platform connections
          platformPanel
            .frame(width: 260)

          Divider().opacity(0.2)

          // Right: message feed
          messageFeed
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .onAppear {
      telegramTokenDraft = service.telegramBotToken
      service.refreshConnectivity()
    }
  }

  // MARK: - Header

  private var pageHeader: some View {
    HStack(spacing: 14) {
      Image(systemName: "person.2.circle.fill")
        .scaledFont(size: 26)
        .foregroundColor(OmiColors.purplePrimary)

      VStack(alignment: .leading, spacing: 2) {
        Text("AI Clone")
          .scaledFont(size: 20, weight: .bold)
          .foregroundColor(OmiColors.textPrimary)
        Text("Respond to messages as you, powered by your memories")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
      }

      Spacer()

      // Master enable toggle
      HStack(spacing: 8) {
        Text(service.isEnabled ? "Active" : "Paused")
          .scaledFont(size: 13, weight: .medium)
          .foregroundColor(service.isEnabled ? OmiColors.success : OmiColors.textTertiary)

        Toggle("", isOn: Binding(
          get: { service.isEnabled },
          set: { service.enable($0) }
        ))
        .toggleStyle(.switch)
        .labelsHidden()
        .tint(OmiColors.purplePrimary)
      }
    }
    .padding(.horizontal, 24)
    .padding(.vertical, 18)
  }

  // MARK: - Empty State

  private var emptyState: some View {
    VStack(spacing: 24) {
      Spacer()

      Image(systemName: "person.2.circle")
        .scaledFont(size: 60)
        .foregroundColor(OmiColors.purplePrimary.opacity(0.5))

      VStack(spacing: 8) {
        Text("Meet Your AI Clone")
          .scaledFont(size: 22, weight: .bold)
          .foregroundColor(OmiColors.textPrimary)

        Text("Omi reads your messages and drafts replies in your voice,\nbased on your memories and communication style.")
          .scaledFont(size: 14)
          .foregroundColor(OmiColors.textSecondary)
          .multilineTextAlignment(.center)
      }

      HStack(spacing: 12) {
        // iMessage setup card
        platformSetupCard(
          icon: "message.fill",
          color: .green,
          name: "iMessage",
          description: "Auto-detect messages\nfrom your Mac",
          isConnected: service.iMessageConnected,
          action: {
            if !service.iMessageConnected {
              NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")!)
            }
          }
        )

        // Telegram setup card
        platformSetupCard(
          icon: "paperplane.fill",
          color: Color(red: 0.2, green: 0.6, blue: 1.0),
          name: "Telegram",
          description: "Connect via your\npersonal bot",
          isConnected: !service.telegramBotToken.isEmpty,
          action: { showTelegramSetup = true }
        )

        // WhatsApp (coming soon)
        platformSetupCard(
          icon: "phone.fill",
          color: Color(red: 0.15, green: 0.7, blue: 0.3),
          name: "WhatsApp",
          description: "Coming soon",
          isConnected: false,
          isComingSoon: true,
          action: {}
        )
      }

      Button(action: { service.enable(true) }) {
        Text("Enable AI Clone")
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(.white)
          .padding(.horizontal, 28)
          .padding(.vertical, 12)
          .background(
            RoundedRectangle(cornerRadius: 12)
              .fill(OmiColors.purplePrimary)
          )
      }
      .buttonStyle(.plain)

      Spacer()
    }
    .padding(.horizontal, 40)
    .sheet(isPresented: $showTelegramSetup) {
      telegramSetupSheet
    }
  }

  // MARK: - Platform Panel (left sidebar when active)

  private var platformPanel: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        Text("Connected Platforms")
          .scaledFont(size: 12, weight: .semibold)
          .foregroundColor(OmiColors.textTertiary)
          .padding(.top, 20)
          .padding(.horizontal, 16)

        // iMessage
        platformRow(
          icon: "message.fill",
          color: .green,
          name: "iMessage",
          isConnected: service.iMessageConnected,
          statusLabel: service.iMessageConnected ? "Monitoring" : "Needs Full Disk Access",
          action: {
            if !service.iMessageConnected {
              NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")!)
            }
          }
        )

        // Telegram
        platformRow(
          icon: "paperplane.fill",
          color: Color(red: 0.2, green: 0.6, blue: 1.0),
          name: "Telegram",
          isConnected: !service.telegramBotToken.isEmpty,
          statusLabel: service.telegramBotToken.isEmpty ? "Tap to set up bot" : "Bot connected",
          action: { showTelegramSetup = true }
        )

        // WhatsApp
        platformRow(
          icon: "phone.fill",
          color: Color(red: 0.15, green: 0.7, blue: 0.3),
          name: "WhatsApp",
          isConnected: false,
          statusLabel: "Coming soon",
          isDisabled: true,
          action: {}
        )

        Divider().opacity(0.2).padding(.horizontal, 16)

        // Auto-reply toggle
        VStack(alignment: .leading, spacing: 4) {
          Text("Auto-Reply")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textTertiary)
            .padding(.horizontal, 16)

          Toggle(isOn: Binding(
            get: { service.autoReply },
            set: { v in
              service.autoReply = v
              UserDefaults.standard.set(v, forKey: "aiCloneAutoReply")
            }
          )) {
            VStack(alignment: .leading, spacing: 2) {
              Text("Send automatically")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
              Text("Skips approval step")
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
            }
          }
          .toggleStyle(.switch)
          .tint(OmiColors.purplePrimary)
          .padding(.horizontal, 16)
          .padding(.vertical, 8)
        }

        // Stats
        let pending = service.pendingMessages.filter { $0.status == .pending }.count
        if pending > 0 {
          HStack {
            Image(systemName: "clock.fill")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.warning)
            Text("\(pending) waiting for approval")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textSecondary)
          }
          .padding(.horizontal, 16)
        }

        Spacer()
      }
    }
    .sheet(isPresented: $showTelegramSetup) {
      telegramSetupSheet
    }
  }

  // MARK: - Platform Row

  private func platformRow(
    icon: String,
    color: Color,
    name: String,
    isConnected: Bool,
    statusLabel: String,
    isDisabled: Bool = false,
    action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      HStack(spacing: 12) {
        ZStack {
          Circle()
            .fill(color.opacity(isDisabled ? 0.15 : 0.18))
            .frame(width: 34, height: 34)
          Image(systemName: icon)
            .scaledFont(size: 14)
            .foregroundColor(isDisabled ? OmiColors.textQuaternary : color)
        }

        VStack(alignment: .leading, spacing: 2) {
          Text(name)
            .scaledFont(size: 13, weight: .medium)
            .foregroundColor(isDisabled ? OmiColors.textQuaternary : OmiColors.textPrimary)
          Text(statusLabel)
            .scaledFont(size: 11)
            .foregroundColor(isConnected ? OmiColors.success : (isDisabled ? OmiColors.textQuaternary : OmiColors.textTertiary))
        }

        Spacer()

        Circle()
          .fill(isConnected ? OmiColors.success : OmiColors.textQuaternary.opacity(0.4))
          .frame(width: 8, height: 8)
      }
      .padding(.horizontal, 14)
      .padding(.vertical, 10)
      .background(
        RoundedRectangle(cornerRadius: 10)
          .fill(OmiColors.backgroundTertiary.opacity(0.5))
      )
      .padding(.horizontal, 12)
    }
    .buttonStyle(.plain)
    .disabled(isDisabled)
  }

  // MARK: - Message Feed

  private var messageFeed: some View {
    Group {
      if service.pendingMessages.isEmpty {
        VStack(spacing: 16) {
          Spacer()
          Image(systemName: "tray")
            .scaledFont(size: 40)
            .foregroundColor(OmiColors.textQuaternary)
          Text("No messages yet")
            .scaledFont(size: 15)
            .foregroundColor(OmiColors.textTertiary)
          Text("New messages will appear here when they arrive")
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textQuaternary)
          Spacer()
        }
      } else {
        ScrollView {
          LazyVStack(spacing: 12) {
            ForEach(service.pendingMessages) { msg in
              messageCard(msg)
                .transition(.asymmetric(
                  insertion: .move(edge: .top).combined(with: .opacity),
                  removal: .opacity
                ))
            }
          }
          .padding(20)
          .animation(.easeInOut(duration: 0.25), value: service.pendingMessages.count)
        }
      }
    }
  }

  // MARK: - Message Card

  @ViewBuilder
  private func messageCard(_ msg: CloneMessage) -> some View {
    let isEditing = editingMessageId == msg.id

    VStack(alignment: .leading, spacing: 12) {
      // Platform + Sender + Time
      HStack(spacing: 10) {
        platformIcon(msg.platform)

        VStack(alignment: .leading, spacing: 1) {
          Text(msg.sender)
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text(relativeTime(msg.createdAt))
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
        }

        Spacer()

        statusBadge(msg.status)
      }

      // Incoming message
      VStack(alignment: .leading, spacing: 4) {
        Text("Received")
          .scaledFont(size: 10, weight: .semibold)
          .foregroundColor(OmiColors.textQuaternary)
          .textCase(.uppercase)

        Text(msg.incoming)
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)
          .padding(.horizontal, 12)
          .padding(.vertical, 8)
          .background(
            RoundedRectangle(cornerRadius: 10)
              .fill(OmiColors.backgroundTertiary.opacity(0.7))
          )
      }

      // AI Draft
      VStack(alignment: .leading, spacing: 4) {
        HStack {
          Text("AI Draft")
            .scaledFont(size: 10, weight: .semibold)
            .foregroundColor(OmiColors.purplePrimary.opacity(0.8))
            .textCase(.uppercase)
          Spacer()
          if msg.status == .pending {
            Button(action: {
              if isEditing {
                editingMessageId = nil
              } else {
                editText = msg.draftReply
                editingMessageId = msg.id
              }
            }) {
              Text(isEditing ? "Done" : "Edit")
                .scaledFont(size: 11, weight: .medium)
                .foregroundColor(OmiColors.purplePrimary)
            }
            .buttonStyle(.plain)
          }
        }

        if isEditing {
          TextEditor(text: $editText)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textPrimary)
            .frame(minHeight: 60, maxHeight: 120)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
              RoundedRectangle(cornerRadius: 10)
                .fill(OmiColors.backgroundTertiary)
                .overlay(
                  RoundedRectangle(cornerRadius: 10)
                    .stroke(OmiColors.purplePrimary.opacity(0.4), lineWidth: 1)
                )
            )
            .scrollContentBackground(.hidden)
        } else {
          Text(msg.draftReply)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
              RoundedRectangle(cornerRadius: 10)
                .fill(OmiColors.purplePrimary.opacity(0.12))
                .overlay(
                  RoundedRectangle(cornerRadius: 10)
                    .stroke(OmiColors.purplePrimary.opacity(0.2), lineWidth: 1)
                )
            )
        }
      }

      // Action buttons
      if msg.status == .pending {
        HStack(spacing: 10) {
          Button(action: {
            Task {
              if isEditing {
                await service.editAndSend(msg.id, editedText: editText)
                editingMessageId = nil
              } else {
                await service.approveMessage(msg.id)
              }
            }
          }) {
            Label(isEditing ? "Send Edited" : "Send", systemImage: "paperplane.fill")
              .scaledFont(size: 13, weight: .semibold)
              .foregroundColor(.white)
              .padding(.horizontal, 16)
              .padding(.vertical, 8)
              .background(
                RoundedRectangle(cornerRadius: 9)
                  .fill(OmiColors.purplePrimary)
              )
          }
          .buttonStyle(.plain)

          Button(action: {
            Task { await service.dismissMessage(msg.id) }
          }) {
            Text("Dismiss")
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textSecondary)
              .padding(.horizontal, 16)
              .padding(.vertical, 8)
              .background(
                RoundedRectangle(cornerRadius: 9)
                  .fill(OmiColors.backgroundTertiary)
              )
          }
          .buttonStyle(.plain)

          if msg.platform == "imessage" && msg.status == .pending {
            Spacer()
            iMessageSendHint
          }
        }
      }
    }
    .padding(16)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(OmiColors.backgroundSecondary.opacity(0.7))
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .stroke(OmiColors.border.opacity(0.15), lineWidth: 1)
        )
    )
  }

  // MARK: - Helpers

  private var iMessageSendHint: some View {
    HStack(spacing: 4) {
      Image(systemName: "info.circle")
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textQuaternary)
      Text("Copy & paste into Messages")
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textQuaternary)
    }
  }

  @ViewBuilder
  private func platformIcon(_ platform: String) -> some View {
    let (icon, color): (String, Color) = {
      switch platform {
      case "imessage": return ("message.fill", .green)
      case "telegram": return ("paperplane.fill", Color(red: 0.2, green: 0.6, blue: 1.0))
      case "whatsapp": return ("phone.fill", Color(red: 0.15, green: 0.7, blue: 0.3))
      default: return ("bubble.left.fill", OmiColors.purplePrimary)
      }
    }()

    ZStack {
      Circle()
        .fill(color.opacity(0.18))
        .frame(width: 32, height: 32)
      Image(systemName: icon)
        .scaledFont(size: 13)
        .foregroundColor(color)
    }
  }

  @ViewBuilder
  private func statusBadge(_ status: CloneMessage.CloneMessageStatus) -> some View {
    switch status {
    case .pending:
      Text("Pending")
        .scaledFont(size: 10, weight: .semibold)
        .foregroundColor(OmiColors.warning)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(RoundedRectangle(cornerRadius: 5).fill(OmiColors.warning.opacity(0.15)))
    case .sent:
      Label("Sent", systemImage: "checkmark")
        .scaledFont(size: 10, weight: .semibold)
        .foregroundColor(OmiColors.success)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(RoundedRectangle(cornerRadius: 5).fill(OmiColors.success.opacity(0.15)))
    case .dismissed:
      Text("Dismissed")
        .scaledFont(size: 10, weight: .semibold)
        .foregroundColor(OmiColors.textQuaternary)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(RoundedRectangle(cornerRadius: 5).fill(OmiColors.backgroundTertiary))
    case .approved:
      Label("Approved", systemImage: "checkmark")
        .scaledFont(size: 10, weight: .semibold)
        .foregroundColor(OmiColors.purplePrimary)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(RoundedRectangle(cornerRadius: 5).fill(OmiColors.purplePrimary.opacity(0.15)))
    }
  }

  private func platformSetupCard(
    icon: String,
    color: Color,
    name: String,
    description: String,
    isConnected: Bool,
    isComingSoon: Bool = false,
    action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      VStack(spacing: 12) {
        ZStack {
          Circle()
            .fill(color.opacity(isComingSoon ? 0.1 : 0.18))
            .frame(width: 48, height: 48)
          Image(systemName: icon)
            .scaledFont(size: 20)
            .foregroundColor(isComingSoon ? OmiColors.textQuaternary : color)
        }

        VStack(spacing: 4) {
          Text(name)
            .scaledFont(size: 14, weight: .semibold)
            .foregroundColor(isComingSoon ? OmiColors.textQuaternary : OmiColors.textPrimary)

          Text(description)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
            .multilineTextAlignment(.center)
        }

        if isComingSoon {
          Text("Soon")
            .scaledFont(size: 10, weight: .semibold)
            .foregroundColor(OmiColors.textQuaternary)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(RoundedRectangle(cornerRadius: 5).fill(OmiColors.backgroundTertiary))
        } else if isConnected {
          Label("Connected", systemImage: "checkmark.circle.fill")
            .scaledFont(size: 11, weight: .semibold)
            .foregroundColor(OmiColors.success)
        } else {
          Text("Set Up")
            .scaledFont(size: 11, weight: .semibold)
            .foregroundColor(OmiColors.purplePrimary)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(
              RoundedRectangle(cornerRadius: 6)
                .stroke(OmiColors.purplePrimary.opacity(0.5), lineWidth: 1)
            )
        }
      }
      .padding(20)
      .frame(width: 160)
      .background(
        RoundedRectangle(cornerRadius: 14)
          .fill(OmiColors.backgroundSecondary.opacity(0.7))
          .overlay(
            RoundedRectangle(cornerRadius: 14)
              .stroke(
                isConnected ? OmiColors.success.opacity(0.3) : OmiColors.border.opacity(0.2),
                lineWidth: 1
              )
          )
      )
    }
    .buttonStyle(.plain)
    .disabled(isComingSoon)
  }

  private func relativeTime(_ date: Date) -> String {
    let seconds = Int(-date.timeIntervalSinceNow)
    if seconds < 60 { return "just now" }
    if seconds < 3600 { return "\(seconds / 60)m ago" }
    if seconds < 86400 { return "\(seconds / 3600)h ago" }
    let formatter = DateFormatter()
    formatter.dateStyle = .short
    formatter.timeStyle = .none
    return formatter.string(from: date)
  }

  // MARK: - Telegram Setup Sheet

  private var telegramSetupSheet: some View {
    VStack(alignment: .leading, spacing: 20) {
      HStack {
        Text("Connect Telegram Bot")
          .scaledFont(size: 18, weight: .bold)
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        Button(action: { showTelegramSetup = false }) {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: 20)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }

      VStack(alignment: .leading, spacing: 8) {
        stepRow(number: "1", text: "Open Telegram and message **@BotFather**")
        stepRow(number: "2", text: "Send **/newbot** and follow the prompts")
        stepRow(number: "3", text: "Copy the **API token** you receive")
        stepRow(number: "4", text: "Paste it below — Omi will poll for new messages")
      }
      .padding(16)
      .background(
        RoundedRectangle(cornerRadius: 12)
          .fill(OmiColors.backgroundTertiary.opacity(0.5))
      )

      VStack(alignment: .leading, spacing: 8) {
        Text("Bot Token")
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)

        TextField("123456:ABCdef...", text: $telegramTokenDraft)
          .textFieldStyle(.plain)
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textPrimary)
          .padding(12)
          .background(
            RoundedRectangle(cornerRadius: 10)
              .fill(OmiColors.backgroundTertiary)
              .overlay(
                RoundedRectangle(cornerRadius: 10)
                  .stroke(OmiColors.border.opacity(0.3), lineWidth: 1)
              )
          )
      }

      HStack(spacing: 12) {
        Spacer()
        Button("Cancel") {
          showTelegramSetup = false
          telegramTokenDraft = service.telegramBotToken
        }
        .buttonStyle(.plain)
        .foregroundColor(OmiColors.textSecondary)

        Button("Connect") {
          service.saveTelegramToken(telegramTokenDraft)
          showTelegramSetup = false
        }
        .buttonStyle(.plain)
        .foregroundColor(.white)
        .padding(.horizontal, 20)
        .padding(.vertical, 9)
        .background(
          RoundedRectangle(cornerRadius: 10)
            .fill(telegramTokenDraft.count > 10 ? OmiColors.purplePrimary : OmiColors.textQuaternary.opacity(0.3))
        )
        .disabled(telegramTokenDraft.count < 10)
      }
    }
    .padding(28)
    .frame(width: 460)
    .background(OmiColors.backgroundPrimary)
    .preferredColorScheme(.dark)
  }

  private func stepRow(number: String, text: String) -> some View {
    HStack(alignment: .top, spacing: 12) {
      ZStack {
        Circle()
          .fill(OmiColors.purplePrimary.opacity(0.2))
          .frame(width: 22, height: 22)
        Text(number)
          .scaledFont(size: 11, weight: .bold)
          .foregroundColor(OmiColors.purplePrimary)
      }
      Text((try? AttributedString(markdown: text)) ?? AttributedString(text))
        .scaledFont(size: 13)
        .foregroundColor(OmiColors.textSecondary)
    }
  }
}
