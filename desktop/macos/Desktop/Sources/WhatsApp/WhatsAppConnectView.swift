import AppKit
import CoreImage.CIFilterBuiltins
import SwiftUI
import OmiTheme

struct WhatsAppConnectView: View {
  @ObservedObject private var state = WhatsAppState.shared

  let onDismiss: () -> Void

  private static let qrContext = CIContext()

  var body: some View {
    VStack(alignment: .leading, spacing: 18) {
      header

      VStack(spacing: 16) {
        qrPanel
        statusLine
        retryButton
        disclaimer
      }
      .frame(maxWidth: .infinity)

      Spacer(minLength: 0)
    }
    .padding(24)
    .frame(width: 520, height: 620)
    .background(OmiColors.backgroundPrimary)
    .onAppear {
      Task { await WhatsAppService.shared.pair() }
    }
    .onChange(of: state.connectionState) { _, newValue in
      if newValue == .connected {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
          onDismiss()
        }
      }
    }
  }

  private var header: some View {
    HStack(alignment: .top, spacing: 14) {
      ConnectorBrandIcon(brand: .whatsapp, size: 56, cornerRadius: 16)

      VStack(alignment: .leading, spacing: 6) {
        Text("Link WhatsApp")
          .scaledFont(size: 20, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Text("Open WhatsApp on your phone, go to Settings -> Linked Devices -> Link a Device, then scan this code.")
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer()

      DismissButton(action: onDismiss)
    }
  }

  @ViewBuilder
  private var qrPanel: some View {
    ZStack {
      RoundedRectangle(cornerRadius: 24, style: .continuous)
        .fill(Color.white)
        .frame(width: 280, height: 280)

      switch state.connectionState {
      case .pairing(let qr):
        if let image = qrImage(from: qr) {
          Image(nsImage: image)
            .interpolation(.none)
            .resizable()
            .aspectRatio(contentMode: .fit)
            .frame(width: 240, height: 240)
        } else {
          fallbackPanel("Could not render QR")
        }
      case .pairingTerminal(let qrText):
        terminalQRView(qrText)
      case .connected:
        VStack(spacing: 12) {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: 52)
            .foregroundColor(OmiColors.success)
          Text("Connected")
            .scaledFont(size: 16, weight: .semibold)
            .foregroundColor(.black)
        }
      case .degraded(let reason):
        fallbackPanel(reason)
      case .downloading:
        VStack(spacing: 12) {
          ProgressView()
            .controlSize(.regular)
          Text("Downloading WhatsApp helper...")
            .scaledFont(size: 13)
            .foregroundColor(.black.opacity(0.65))
        }
      default:
        VStack(spacing: 12) {
          ProgressView()
            .controlSize(.regular)
          Text("Starting WhatsApp link...")
            .scaledFont(size: 13)
            .foregroundColor(.black.opacity(0.65))
        }
      }
    }
  }

  private var statusLine: some View {
    HStack(spacing: 8) {
      Circle()
        .fill(statusColor)
        .frame(width: 8, height: 8)
      Text(state.connectionState.statusText)
        .scaledFont(size: 13, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
    }
    .frame(maxWidth: .infinity)
  }

  @ViewBuilder
  private var retryButton: some View {
    if case .degraded = state.connectionState {
      Button("Try again") {
        Task { await WhatsAppService.shared.pair() }
      }
      .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
    }
  }

  private var disclaimer: some View {
    Text("WhatsApp linking uses a third-party WhatsApp Web-compatible tool. Omi is not affiliated with WhatsApp; use responsibly and disconnect anytime.")
      .scaledFont(size: 12)
      .foregroundColor(OmiColors.textTertiary)
      .multilineTextAlignment(.center)
      .fixedSize(horizontal: false, vertical: true)
      .frame(maxWidth: 360)
  }

  private var statusColor: Color {
    switch state.connectionState {
    case .connected:
      return OmiColors.success
    case .degraded, .needsReauth:
      return OmiColors.warning
    case .pairing, .pairingTerminal, .connecting, .downloading:
      return OmiColors.purplePrimary
    case .disconnected:
      return OmiColors.textTertiary.opacity(0.5)
    }
  }

  private func fallbackPanel(_ message: String) -> some View {
    VStack(spacing: 10) {
      Image(systemName: "exclamationmark.triangle")
        .scaledFont(size: 36)
        .foregroundColor(OmiColors.warning)
      Text(message)
        .scaledFont(size: 13, weight: .medium)
        .foregroundColor(.black.opacity(0.7))
        .multilineTextAlignment(.center)
        .padding(.horizontal, 20)
    }
  }

  private func terminalQRView(_ qrText: String) -> some View {
    Text(qrText)
      .font(.system(size: 3.8, weight: .regular, design: .monospaced))
      .lineSpacing(-1)
      .foregroundColor(.black)
      .multilineTextAlignment(.center)
      .fixedSize(horizontal: true, vertical: true)
      .padding(8)
      .accessibilityLabel("WhatsApp QR code")
  }

  private func qrImage(from string: String) -> NSImage? {
    let filter = CIFilter.qrCodeGenerator()
    filter.message = Data(string.utf8)
    guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 10, y: 10)),
      let cgImage = Self.qrContext.createCGImage(output, from: output.extent)
    else {
      return nil
    }
    return NSImage(cgImage: cgImage, size: NSSize(width: 240, height: 240))
  }
}
