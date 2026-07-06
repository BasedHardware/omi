import SwiftUI

/// Settings card for connecting Hermes to Nous Portal. Hermes only supports
/// interactive device-code OAuth (no API keys), so the card drives
/// `HermesConnectService`: it opens the verification page in the browser and
/// waits for the CLI to confirm approval.
struct HermesConnectionCardContent: View {
  @ObservedObject private var service = HermesConnectService.shared
  @State private var hermesInstalled = false

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack {
        Image(systemName: "link")
          .scaledFont(size: 16)
          .foregroundColor(OmiColors.textTertiary)

        Text("Hermes")
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        trailingControl
      }

      statusDetail
    }
    .onAppear {
      hermesInstalled = LocalAgentProviderDetector.executablePath(for: .hermes) != nil
      service.refreshConnectionState()
    }
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("settings-hermes-connection")
  }

  @ViewBuilder
  private var trailingControl: some View {
    switch service.phase {
    case .connected:
      HStack(spacing: 6) {
        Image(systemName: "checkmark.circle.fill")
          .foregroundColor(.green)
          .scaledFont(size: 12)
        Text("Connected")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textSecondary)
      }
    case .starting, .waitingForApproval:
      HStack(spacing: 8) {
        ProgressView()
          .controlSize(.small)
        Button("Cancel") {
          service.cancel()
        }
        .buttonStyle(.bordered)
        .controlSize(.small)
      }
    case .idle, .failed:
      Button(connectButtonTitle) {
        service.connect()
      }
      .buttonStyle(.bordered)
      .controlSize(.small)
      .disabled(!hermesInstalled)
      .accessibilityIdentifier("settings-hermes-connect")
    }
  }

  private var connectButtonTitle: String {
    if case .failed = service.phase { return "Retry sign-in" }
    return "Connect Hermes"
  }

  @ViewBuilder
  private var statusDetail: some View {
    switch service.phase {
    case .idle:
      if hermesInstalled {
        Text("Sign in to Nous to run tasks with Hermes. Omi opens the sign-in page in your browser and waits for approval — no API key needed (Hermes doesn't use them).")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
      } else {
        Text("Hermes isn't installed on this Mac. Ask Omi to \"use Hermes\" to get the installer, then connect it here.")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
      }
    case .starting:
      Text("Starting sign-in…")
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
    case .waitingForApproval(_, let userCode):
      VStack(alignment: .leading, spacing: 8) {
        Text("Waiting for approval in your browser… Approve the sign-in on the Nous page that just opened.")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
        if let userCode, !userCode.isEmpty {
          HStack(spacing: 8) {
            Text("If the page asks for a code:")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
            Text(userCode)
              .font(.system(size: 16, weight: .bold, design: .monospaced))
              .foregroundColor(OmiColors.textPrimary)
              .textSelection(.enabled)
          }
        }
      }
    case .connected:
      Text("Hermes is signed in to Nous. Ask Omi to \"use Hermes\" for any task.")
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
    case .failed(let message):
      Text(message)
        .scaledFont(size: 12)
        .foregroundColor(.red)
        .textSelection(.enabled)
    }
  }
}
