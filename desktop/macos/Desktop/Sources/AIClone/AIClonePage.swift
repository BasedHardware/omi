import OmiTheme
import SwiftUI

// MARK: - AI Clone page
//
// One screen for the whole feature: connect Beeper, pick per-chat trust
// modes, review approval requests, run the self-benchmark, and read the
// activity log of everything the clone did on the user's behalf.

struct AIClonePage: View {
  @ObservedObject private var service = AICloneService.shared
  @State private var tokenInput: String = ""
  @State private var editedApprovalText: [UUID: String] = [:]

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        header
        connectionCard
        if service.connectionState.isConnected {
          if !service.pendingApprovals.isEmpty {
            approvalsCard
          }
          chatsCard
          activityCard
        }
      }
      .padding(24)
      .frame(maxWidth: 760, alignment: .leading)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    .background(OmiColors.backgroundPrimary)
    .task {
      if service.hasAccessToken, !service.connectionState.isConnected {
        await service.connect()
      }
    }
  }

  // MARK: Header

  private var header: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack(spacing: 10) {
        Image(systemName: "person.2.wave.2.fill")
          .font(.system(size: 22, weight: .semibold))
          .foregroundColor(OmiColors.accent)
        Text("AI Clone")
          .font(.system(size: 24, weight: .bold))
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        Toggle("", isOn: Binding(
          get: { service.configuration.enabled },
          set: { service.setEnabled($0) }
        ))
        .toggleStyle(.switch)
        .accessibilityLabel("Enable AI Clone")
      }
      Text("Replies to people on your behalf in WhatsApp, Telegram, iMessage and more — grounded in your Omi memories, through Beeper Desktop.")
        .font(.system(size: 13))
        .foregroundColor(OmiColors.textSecondary)
    }
  }

  // MARK: Connection

  private var connectionCard: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack {
        Text("Beeper Desktop")
          .font(.system(size: 15, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        connectionBadge
      }
      switch service.connectionState {
      case .connected(let accounts):
        connectedNetworks(accounts)
        HStack {
          Button("Refresh") { Task { await service.connect() } }
          Button("Disconnect") { service.disconnectAndForgetToken() }
            .foregroundColor(OmiColors.error)
        }
      case .connecting:
        ProgressView().controlSize(.small)
      case .disconnected, .failed:
        tokenEntry
      }
      if case .failed(let message) = service.connectionState {
        Text(message)
          .font(.system(size: 12))
          .foregroundColor(OmiColors.warning)
      }
    }
    .padding(16)
    .background(OmiColors.backgroundSecondary)
    .cornerRadius(12)
  }

  private var connectionBadge: some View {
    Group {
      switch service.connectionState {
      case .connected:
        Label("Connected", systemImage: "checkmark.circle.fill")
          .foregroundColor(.green)
      case .connecting:
        Label("Connecting…", systemImage: "arrow.triangle.2.circlepath")
          .foregroundColor(OmiColors.textSecondary)
      case .failed:
        Label("Not connected", systemImage: "exclamationmark.triangle.fill")
          .foregroundColor(OmiColors.warning)
      case .disconnected:
        Label("Not connected", systemImage: "circle")
          .foregroundColor(OmiColors.textTertiary)
      }
    }
    .font(.system(size: 12, weight: .medium))
  }

  private func connectedNetworks(_ accounts: [BeeperAccount]) -> some View {
    HStack(spacing: 8) {
      ForEach(accounts) { account in
        Text(account.displayNetwork)
          .font(.system(size: 11, weight: .medium))
          .padding(.horizontal, 8)
          .padding(.vertical, 4)
          .background(OmiColors.backgroundTertiary)
          .cornerRadius(6)
          .foregroundColor(OmiColors.textSecondary)
      }
    }
  }

  private var tokenEntry: some View {
    VStack(alignment: .leading, spacing: 8) {
      Text("1. Install and open Beeper Desktop (beeper.com) and sign in to your chat networks.\n2. In Beeper: Settings → Developer → enable the Desktop API and create an access token.\n3. Paste the token here.")
        .font(.system(size: 12))
        .foregroundColor(OmiColors.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
      HStack(spacing: 8) {
        SecureField("Beeper access token", text: $tokenInput)
          .textFieldStyle(.roundedBorder)
          .frame(maxWidth: 340)
        Button("Connect") {
          service.saveAccessToken(tokenInput)
          tokenInput = ""
          Task { await service.connect() }
        }
        .disabled(tokenInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
      }
    }
  }

  // MARK: Approvals

  private var approvalsCard: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text("Waiting for your approval")
        .font(.system(size: 15, weight: .semibold))
        .foregroundColor(OmiColors.textPrimary)
      ForEach(service.pendingApprovals) { approval in
        VStack(alignment: .leading, spacing: 8) {
          Text("\(approval.chatTitle) · \(approval.network)")
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(OmiColors.textSecondary)
          Text("They said: \(approval.inboundPreview)")
            .font(.system(size: 12))
            .foregroundColor(OmiColors.textTertiary)
          TextEditor(text: Binding(
            get: { editedApprovalText[approval.id] ?? approval.replyText },
            set: { editedApprovalText[approval.id] = $0 }
          ))
          .font(.system(size: 13))
          .frame(minHeight: 48, maxHeight: 96)
          .scrollContentBackground(.hidden)
          .padding(6)
          .background(OmiColors.backgroundTertiary)
          .cornerRadius(8)
          HStack {
            Button("Send") {
              let text = editedApprovalText[approval.id]
              editedApprovalText.removeValue(forKey: approval.id)
              Task { await service.approve(approval, editedText: text) }
            }
            .keyboardShortcut(.defaultAction)
            Button("Skip") {
              editedApprovalText.removeValue(forKey: approval.id)
              service.skip(approval)
            }
          }
        }
        .padding(12)
        .background(OmiColors.backgroundSecondary)
        .cornerRadius(10)
      }
    }
    .padding(16)
    .background(OmiColors.backgroundSecondary.opacity(0.5))
    .cornerRadius(12)
  }

  // MARK: Chats

  private var chatsCard: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Chats")
        .font(.system(size: 15, weight: .semibold))
        .foregroundColor(OmiColors.textPrimary)
      Text("Draft puts the reply in Beeper's compose box. Ask me sends only after you approve. Auto sends by itself when confident — unlocked by a benchmark score of \(service.configuration.autoModeMinimumBenchmarkScore)+.")
        .font(.system(size: 12))
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)
      ForEach(service.chats) { chat in
        chatRow(chat)
      }
    }
    .padding(16)
    .background(OmiColors.backgroundSecondary)
    .cornerRadius(12)
  }

  private func chatRow(_ chat: BeeperChat) -> some View {
    HStack(spacing: 12) {
      VStack(alignment: .leading, spacing: 2) {
        Text(chat.title ?? "Untitled chat")
          .font(.system(size: 13, weight: .medium))
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)
        HStack(spacing: 6) {
          Text(chat.network ?? "Beeper")
            .font(.system(size: 11))
            .foregroundColor(OmiColors.textTertiary)
          if let result = service.configuration.benchmarkResults[chat.id] {
            Text("matches you \(result.matchScore)%")
              .font(.system(size: 11, weight: .medium))
              .foregroundColor(result.matchScore >= service.configuration.autoModeMinimumBenchmarkScore ? .green : OmiColors.warning)
          }
        }
      }
      Spacer()
      if service.benchmarkRunningChatIDs.contains(chat.id) {
        ProgressView().controlSize(.small)
      } else {
        Button("Benchmark") {
          Task { await service.runBenchmark(for: chat) }
        }
        .font(.system(size: 11))
      }
      Picker("", selection: Binding(
        get: { service.configuration.mode(for: chat.id) },
        set: { service.setMode($0, for: chat) }
      )) {
        ForEach(AICloneChatMode.allCases, id: \.self) { mode in
          if mode != .auto || service.configuration.canEnableAuto(for: chat.id) {
            Text(mode.displayName).tag(mode)
          }
        }
      }
      .pickerStyle(.segmented)
      .frame(width: 260)
    }
    .padding(.vertical, 4)
  }

  // MARK: Activity

  private var activityCard: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Activity")
        .font(.system(size: 15, weight: .semibold))
        .foregroundColor(OmiColors.textPrimary)
      if service.configuration.activityLog.isEmpty {
        Text("Nothing yet. When the clone drafts, sends, or declines a reply, it shows up here.")
          .font(.system(size: 12))
          .foregroundColor(OmiColors.textTertiary)
      }
      ForEach(service.configuration.activityLog.prefix(30)) { entry in
        VStack(alignment: .leading, spacing: 3) {
          HStack(spacing: 6) {
            Text(entry.chatTitle)
              .font(.system(size: 12, weight: .semibold))
              .foregroundColor(OmiColors.textPrimary)
            Text(entry.network)
              .font(.system(size: 11))
              .foregroundColor(OmiColors.textTertiary)
            Spacer()
            outcomeBadge(entry.outcome)
            Text(entry.date, style: .relative)
              .font(.system(size: 11))
              .foregroundColor(OmiColors.textQuaternary)
          }
          Text("They said: \(entry.inboundPreview)")
            .font(.system(size: 11))
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
          if let reply = entry.replyText, !reply.isEmpty {
            Text("Clone: \(reply)")
              .font(.system(size: 11))
              .foregroundColor(OmiColors.textSecondary)
              .lineLimit(2)
          }
        }
        .padding(.vertical, 4)
        Divider()
      }
    }
    .padding(16)
    .background(OmiColors.backgroundSecondary)
    .cornerRadius(12)
  }

  private func outcomeBadge(_ outcome: AICloneActionOutcome) -> some View {
    let (label, color): (String, Color)
    switch outcome {
    case .drafted: (label, color) = ("Drafted", OmiColors.textSecondary)
    case .askedApproval: (label, color) = ("Needs approval", OmiColors.warning)
    case .sentAutomatically: (label, color) = ("Sent", .green)
    case .sentAfterApproval: (label, color) = ("Sent (approved)", .green)
    case .stayedSilent: (label, color) = ("Left for you", OmiColors.textTertiary)
    case .declinedInjection: (label, color) = ("Blocked suspicious", OmiColors.error)
    case .failed: (label, color) = ("Failed", OmiColors.error)
    }
    return Text(label)
      .font(.system(size: 10, weight: .semibold))
      .padding(.horizontal, 6)
      .padding(.vertical, 2)
      .background(color.opacity(0.15))
      .foregroundColor(color)
      .cornerRadius(4)
  }
}
