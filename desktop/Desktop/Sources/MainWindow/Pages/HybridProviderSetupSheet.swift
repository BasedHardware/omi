import SwiftUI

/// Sheet that hosts the full BYOK provider editor (base URL, API key, per-slot models).
/// Lifted out of the Plan & Usage page to keep that surface as a calm status view.
struct HybridProviderSetupSheet: View {
  @Binding var baseURL: String
  @Binding var apiKey: String
  @Binding var chatModel: String
  @Binding var postTranscriptModel: String
  @Binding var proactiveModel: String
  @Binding var visionModel: String

  let status: String?
  let isSaving: Bool
  let isTesting: Bool
  let applyDefaults: () -> Void
  let save: () -> Void
  let test: (String) -> Void
  let dismiss: () -> Void

  var body: some View {
    VStack(spacing: 0) {
      header

      Divider().overlay(OmiColors.backgroundQuaternary)

      ScrollView {
        VStack(alignment: .leading, spacing: 18) {
          providerAccountCard

          slotCard(
            title: "Chat",
            subtitle: "Powers Ask Omi chat replies.",
            model: $chatModel,
            slot: HybridProviderPolicy.chatSlot
          )

          slotCard(
            title: "Post-transcript processing",
            subtitle: "Titles, summaries, memories, and action items.",
            model: $postTranscriptModel,
            slot: HybridProviderPolicy.postTranscriptSlot
          )

          slotCard(
            title: "Proactive assistants",
            subtitle: "Local assistant jobs. Defaults to \(HybridProviderReadiness.defaultSmallModel()).",
            model: $proactiveModel,
            slot: HybridProviderPolicy.proactiveSlot
          )

          slotCard(
            title: "Vision",
            subtitle: "Optional. Leave blank to use local OCR text.",
            model: $visionModel,
            slot: HybridProviderPolicy.visionSlot,
            optional: true
          )

          memorySearchNote

          if let status {
            Text(status)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textSecondary)
              .textSelection(.enabled)
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(12)
              .background(
                RoundedRectangle(cornerRadius: 8)
                  .fill(OmiColors.backgroundTertiary.opacity(0.5))
              )
          }
        }
        .padding(24)
      }

      Divider().overlay(OmiColors.backgroundQuaternary)

      footer
    }
    .frame(width: 560, height: 640)
    .background(OmiColors.backgroundPrimary)
  }

  // MARK: - Sections

  private var header: some View {
    HStack(alignment: .center) {
      VStack(alignment: .leading, spacing: 4) {
        Text("Configure providers")
          .scaledFont(size: 18, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(
          "Bring your own AI endpoint, then assign models per task. Keys stay on this Mac."
        )
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)
      }

      Spacer()

      Button(action: dismiss) {
        Image(systemName: "xmark")
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)
          .padding(8)
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, 24)
    .padding(.vertical, 18)
  }

  private var providerAccountCard: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Provider account")
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)

      TextField("Base URL", text: $baseURL)
        .textFieldStyle(.roundedBorder)

      SecureField("API key (optional on loopback)", text: $apiKey)
        .textFieldStyle(.roundedBorder)
    }
    .padding(16)
    .background(
      RoundedRectangle(cornerRadius: 10)
        .fill(OmiColors.backgroundTertiary.opacity(0.5))
    )
  }

  private func slotCard(
    title: String,
    subtitle: String,
    model: Binding<String>,
    slot: String,
    optional: Bool = false
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(title)
        .scaledFont(size: 13, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
      Text(subtitle)
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)

      TextField("Model", text: model)
        .textFieldStyle(.roundedBorder)

      HStack(spacing: 8) {
        Spacer()
        Button("Test") {
          test(slot)
        }
        .buttonStyle(.bordered)
        .disabled(
          isTesting
            || (optional
              && model.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        )
      }
    }
    .padding(16)
    .background(
      RoundedRectangle(cornerRadius: 10)
        .fill(OmiColors.backgroundTertiary.opacity(0.5))
    )
  }

  private var memorySearchNote: some View {
    HStack(alignment: .top, spacing: 8) {
      Image(systemName: "info.circle.fill")
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
        .padding(.top, 1)
      Text("Memory search uses the on-device local wiki / FTS index — no embeddings required.")
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
      Spacer()
    }
    .padding(.horizontal, 4)
  }

  private var footer: some View {
    HStack(spacing: 12) {
      Button("Apply local defaults", action: applyDefaults)
        .buttonStyle(.bordered)
        .disabled(isSaving)

      Spacer()

      Button("Done", action: dismiss)
        .buttonStyle(.bordered)

      Button {
        save()
      } label: {
        if isSaving {
          ProgressView().controlSize(.small)
        } else {
          Text("Save")
            .scaledFont(size: 13, weight: .semibold)
        }
      }
      .buttonStyle(.borderedProminent)
      .disabled(isSaving)
    }
    .padding(.horizontal, 24)
    .padding(.vertical, 14)
  }
}
