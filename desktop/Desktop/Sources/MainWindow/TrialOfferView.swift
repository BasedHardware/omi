import SwiftUI

/// First-sign-in opt-in offer for the desktop 3-day premium trial.
///
/// Rendered as a `.overlay` on `DesktopHomeView` (the same surface as
/// `UsageLimitPopupView`). Surface gating happens in `AppState`:
/// `shouldShowTrialOffer` returns true when the backend reports
/// `trialAvailable == true && trialStartedAt == nil` and the per-uid
/// "already saw it" UserDefaults flag is unset.
///
/// Either button calls `appState.markTrialOfferSeen()` to set the flag so
/// the modal never auto-fires again on this device. "Start Trial" also
/// calls `appState.startTrial()` which hits POST `/v1/users/me/trial/start`
/// and refreshes the published metadata (kicking the countdown UI on).
struct TrialOfferView: View {
  @ObservedObject var appState: AppState
  let onDismiss: () -> Void

  // Feature labels are server-driven (TrialMetadata.trial_features). Falling
  // back to a fixed copy if the metadata happens to be stale at modal-render
  // time — should never happen in practice since shouldShowTrialOffer
  // requires metadata to be present.
  private var features: [String] {
    appState.trialMetadata?.trialFeatures ?? [
      "unlimited_listening",
      "unlimited_transcription",
      "unlimited_memories",
      "unlimited_insights",
    ]
  }

  private func displayLabel(for feature: String) -> String {
    switch feature {
    case "unlimited_listening": return "Unlimited listening"
    case "unlimited_transcription": return "Unlimited transcription"
    case "unlimited_memories": return "Unlimited memories"
    case "unlimited_insights": return "Unlimited insights"
    case "30_chat_questions_per_month": return "30 chat questions / month"
    default: return feature.replacingOccurrences(of: "_", with: " ").capitalized
    }
  }

  var body: some View {
    ZStack {
      Color.black.opacity(0.55)
        .ignoresSafeArea()

      VStack(spacing: 0) {
        HStack {
          Spacer()
          Button(action: dismiss) {
            Image(systemName: "xmark")
              .scaledFont(size: 14, weight: .semibold)
              .foregroundColor(OmiColors.textTertiary)
              .padding(8)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
        }
        .padding(.horizontal, 8)
        .padding(.top, 8)

        VStack(spacing: 20) {
          ZStack {
            Circle()
              .fill(OmiColors.purplePrimary.opacity(0.15))
              .frame(width: 64, height: 64)
            Image(systemName: "sparkles")
              .scaledFont(size: 28, weight: .semibold)
              .foregroundColor(OmiColors.purplePrimary)
          }

          VStack(spacing: 8) {
            Text("Try Omi Premium free for 3 days")
              .scaledFont(size: 20, weight: .bold)
              .foregroundColor(OmiColors.textPrimary)
              .multilineTextAlignment(.center)

            Text("Unlock everything for three days — no card required. Cancel anytime.")
              .scaledFont(size: 14)
              .foregroundColor(OmiColors.textTertiary)
              .multilineTextAlignment(.center)
              .fixedSize(horizontal: false, vertical: true)
              .padding(.horizontal, 16)
          }

          VStack(alignment: .leading, spacing: 8) {
            ForEach(features, id: \.self) { feature in
              HStack(spacing: 10) {
                Image(systemName: "checkmark.circle.fill")
                  .scaledFont(size: 14, weight: .semibold)
                  .foregroundColor(OmiColors.purplePrimary)
                Text(displayLabel(for: feature))
                  .scaledFont(size: 13)
                  .foregroundColor(OmiColors.textPrimary)
                Spacer()
              }
            }
          }
          .padding(.horizontal, 24)

          VStack(spacing: 10) {
            Button(action: startTrial) {
              Text("Start Trial")
                .scaledFont(size: 15, weight: .semibold)
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 44)
                .background(
                  RoundedRectangle(cornerRadius: 10)
                    .fill(OmiColors.purplePrimary)
                )
            }
            .buttonStyle(.plain)

            Button(action: dismiss) {
              Text("Maybe later")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.purplePrimary)
                .frame(maxWidth: .infinity)
                .frame(height: 32)
            }
            .buttonStyle(.plain)
          }
          .padding(.horizontal, 24)
        }
        .padding(.bottom, 28)
      }
      .frame(width: 380)
      .background(
        RoundedRectangle(cornerRadius: 16)
          .fill(OmiColors.backgroundRaised)
          .overlay(
            RoundedRectangle(cornerRadius: 16)
              .stroke(OmiColors.border, lineWidth: 1)
          )
      )
      .shadow(color: .black.opacity(0.5), radius: 24, y: 8)
    }
    .transition(.opacity.animation(.easeInOut(duration: 0.2)))
  }

  private func dismiss() {
    appState.markTrialOfferSeen()
    onDismiss()
  }

  private func startTrial() {
    appState.markTrialOfferSeen()
    onDismiss()
    Task {
      await appState.startTrial()
    }
  }
}
