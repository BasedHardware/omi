import OmiTheme
import SwiftUI

struct AccountDataExportView: View {
  @ObservedObject var model: AccountDataExportModel

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      if model.isExporting {
        HStack(spacing: OmiSpacing.sm) {
          ProgressView()
            .controlSize(.small)
          Text(ByteCountFormatter.string(fromByteCount: model.bytesReceived, countStyle: .file))
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
          Button("Cancel") { model.cancelExport() }
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        }
      }
      if let errorMessage = model.errorMessage {
        HStack(spacing: OmiSpacing.sm) {
          Text(errorMessage)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.errorRed)
            .fixedSize(horizontal: false, vertical: true)
          Button("Try Again") { model.startExport() }
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        }
      }
    }
    .onAppear { model.registerAutomationActions() }
    .onDisappear { model.unregisterAutomationActions() }
  }
}
