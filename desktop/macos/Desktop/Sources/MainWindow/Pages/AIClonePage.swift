import SwiftUI

// MARK: - AI Clone Page

struct AIClonePage: View {
  @StateObject private var service = AICloneService.shared
  @State private var showTelegramSetup = false
  @State private var showWhatsAppSetup = false
  @State private var editingMessageId: String? = nil
  @State private var editText = ""

  var body: some View {
    VStack(spacing: 0) {
      pageHeader
      Divider().opacity(0.2)

      if service.pendingMessages.isEmpty && !service.isEnabled {
        emptyState
      } else {
        HStack(alignment: .top, spacing: 0) {
          platformPanel.frame(width: 260)
          Divider().opacity(0.2)
          messageFeed
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .onAppear { service.refreshConnectivity() }
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

      HStack(spacing: 8) {
        Text(service.isEnabled ? "Active" : "Paused")
          .scaledFont(size: 13, weight: .medium)
          .foregroundColor(service.isEnabled ? OmiColors.success : OmiColors.textTertiary)
        Toggle("", isOn: Binding(get: { service.isEnabled }, set: { service.enable($0) }))
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
        platformSetupCard(
          icon: "message.fill", color: .green, name: "iMessage",
          description: "Reads & sends via\nMessages.app",
          isConnected: service.iMessageConnected,
          action: {
            if !service.iMessageConnected {
              NSWorkspace.shared.open(
                URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")!)
            }
          }
        )
        platformSetupCard(
          icon: "paperplane.fill", color: Color(red: 0.2, green: 0.6, blue: 1.0), name: "Telegram",
          description: "Your personal account\nvia phone + OTP",
          isConnected: service.telegramConnected,
          action: { showTelegramSetup = true }
        )
        platformSetupCard(
          icon: "phone.fill", color: Color(red: 0.15, green: 0.7, blue: 0.3), name: "WhatsApp",
          description: "Bot via WhatsApp\nCloud API",
          isConnected: service.whatsAppConfigured,
          action: { showWhatsAppSetup = true }
        )
      }

      Button(action: { service.enable(true) }) {
        Text("Enable AI Clone")
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(.white)
          .padding(.horizontal, 28).padding(.vertical, 12)
          .background(RoundedRectangle(cornerRadius: 12).fill(OmiColors.purplePrimary))
      }
      .buttonStyle(.plain)

      Spacer()
    }
    .padding(.horizontal, 40)
    .sheet(isPresented: $showTelegramSetup) { telegramSetupSheet }
    .sheet(isPresented: $showWhatsAppSetup) { whatsAppSetupSheet }
  }

  // MARK: - Platform Panel

  private var platformPanel: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        Text("Connected Platforms")
          .scaledFont(size: 12, weight: .semibold)
          .foregroundColor(OmiColors.textTertiary)
          .padding(.top, 20).padding(.horizontal, 16)

        platformRow(
          icon: "message.fill", color: .green, name: "iMessage",
          isConnected: service.iMessageConnected,
          statusLabel: service.iMessageConnected ? "Reads & sends via Messages" : "Grant Automation access",
          action: {
            if !service.iMessageConnected {
              NSWorkspace.shared.open(
                URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")!)
            }
          }
        )

        platformRow(
          icon: "paperplane.fill", color: Color(red: 0.2, green: 0.6, blue: 1.0), name: "Telegram",
          isConnected: service.telegramConnected,
          statusLabel: service.telegramConnected ? service.telegramDisplayName : "Tap to connect account",
          action: { showTelegramSetup = true }
        )

        platformRow(
          icon: "phone.fill", color: Color(red: 0.15, green: 0.7, blue: 0.3), name: "WhatsApp",
          isConnected: service.whatsAppConfigured,
          statusLabel: service.whatsAppConfigured ? service.whatsAppBotPhone : "Tap to set up bot",
          action: { showWhatsAppSetup = true }
        )

        Divider().opacity(0.2).padding(.horizontal, 16)

        VStack(alignment: .leading, spacing: 4) {
          Text("Auto-Reply")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textTertiary)
            .padding(.horizontal, 16)
          Toggle(isOn: Binding(
            get: { service.autoReply },
            set: { v in service.setAutoReply(v) }
          )) {
            VStack(alignment: .leading, spacing: 2) {
              Text("Send automatically")
                .scaledFont(size: 13, weight: .medium).foregroundColor(OmiColors.textPrimary)
              Text("Skips approval step")
                .scaledFont(size: 11).foregroundColor(OmiColors.textTertiary)
            }
          }
          .toggleStyle(.switch).tint(OmiColors.purplePrimary)
          .padding(.horizontal, 16).padding(.vertical, 8)
        }

        let pending = service.pendingMessages.filter { $0.status == .pending }.count
        if pending > 0 {
          HStack {
            Image(systemName: "clock.fill").scaledFont(size: 12).foregroundColor(OmiColors.warning)
            Text("\(pending) waiting for approval")
              .scaledFont(size: 12).foregroundColor(OmiColors.textSecondary)
          }
          .padding(.horizontal, 16)
        }

        Spacer()
      }
    }
    .sheet(isPresented: $showTelegramSetup) { telegramSetupSheet }
    .sheet(isPresented: $showWhatsAppSetup) { whatsAppSetupSheet }
  }

  // MARK: - Platform Row

  private func platformRow(
    icon: String, color: Color, name: String,
    isConnected: Bool, statusLabel: String,
    isDisabled: Bool = false, action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      HStack(spacing: 12) {
        ZStack {
          Circle().fill(color.opacity(isDisabled ? 0.15 : 0.18)).frame(width: 34, height: 34)
          Image(systemName: icon).scaledFont(size: 14)
            .foregroundColor(isDisabled ? OmiColors.textQuaternary : color)
        }
        VStack(alignment: .leading, spacing: 2) {
          Text(name).scaledFont(size: 13, weight: .medium)
            .foregroundColor(isDisabled ? OmiColors.textQuaternary : OmiColors.textPrimary)
          Text(statusLabel).scaledFont(size: 11)
            .foregroundColor(isConnected ? OmiColors.success : (isDisabled ? OmiColors.textQuaternary : OmiColors.textTertiary))
        }
        Spacer()
        Circle()
          .fill(isConnected ? OmiColors.success : OmiColors.textQuaternary.opacity(0.4))
          .frame(width: 8, height: 8)
      }
      .padding(.horizontal, 14).padding(.vertical, 10)
      .background(RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundTertiary.opacity(0.5)))
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
          Image(systemName: "tray").scaledFont(size: 40).foregroundColor(OmiColors.textQuaternary)
          Text("No messages yet").scaledFont(size: 15).foregroundColor(OmiColors.textTertiary)
          Text("New messages will appear here when they arrive")
            .scaledFont(size: 13).foregroundColor(OmiColors.textQuaternary)
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
      HStack(spacing: 10) {
        platformIcon(msg.platform)
        VStack(alignment: .leading, spacing: 1) {
          Text(msg.sender).scaledFont(size: 13, weight: .semibold).foregroundColor(OmiColors.textPrimary)
          Text(relativeTime(msg.createdAt)).scaledFont(size: 11).foregroundColor(OmiColors.textTertiary)
        }
        Spacer()
        statusBadge(msg.status)
      }

      VStack(alignment: .leading, spacing: 4) {
        Text("Received").scaledFont(size: 10, weight: .semibold)
          .foregroundColor(OmiColors.textQuaternary).textCase(.uppercase)
        Text(msg.incoming).scaledFont(size: 13).foregroundColor(OmiColors.textSecondary)
          .padding(.horizontal, 12).padding(.vertical, 8)
          .background(RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundTertiary.opacity(0.7)))
      }

      VStack(alignment: .leading, spacing: 4) {
        HStack {
          Text("AI Draft").scaledFont(size: 10, weight: .semibold)
            .foregroundColor(OmiColors.purplePrimary.opacity(0.8)).textCase(.uppercase)
          Spacer()
          if msg.status == .pending {
            Button(action: {
              if isEditing { editingMessageId = nil }
              else { editText = msg.draftReply; editingMessageId = msg.id }
            }) {
              Text(isEditing ? "Done" : "Edit")
                .scaledFont(size: 11, weight: .medium).foregroundColor(OmiColors.purplePrimary)
            }
            .buttonStyle(.plain)
          }
        }

        if isEditing {
          TextEditor(text: $editText)
            .scaledFont(size: 13).foregroundColor(OmiColors.textPrimary)
            .frame(minHeight: 60, maxHeight: 120)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(
              RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundTertiary)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(OmiColors.purplePrimary.opacity(0.4), lineWidth: 1))
            )
            .scrollContentBackground(.hidden)
        } else {
          Text(msg.draftReply).scaledFont(size: 13).foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(
              RoundedRectangle(cornerRadius: 10).fill(OmiColors.purplePrimary.opacity(0.12))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(OmiColors.purplePrimary.opacity(0.2), lineWidth: 1))
            )
        }
      }

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
              .scaledFont(size: 13, weight: .semibold).foregroundColor(.white)
              .padding(.horizontal, 16).padding(.vertical, 8)
              .background(RoundedRectangle(cornerRadius: 9).fill(OmiColors.purplePrimary))
          }
          .buttonStyle(.plain)

          Button(action: { Task { await service.dismissMessage(msg.id) } }) {
            Text("Dismiss").scaledFont(size: 13).foregroundColor(OmiColors.textSecondary)
              .padding(.horizontal, 16).padding(.vertical, 8)
              .background(RoundedRectangle(cornerRadius: 9).fill(OmiColors.backgroundTertiary))
          }
          .buttonStyle(.plain)
        }
      }
    }
    .padding(16)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(OmiColors.backgroundSecondary.opacity(0.7))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
          .stroke(OmiColors.border.opacity(0.15), lineWidth: 1))
    )
  }

  // MARK: - Helpers

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
      Circle().fill(color.opacity(0.18)).frame(width: 32, height: 32)
      Image(systemName: icon).scaledFont(size: 13).foregroundColor(color)
    }
  }

  @ViewBuilder
  private func statusBadge(_ status: CloneMessage.CloneMessageStatus) -> some View {
    switch status {
    case .pending:
      Text("Pending").scaledFont(size: 10, weight: .semibold).foregroundColor(OmiColors.warning)
        .padding(.horizontal, 8).padding(.vertical, 3)
        .background(RoundedRectangle(cornerRadius: 5).fill(OmiColors.warning.opacity(0.15)))
    case .sent:
      Label("Sent", systemImage: "checkmark").scaledFont(size: 10, weight: .semibold).foregroundColor(OmiColors.success)
        .padding(.horizontal, 8).padding(.vertical, 3)
        .background(RoundedRectangle(cornerRadius: 5).fill(OmiColors.success.opacity(0.15)))
    case .dismissed:
      Text("Dismissed").scaledFont(size: 10, weight: .semibold).foregroundColor(OmiColors.textQuaternary)
        .padding(.horizontal, 8).padding(.vertical, 3)
        .background(RoundedRectangle(cornerRadius: 5).fill(OmiColors.backgroundTertiary))
    case .approved:
      Label("Approved", systemImage: "checkmark").scaledFont(size: 10, weight: .semibold)
        .foregroundColor(OmiColors.purplePrimary)
        .padding(.horizontal, 8).padding(.vertical, 3)
        .background(RoundedRectangle(cornerRadius: 5).fill(OmiColors.purplePrimary.opacity(0.15)))
    }
  }

  private func platformSetupCard(
    icon: String, color: Color, name: String, description: String,
    isConnected: Bool, isComingSoon: Bool = false, action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      VStack(spacing: 12) {
        ZStack {
          Circle().fill(color.opacity(isComingSoon ? 0.1 : 0.18)).frame(width: 48, height: 48)
          Image(systemName: icon).scaledFont(size: 20)
            .foregroundColor(isComingSoon ? OmiColors.textQuaternary : color)
        }
        VStack(spacing: 4) {
          Text(name).scaledFont(size: 14, weight: .semibold)
            .foregroundColor(isComingSoon ? OmiColors.textQuaternary : OmiColors.textPrimary)
          Text(description).scaledFont(size: 11).foregroundColor(OmiColors.textTertiary)
            .multilineTextAlignment(.center)
        }
        if isComingSoon {
          Text("Soon").scaledFont(size: 10, weight: .semibold).foregroundColor(OmiColors.textQuaternary)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(RoundedRectangle(cornerRadius: 5).fill(OmiColors.backgroundTertiary))
        } else if isConnected {
          Label("Connected", systemImage: "checkmark.circle.fill")
            .scaledFont(size: 11, weight: .semibold).foregroundColor(OmiColors.success)
        } else {
          Text("Set Up").scaledFont(size: 11, weight: .semibold).foregroundColor(OmiColors.purplePrimary)
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(RoundedRectangle(cornerRadius: 6).stroke(OmiColors.purplePrimary.opacity(0.5), lineWidth: 1))
        }
      }
      .padding(20).frame(width: 160)
      .background(
        RoundedRectangle(cornerRadius: 14).fill(OmiColors.backgroundSecondary.opacity(0.7))
          .overlay(RoundedRectangle(cornerRadius: 14)
            .stroke(isConnected ? OmiColors.success.opacity(0.3) : OmiColors.border.opacity(0.2), lineWidth: 1))
      )
    }
    .buttonStyle(.plain)
    .disabled(isComingSoon)
  }

  private static let shortDateFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateStyle = .short
    f.timeStyle = .none
    return f
  }()

  private func relativeTime(_ date: Date) -> String {
    let seconds = Int(-date.timeIntervalSinceNow)
    if seconds < 60 { return "just now" }
    if seconds < 3600 { return "\(seconds / 60)m ago" }
    if seconds < 86400 { return "\(seconds / 3600)h ago" }
    return AIClonePage.shortDateFormatter.string(from: date)
  }

  // MARK: - WhatsApp Setup Sheet

  private var whatsAppSetupSheet: some View {
    WhatsAppSetupSheet(isPresented: $showWhatsAppSetup)
      .environmentObject(service)
  }

  // MARK: - Telegram Setup Sheet (Phone + OTP)

  private var telegramSetupSheet: some View {
    TelegramSetupSheet(isPresented: $showTelegramSetup)
      .environmentObject(service)
  }
}

// MARK: - WhatsApp Setup Sheet

private struct WhatsAppSetupSheet: View {
  @Binding var isPresented: Bool
  @EnvironmentObject var service: AICloneService
  @State private var botPhoneDraft = ""

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack {
        Text(service.whatsAppConfigured ? "WhatsApp Bot" : "Set Up WhatsApp Bot")
          .scaledFont(size: 18, weight: .bold).foregroundColor(OmiColors.textPrimary)
        Spacer()
        Button(action: { isPresented = false }) {
          Image(systemName: "xmark.circle.fill").scaledFont(size: 20).foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
      .padding(24)

      Divider().opacity(0.2)

      if service.whatsAppConfigured {
        // Connected state
        VStack(spacing: 20) {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: 48).foregroundColor(OmiColors.success)
          Text(service.whatsAppBotPhone)
            .scaledFont(size: 15, weight: .semibold).foregroundColor(OmiColors.textPrimary)
          Text("Omi is replying to WhatsApp messages sent to this bot number.")
            .scaledFont(size: 13).foregroundColor(OmiColors.textSecondary).multilineTextAlignment(.center)
          Button(action: { service.configureWhatsApp(botPhone: ""); isPresented = false }) {
            Text("Disconnect").scaledFont(size: 13).foregroundColor(OmiColors.warning)
          }
          .buttonStyle(.plain)
        }
        .padding(28)
      } else {
        VStack(alignment: .leading, spacing: 20) {
          // How it works
          VStack(alignment: .leading, spacing: 6) {
            Label("How it works", systemImage: "info.circle")
              .scaledFont(size: 12, weight: .semibold).foregroundColor(OmiColors.textTertiary)
            Text("Omi uses a WhatsApp Cloud API bot number. Your contacts message the bot, and Omi replies using your memories.\n\nGet your phone number ID and access token at developers.facebook.com → WhatsApp.")
              .scaledFont(size: 12).foregroundColor(OmiColors.textSecondary)
          }
          .padding(14)
          .background(RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundTertiary.opacity(0.5)))

          VStack(alignment: .leading, spacing: 8) {
            Text("Bot phone number (E.164 format)")
              .scaledFont(size: 13, weight: .semibold).foregroundColor(OmiColors.textSecondary)
            TextField("+1 555 000 0000", text: $botPhoneDraft)
              .textFieldStyle(.plain).scaledFont(size: 14).foregroundColor(OmiColors.textPrimary)
              .padding(12)
              .background(
                RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundTertiary)
                  .overlay(RoundedRectangle(cornerRadius: 10).stroke(OmiColors.border.opacity(0.3), lineWidth: 1))
              )
            Text("Set WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN in your backend .env")
              .scaledFont(size: 11).foregroundColor(OmiColors.textQuaternary)
          }

          HStack {
            Spacer()
            Button("Cancel") { isPresented = false }
              .buttonStyle(.plain).foregroundColor(OmiColors.textSecondary)
            Button(action: { service.configureWhatsApp(botPhone: botPhoneDraft); isPresented = false }) {
              Text("Save")
                .scaledFont(size: 13, weight: .semibold).foregroundColor(.white)
                .padding(.horizontal, 20).padding(.vertical, 9)
                .background(
                  RoundedRectangle(cornerRadius: 10)
                    .fill(botPhoneDraft.count > 5 ? OmiColors.purplePrimary : OmiColors.textQuaternary.opacity(0.3))
                )
            }
            .buttonStyle(.plain)
            .disabled(botPhoneDraft.count < 6)
          }
        }
        .padding(24)
      }
    }
    .frame(width: 420)
    .background(OmiColors.backgroundPrimary)
    .preferredColorScheme(.dark)
    .onAppear { botPhoneDraft = service.whatsAppBotPhone }
  }
}

// MARK: - Telegram Setup Sheet (separate view for state management)

private struct TelegramSetupSheet: View {
  @Binding var isPresented: Bool
  @EnvironmentObject var service: AICloneService

  // Auth state machine: .phone → .code → .done
  @State private var step: Step = .phone
  @State private var phoneDraft = ""
  @State private var codeDraft = ""

  enum Step { case phone, code, done }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      sheetHeader
      Divider().opacity(0.2)

      if service.telegramConnected && step != .code {
        connectedView
      } else {
        switch step {
        case .phone: phoneStep
        case .code: codeStep
        case .done: connectedView
        }
      }
    }
    .frame(width: 420)
    .background(OmiColors.backgroundPrimary)
    .preferredColorScheme(.dark)
    .onAppear {
      if service.telegramConnected { step = .done }
    }
  }

  private var sheetHeader: some View {
    HStack {
      Text(service.telegramConnected ? "Telegram Connected" : "Connect Telegram")
        .scaledFont(size: 18, weight: .bold).foregroundColor(OmiColors.textPrimary)
      Spacer()
      Button(action: { isPresented = false }) {
        Image(systemName: "xmark.circle.fill").scaledFont(size: 20).foregroundColor(OmiColors.textTertiary)
      }
      .buttonStyle(.plain)
    }
    .padding(24)
  }

  // Connected state
  private var connectedView: some View {
    VStack(spacing: 20) {
      Image(systemName: "checkmark.circle.fill")
        .scaledFont(size: 48).foregroundColor(OmiColors.success)

      VStack(spacing: 4) {
        Text(service.telegramDisplayName)
          .scaledFont(size: 16, weight: .semibold).foregroundColor(OmiColors.textPrimary)
        Text(service.telegramPhone)
          .scaledFont(size: 13).foregroundColor(OmiColors.textTertiary)
      }

      Text("Omi is monitoring your personal Telegram messages and will draft replies in your voice.")
        .scaledFont(size: 13).foregroundColor(OmiColors.textSecondary)
        .multilineTextAlignment(.center)

      Button(action: {
        Task {
          await service.telegramDisconnect()
          step = .phone
        }
      }) {
        Text("Disconnect")
          .scaledFont(size: 13).foregroundColor(OmiColors.warning)
      }
      .buttonStyle(.plain)
    }
    .padding(28)
  }

  // Step 1: Enter phone number
  private var phoneStep: some View {
    VStack(alignment: .leading, spacing: 20) {
      VStack(alignment: .leading, spacing: 6) {
        Label("How it works", systemImage: "info.circle")
          .scaledFont(size: 12, weight: .semibold).foregroundColor(OmiColors.textTertiary)
        Text("Omi connects to your actual Telegram account (not a bot) using Telegram's official MTProto protocol — the same one the official app uses. Your session is encrypted and stored securely.")
          .scaledFont(size: 12).foregroundColor(OmiColors.textSecondary)
      }
      .padding(14)
      .background(RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundTertiary.opacity(0.5)))

      VStack(alignment: .leading, spacing: 8) {
        Text("Your phone number")
          .scaledFont(size: 13, weight: .semibold).foregroundColor(OmiColors.textSecondary)
        TextField("+1 555 000 0000", text: $phoneDraft)
          .textFieldStyle(.plain)
          .scaledFont(size: 14)
          .foregroundColor(OmiColors.textPrimary)
          .padding(12)
          .background(
            RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundTertiary)
              .overlay(RoundedRectangle(cornerRadius: 10).stroke(OmiColors.border.opacity(0.3), lineWidth: 1))
          )
        Text("Include country code, e.g. +1 for US")
          .scaledFont(size: 11).foregroundColor(OmiColors.textQuaternary)
      }

      if !service.telegramError.isEmpty {
        Text(service.telegramError).scaledFont(size: 12).foregroundColor(OmiColors.warning)
      }

      HStack(spacing: 12) {
        Spacer()
        Button("Cancel") { isPresented = false }
          .buttonStyle(.plain).foregroundColor(OmiColors.textSecondary)

        Button(action: {
          Task {
            await service.telegramSendCode(phone: phoneDraft)
            if service.telegramError.isEmpty { step = .code }
          }
        }) {
          Group {
            if service.telegramSendingCode {
              ProgressView().scaleEffect(0.75)
            } else {
              Text("Send Code")
            }
          }
          .scaledFont(size: 13, weight: .semibold).foregroundColor(.white)
          .padding(.horizontal, 20).padding(.vertical, 9)
          .background(
            RoundedRectangle(cornerRadius: 10)
              .fill(phoneDraft.count > 5 ? OmiColors.purplePrimary : OmiColors.textQuaternary.opacity(0.3))
          )
        }
        .buttonStyle(.plain)
        .disabled(phoneDraft.count < 6 || service.telegramSendingCode)
      }
    }
    .padding(24)
  }

  // Step 2: Enter OTP code
  private var codeStep: some View {
    VStack(alignment: .leading, spacing: 20) {
      VStack(alignment: .leading, spacing: 6) {
        Label("Check Telegram", systemImage: "bell.badge.fill")
          .scaledFont(size: 12, weight: .semibold).foregroundColor(OmiColors.purplePrimary)
        Text("A code was sent to your Telegram account on your phone. Open Telegram and enter the 5-digit code you received.")
          .scaledFont(size: 12).foregroundColor(OmiColors.textSecondary)
      }
      .padding(14)
      .background(RoundedRectangle(cornerRadius: 10).fill(OmiColors.purplePrimary.opacity(0.08)))

      VStack(alignment: .leading, spacing: 8) {
        Text("Verification code")
          .scaledFont(size: 13, weight: .semibold).foregroundColor(OmiColors.textSecondary)
        TextField("12345", text: $codeDraft)
          .textFieldStyle(.plain)
          .scaledFont(size: 22, weight: .semibold)
          .multilineTextAlignment(.center)
          .foregroundColor(OmiColors.textPrimary)
          .padding(14)
          .background(
            RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundTertiary)
              .overlay(RoundedRectangle(cornerRadius: 10).stroke(OmiColors.purplePrimary.opacity(0.4), lineWidth: 1))
          )
      }

      if !service.telegramError.isEmpty {
        Text(service.telegramError).scaledFont(size: 12).foregroundColor(OmiColors.warning)
      }

      HStack(spacing: 12) {
        Button("Back") { step = .phone; service.telegramError = "" }
          .buttonStyle(.plain).foregroundColor(OmiColors.textSecondary)

        Spacer()

        Button(action: {
          Task {
            await service.telegramVerify(phone: phoneDraft, code: codeDraft)
            if service.telegramError.isEmpty { step = .done }
          }
        }) {
          Group {
            if service.telegramVerifying {
              ProgressView().scaleEffect(0.75)
            } else {
              Text("Verify")
            }
          }
          .scaledFont(size: 13, weight: .semibold).foregroundColor(.white)
          .padding(.horizontal, 20).padding(.vertical, 9)
          .background(
            RoundedRectangle(cornerRadius: 10)
              .fill(codeDraft.count >= 4 ? OmiColors.purplePrimary : OmiColors.textQuaternary.opacity(0.3))
          )
        }
        .buttonStyle(.plain)
        .disabled(codeDraft.count < 4 || service.telegramVerifying)
      }
    }
    .padding(24)
  }
}
