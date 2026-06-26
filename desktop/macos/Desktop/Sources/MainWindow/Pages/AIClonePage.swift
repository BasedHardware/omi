import SwiftUI

// MARK: - AI Clone Page

struct AIClonePage: View {
  @StateObject private var service = AICloneService.shared
  @State private var showTelegramSetup = false
  @State private var showWhatsAppSetup = false

  var body: some View {
    VStack(spacing: 0) {
      pageHeader
      Divider().opacity(0.2)

      if !service.isEnabled {
        emptyState
      } else {
        HStack(alignment: .top, spacing: 0) {
          platformPanel.frame(width: 260)
          Divider().opacity(0.2)
          activityLog
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
        Text("Omi reads your messages and auto-replies in your voice,\nbased on your memories and communication style.")
          .scaledFont(size: 14)
          .foregroundColor(OmiColors.textSecondary)
          .multilineTextAlignment(.center)
      }

      HStack(spacing: 12) {
        platformSetupCard(
          icon: "message.fill", color: .green, name: "iMessage",
          description: "Reads & auto-replies\nvia Messages.app",
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
          description: "Your Telegram bot\nauto-replies for you",
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
          statusLabel: service.iMessageConnected ? "Auto-replies via Messages" : "Grant Automation access",
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
          statusLabel: service.telegramConnected
            ? (service.telegramBotUsername.isEmpty ? "Bot connected" : "@\(service.telegramBotUsername)")
            : "Tap to connect bot",
          action: { showTelegramSetup = true }
        )

        platformRow(
          icon: "phone.fill", color: Color(red: 0.15, green: 0.7, blue: 0.3), name: "WhatsApp",
          isConnected: service.whatsAppConfigured,
          statusLabel: service.whatsAppConfigured ? service.whatsAppBotPhone : "Tap to set up bot",
          action: { showWhatsAppSetup = true }
        )

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

  // MARK: - Activity Log

  private var activityLog: some View {
    VStack(spacing: 0) {
      HStack {
        Text("Recent Omi Replies")
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)
        Spacer()
        Image(systemName: "checkmark.circle.fill")
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.success)
        Text("Auto-sending")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.success)
      }
      .padding(.horizontal, 20)
      .padding(.vertical, 14)

      Divider().opacity(0.15)

      VStack(spacing: 16) {
        Spacer()
        Image(systemName: "waveform.path.ecg").scaledFont(size: 40).foregroundColor(OmiColors.textQuaternary)
        Text("Watching for messages…").scaledFont(size: 15).foregroundColor(OmiColors.textTertiary)
        Text("Omi auto-replies to iMessage, Telegram, and WhatsApp on your behalf.\nMessages appear here after sending.")
          .scaledFont(size: 13).foregroundColor(OmiColors.textQuaternary)
          .multilineTextAlignment(.center)
        Spacer()
      }
      .padding(.horizontal, 40)
    }
  }

  // MARK: - Helpers

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

  // MARK: - WhatsApp Setup Sheet

  private var whatsAppSetupSheet: some View {
    WhatsAppSetupSheet(isPresented: $showWhatsAppSetup)
      .environmentObject(service)
  }

  // MARK: - Telegram Setup Sheet (Bot API)

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
        VStack(spacing: 20) {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: 48).foregroundColor(OmiColors.success)
          Text(service.whatsAppBotPhone)
            .scaledFont(size: 15, weight: .semibold).foregroundColor(OmiColors.textPrimary)
          Text("Omi is auto-replying to WhatsApp messages sent to this bot number.")
            .scaledFont(size: 13).foregroundColor(OmiColors.textSecondary).multilineTextAlignment(.center)
          Button(action: { service.configureWhatsApp(botPhone: ""); isPresented = false }) {
            Text("Disconnect").scaledFont(size: 13).foregroundColor(OmiColors.warning)
          }
          .buttonStyle(.plain)
        }
        .padding(28)
      } else {
        VStack(alignment: .leading, spacing: 20) {
          VStack(alignment: .leading, spacing: 6) {
            Label("How it works", systemImage: "info.circle")
              .scaledFont(size: 12, weight: .semibold).foregroundColor(OmiColors.textTertiary)
            Text("Omi uses a WhatsApp Cloud API bot number. Your contacts message the bot, and Omi auto-replies using your memories.\n\nGet your phone number ID and access token at developers.facebook.com → WhatsApp.")
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

// MARK: - Telegram Setup Sheet (Bot API — bot token)

private struct TelegramSetupSheet: View {
  @Binding var isPresented: Bool
  @EnvironmentObject var service: AICloneService
  @State private var tokenDraft = ""

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      sheetHeader
      Divider().opacity(0.2)

      if service.telegramConnected {
        connectedView
      } else {
        setupView
      }
    }
    .frame(width: 420)
    .background(OmiColors.backgroundPrimary)
    .preferredColorScheme(.dark)
  }

  private var sheetHeader: some View {
    HStack {
      Text(service.telegramConnected ? "Telegram Bot Connected" : "Connect Telegram Bot")
        .scaledFont(size: 18, weight: .bold).foregroundColor(OmiColors.textPrimary)
      Spacer()
      Button(action: { isPresented = false }) {
        Image(systemName: "xmark.circle.fill").scaledFont(size: 20).foregroundColor(OmiColors.textTertiary)
      }
      .buttonStyle(.plain)
    }
    .padding(24)
  }

  private var connectedView: some View {
    VStack(spacing: 20) {
      Image(systemName: "checkmark.circle.fill")
        .scaledFont(size: 48).foregroundColor(OmiColors.success)

      VStack(spacing: 4) {
        if !service.telegramBotUsername.isEmpty {
          Text("@\(service.telegramBotUsername)")
            .scaledFont(size: 16, weight: .semibold).foregroundColor(OmiColors.textPrimary)
        }
        Text("Bot connected")
          .scaledFont(size: 13).foregroundColor(OmiColors.textTertiary)
      }

      Text("Friends message your bot and Omi auto-replies in your voice.\nShare your bot link so people can find it.")
        .scaledFont(size: 13).foregroundColor(OmiColors.textSecondary)
        .multilineTextAlignment(.center)

      Button(action: {
        Task {
          await service.telegramDisconnect()
          isPresented = false
        }
      }) {
        Text("Disconnect")
          .scaledFont(size: 13).foregroundColor(OmiColors.warning)
      }
      .buttonStyle(.plain)
    }
    .padding(28)
  }

  private var setupView: some View {
    VStack(alignment: .leading, spacing: 20) {
      VStack(alignment: .leading, spacing: 6) {
        Label("How it works", systemImage: "info.circle")
          .scaledFont(size: 12, weight: .semibold).foregroundColor(OmiColors.textTertiary)
        Text("1. Open Telegram and message @BotFather\n2. Send /newbot and follow the prompts\n3. Copy the bot token and paste it below\n4. Share your new bot link with friends — they message the bot and Omi auto-replies")
          .scaledFont(size: 12).foregroundColor(OmiColors.textSecondary)
      }
      .padding(14)
      .background(RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundTertiary.opacity(0.5)))

      VStack(alignment: .leading, spacing: 8) {
        Text("Bot token from @BotFather")
          .scaledFont(size: 13, weight: .semibold).foregroundColor(OmiColors.textSecondary)
        TextField("1234567890:ABCdef...", text: $tokenDraft)
          .textFieldStyle(.plain).scaledFont(size: 13).foregroundColor(OmiColors.textPrimary)
          .padding(12)
          .background(
            RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundTertiary)
              .overlay(RoundedRectangle(cornerRadius: 10).stroke(OmiColors.border.opacity(0.3), lineWidth: 1))
          )
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
            await service.telegramConnect(botToken: tokenDraft)
            if service.telegramConnected { isPresented = false }
          }
        }) {
          Group {
            if service.telegramConnecting {
              ProgressView().scaleEffect(0.75)
            } else {
              Text("Connect")
            }
          }
          .scaledFont(size: 13, weight: .semibold).foregroundColor(.white)
          .padding(.horizontal, 20).padding(.vertical, 9)
          .background(
            RoundedRectangle(cornerRadius: 10)
              .fill(tokenDraft.count > 20 ? OmiColors.purplePrimary : OmiColors.textQuaternary.opacity(0.3))
          )
        }
        .buttonStyle(.plain)
        .disabled(tokenDraft.count < 20 || service.telegramConnecting)
      }
    }
    .padding(24)
  }
}
