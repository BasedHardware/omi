import OmiTheme
import SwiftUI

// MARK: - AI Clone settings UI
//
// Rendered as the "AI Clone" section inside Settings (AICloneContent), and
// also wrapped as a standalone page (AIClonePage) for automation reachability.
// Styling mirrors the other settings sections: settings-style cards
// (backgroundTertiary card + hairline stroke), OmiType scale, OmiSpacing, and
// OmiToggleStyle.

/// Standalone wrapper kept for automation/e2e reachability. The feature's
/// primary home is the AI Clone section in Settings.
struct AIClonePage: View {
  var body: some View {
    ScrollView {
      AICloneContent()
        .padding(OmiSpacing.xl)
        .frame(maxWidth: 760, alignment: .leading)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    .background(OmiColors.backgroundPrimary)
  }
}

struct AICloneContent: View {
  @ObservedObject private var service = AICloneService.shared
  @State private var tokenInput: String = ""
  @State private var editedApprovalText: [UUID: String] = [:]

  var body: some View {
    VStack(spacing: OmiSpacing.xl) {
      masterCard
      connectionCard
      if service.connectionState.isConnected {
        if !service.pendingApprovals.isEmpty {
          approvalsCard
        }
        chatsCard
        activityCard
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .task {
      if service.hasAccessToken, !service.connectionState.isConnected {
        await service.connect()
      }
    }
  }

  // MARK: Card chrome (mirrors SettingsContentView.settingsCard)

  private func card<Content: View>(@ViewBuilder content: () -> Content) -> some View {
    content()
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(OmiSpacing.xl)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(OmiColors.backgroundTertiary.opacity(0.5))
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .stroke(OmiColors.backgroundQuaternary.opacity(0.3), lineWidth: 1)
          )
      )
  }

  private func cardTitle(_ text: String) -> some View {
    Text(text)
      .scaledFont(size: OmiType.subheading, weight: .semibold)
      .foregroundColor(OmiColors.textPrimary)
  }

  private func cardSubtitle(_ text: String) -> some View {
    Text(text)
      .scaledFont(size: OmiType.body)
      .foregroundColor(OmiColors.textSecondary)
      .fixedSize(horizontal: false, vertical: true)
  }

  // MARK: Master switch

  private var masterCard: some View {
    card {
      HStack(spacing: OmiSpacing.lg) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          cardTitle("Reply on my behalf")
          cardSubtitle(
            "Let Omi reply to people in WhatsApp, Telegram, iMessage and more, using your memories. Connect Beeper Desktop below, then choose how each chat is handled.")
        }
        Spacer()
        Toggle("", isOn: Binding(get: { service.configuration.enabled }, set: { service.setEnabled($0) }))
          .toggleStyle(OmiToggleStyle())
          .labelsHidden()
      }
    }
  }

  // MARK: Connection

  private var connectionCard: some View {
    card {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        HStack(spacing: OmiSpacing.lg) {
          cardTitle("Beeper Desktop")
          Spacer()
          connectionBadge
        }
        switch service.connectionState {
        case .connected(let accounts):
          connectedNetworks(accounts)
          HStack(spacing: OmiSpacing.md) {
            Button("Refresh") { Task { await service.connect() } }
              .buttonStyle(OmiButtonStyle(.secondary))
            Button("Disconnect") { service.disconnectAndForgetToken() }
              .buttonStyle(OmiButtonStyle(.secondary))
          }
        case .connecting:
          ProgressView().controlSize(.small)
        case .disconnected, .failed:
          tokenEntry
        }
        if case .failed(let message) = service.connectionState {
          Text(message)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.warning)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
    }
  }

  private var connectionBadge: some View {
    Group {
      switch service.connectionState {
      case .connected:
        Label("Connected", systemImage: "checkmark.circle.fill").foregroundColor(.green)
      case .connecting:
        Label("Connecting", systemImage: "arrow.triangle.2.circlepath").foregroundColor(OmiColors.textSecondary)
      case .failed:
        Label("Not connected", systemImage: "exclamationmark.triangle.fill").foregroundColor(OmiColors.warning)
      case .disconnected:
        Label("Not connected", systemImage: "circle").foregroundColor(OmiColors.textTertiary)
      }
    }
    .scaledFont(size: OmiType.caption, weight: .medium)
  }

  private func connectedNetworks(_ accounts: [BeeperAccount]) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      ForEach(accounts) { account in
        Text(account.displayNetwork)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.chipRadius)
              .fill(OmiColors.backgroundQuaternary.opacity(0.4)))
          .foregroundColor(OmiColors.textSecondary)
      }
    }
  }

  private var tokenEntry: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        setupStep("1.", "Install and open Beeper Desktop from beeper.com and sign in to your chat networks.")
        setupStep("2.", "In Beeper, open Settings, then Developer, enable the Desktop API and create an access token.")
        setupStep("3.", "Paste the token below.")
      }
      HStack(spacing: OmiSpacing.sm) {
        SecureField("Beeper access token", text: $tokenInput)
          .textFieldStyle(.roundedBorder)
          .frame(maxWidth: 340)
        Button("Connect") {
          service.saveAccessToken(tokenInput)
          tokenInput = ""
          Task { await service.connect() }
        }
        .buttonStyle(OmiButtonStyle(.primary))
        .disabled(tokenInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
      }
    }
  }

  private func setupStep(_ number: String, _ text: String) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.sm) {
      Text(number)
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(OmiColors.textTertiary)
      Text(text)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  // MARK: Approvals

  private var approvalsCard: some View {
    card {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        cardTitle("Waiting for your approval")
        ForEach(service.pendingApprovals) { approval in
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("\(approval.chatTitle) · \(approval.network)")
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(OmiColors.textSecondary)
            Text("They said: \(approval.inboundPreview)")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
            TextEditor(text: Binding(
              get: { editedApprovalText[approval.id] ?? approval.replyText },
              set: { editedApprovalText[approval.id] = $0 }))
              .scaledFont(size: OmiType.body)
              .frame(minHeight: 48, maxHeight: 96)
              .scrollContentBackground(.hidden)
              .padding(OmiSpacing.sm)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                  .fill(OmiColors.backgroundQuaternary.opacity(0.35)))
            HStack(spacing: OmiSpacing.sm) {
              Button("Send") {
                let text = editedApprovalText[approval.id]
                editedApprovalText.removeValue(forKey: approval.id)
                Task { await service.approve(approval, editedText: text) }
              }
              .buttonStyle(OmiButtonStyle(.primary))
              .keyboardShortcut(.defaultAction)
              Button("Skip") {
                editedApprovalText.removeValue(forKey: approval.id)
                service.skip(approval)
              }
              .buttonStyle(OmiButtonStyle(.secondary))
            }
          }
          .padding(OmiSpacing.md)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(OmiColors.backgroundQuaternary.opacity(0.25)))
        }
      }
    }
  }

  // MARK: Chats

  private var chatsCard: some View {
    card {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        cardTitle("Chats")
        cardSubtitle(
          "Draft puts the reply in Beeper's compose box. Ask me sends only after you approve. Auto sends by itself when confident, and unlocks once a chat's benchmark score reaches \(service.configuration.autoModeMinimumBenchmarkScore).")
        ForEach(service.chats) { chat in
          chatRow(chat)
          if chat.id != service.chats.last?.id {
            Divider().overlay(OmiColors.backgroundQuaternary.opacity(0.3))
          }
        }
      }
    }
  }

  private func chatRow(_ chat: BeeperChat) -> some View {
    HStack(spacing: OmiSpacing.md) {
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(chat.title ?? "Untitled chat")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)
        HStack(spacing: OmiSpacing.sm) {
          Text(chat.network ?? "Beeper")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
          if let result = service.configuration.benchmarkResults[chat.id] {
            Text("matches you \(result.matchScore)%")
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(
                result.matchScore >= service.configuration.autoModeMinimumBenchmarkScore
                  ? .green : OmiColors.warning)
          }
        }
      }
      Spacer()
      if service.benchmarkRunningChatIDs.contains(chat.id) {
        ProgressView().controlSize(.small)
      } else {
        Button("Benchmark") { Task { await service.runBenchmark(for: chat) } }
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
      }
      Picker("", selection: Binding(
        get: { service.configuration.mode(for: chat.id) },
        set: { service.setMode($0, for: chat) })) {
        ForEach(AICloneChatMode.allCases, id: \.self) { mode in
          if mode != .auto || service.configuration.canEnableAuto(for: chat.id) {
            Text(mode.displayName).tag(mode)
          }
        }
      }
      .pickerStyle(.segmented)
      .labelsHidden()
      .frame(width: 260)
    }
    .padding(.vertical, OmiSpacing.xxs)
  }

  // MARK: Activity

  private var activityCard: some View {
    card {
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        cardTitle("Activity")
        if service.configuration.activityLog.isEmpty {
          cardSubtitle("Nothing yet. When the clone drafts, sends, or declines a reply, it shows up here.")
        }
        ForEach(service.configuration.activityLog.prefix(30)) { entry in
          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            HStack(spacing: OmiSpacing.sm) {
              Text(entry.chatTitle)
                .scaledFont(size: OmiType.caption, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)
              Text(entry.network)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
              Spacer()
              outcomeBadge(entry.outcome)
              Text(entry.date, style: .relative)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textQuaternary)
            }
            Text("They said: \(entry.inboundPreview)")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(1)
            if let reply = entry.replyText, !reply.isEmpty {
              Text("Clone: \(reply)")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(2)
            }
          }
          .padding(.vertical, OmiSpacing.xxs)
          if entry.id != service.configuration.activityLog.prefix(30).last?.id {
            Divider().overlay(OmiColors.backgroundQuaternary.opacity(0.3))
          }
        }
      }
    }
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
      .scaledFont(size: OmiType.micro, weight: .semibold)
      .padding(.horizontal, OmiSpacing.xs)
      .padding(.vertical, OmiSpacing.hairline)
      .background(RoundedRectangle(cornerRadius: OmiChrome.chipRadius).fill(color.opacity(0.15)))
      .foregroundColor(color)
  }
}
