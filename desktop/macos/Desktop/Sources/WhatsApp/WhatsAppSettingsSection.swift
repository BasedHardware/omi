import SwiftUI

struct WhatsAppSettingsSection: View {
  @ObservedObject private var state = WhatsAppState.shared
  @Binding var highlightedSettingId: String?

  @State private var showConnectSheet = false
  @State private var isDisconnecting = false
  @State private var isCheckingHealth = false
  @State private var healthSummary: String?

  var body: some View {
    VStack(spacing: 20) {
      connectionCard
      detailsCard
    }
    .sheet(isPresented: $showConnectSheet) {
      WhatsAppConnectView(onDismiss: { showConnectSheet = false })
    }
  }

  private var connectionCard: some View {
    card(settingId: "whatsapp.connection") {
      VStack(alignment: .leading, spacing: 16) {
        HStack(spacing: 16) {
          Circle()
            .fill(statusColor)
            .frame(width: 12, height: 12)
            .shadow(color: statusColor.opacity(0.45), radius: 6)

          Image(systemName: "message.fill")
            .scaledFont(size: 16)
            .foregroundColor(OmiColors.purplePrimary)

          VStack(alignment: .leading, spacing: 4) {
            Text("WhatsApp")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(state.connectionState.statusText)
              .scaledFont(size: 13)
              .foregroundColor(statusTextColor)
          }

          Spacer()

          if state.connectionState.isConnected {
            Button(isDisconnecting ? "Disconnecting..." : "Disconnect") {
              Task { await disconnect() }
            }
            .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
            .disabled(isDisconnecting)
          } else {
            Button("Connect") {
              showConnectSheet = true
            }
            .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
          }
        }

        Text("Scan a QR code to link your WhatsApp account as a linked device. Phase 1 mirrors messages locally; reply drafting and sending come in later phases.")
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textTertiary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  private var detailsCard: some View {
    card(settingId: "whatsapp.status") {
      VStack(alignment: .leading, spacing: 14) {
        HStack {
          VStack(alignment: .leading, spacing: 4) {
            Text("Connection Details")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text("Store: \(state.storePath)")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(2)
              .truncationMode(.middle)
          }

          Spacer()

          Button(isCheckingHealth ? "Checking..." : "Check Health") {
            Task { await checkHealth() }
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
          .disabled(isCheckingHealth)
        }

        if let lastEventSummary = state.lastEventSummary {
          divider
          detailRow(title: "Last event", value: lastEventSummary)
        }

        if let healthSummary {
          divider
          detailRow(title: "Health", value: healthSummary)
        }
      }
    }
  }

  private var statusColor: Color {
    switch state.connectionState {
    case .connected:
      return OmiColors.success
    case .degraded, .needsReauth:
      return OmiColors.warning
    case .pairing, .pairingTerminal, .connecting:
      return OmiColors.purplePrimary
    case .disconnected:
      return OmiColors.textTertiary.opacity(0.35)
    }
  }

  private var statusTextColor: Color {
    switch state.connectionState {
    case .degraded, .needsReauth:
      return OmiColors.warning
    default:
      return OmiColors.textTertiary
    }
  }

  private var divider: some View {
    Rectangle()
      .fill(OmiColors.backgroundQuaternary)
      .frame(height: 1)
  }

  private func detailRow(title: String, value: String) -> some View {
    HStack(alignment: .top, spacing: 12) {
      Text(title)
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
        .frame(width: 84, alignment: .leading)

      Text(value)
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)

      Spacer(minLength: 0)
    }
  }

  private func card<Content: View>(
    settingId: String,
    @ViewBuilder content: () -> Content
  ) -> some View {
    content()
      .padding(20)
      .background(
        RoundedRectangle(cornerRadius: 16)
          .fill(OmiColors.backgroundTertiary)
          .overlay(
            RoundedRectangle(cornerRadius: 16)
              .stroke(OmiColors.border.opacity(0.5), lineWidth: 1)
          )
      )
      .modifier(SettingHighlightModifier(settingId: settingId, highlightedSettingId: $highlightedSettingId))
  }

  private func disconnect() async {
    isDisconnecting = true
    await WhatsAppService.shared.disconnect()
    isDisconnecting = false
  }

  private func checkHealth() async {
    isCheckingHealth = true
    let health = await WhatsAppService.shared.health()
    healthSummary = health.summary
    isCheckingHealth = false
  }
}
