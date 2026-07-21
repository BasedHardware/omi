import AppKit
import OmiTheme
import SwiftUI

struct OnboardingTrustStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Before I continue",
      title: "I’m going to ask for a few permissions.",
      description: "",
      layoutMode: .centered,
      onForceComplete: onForceComplete
    ) {
      VStack(spacing: OmiSpacing.lg) {
        openSourceChip

        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          permissionRow(
            icon: "display", title: "Screen + files",
            detail: "Build context from what you’re working on.")
          permissionRow(
            icon: "mic.fill", title: "Microphone",
            detail: "Capture voice notes and meeting context.")
          permissionRow(
            icon: "sparkles", title: "Accessibility + automation",
            detail: "Know the active app and act when you ask.")
        }
        .frame(maxWidth: 560, alignment: .leading)

        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          Button("Continue") {
            coordinator.clearLastActionError()
            onContinue()
          }
          .buttonStyle(OmiButtonStyle(.primary))
          .keyboardShortcut(.defaultAction)
        }
      }
      .frame(maxWidth: .infinity, alignment: .center)
      .onAppear {
        coordinator.clearLastActionError()
      }
    }
  }

  /// Pill chip from the mock: octocat-style mark + "Open source & private by
  /// design" + ↗, opening the public repo.
  private var openSourceChip: some View {
    Button {
      guard let url = URL(string: "https://github.com/BasedHardware/omi") else { return }
      NSWorkspace.shared.open(url)
    } label: {
      HStack(spacing: 9) {
        Image(systemName: "chevron.left.forwardslash.chevron.right")
          .font(.system(size: 13, weight: .semibold))
        Text("Open source & private by design")
          .font(.system(size: 14, weight: .semibold))
        Text("↗")
          .font(.system(size: 12))
          .foregroundColor(OmiColors.textTertiary)
      }
      .foregroundColor(OmiColors.textSecondary)
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, 9)
      .background(Capsule().fill(OmiColors.backgroundSecondary))
      .overlay(Capsule().stroke(Color.white.opacity(0.08), lineWidth: 1))
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { inside in
      if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() }
    }
    .accessibilityLabel("Open source and private by design — view the code on GitHub")
  }

  private func permissionRow(icon: String, title: String, detail: String) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      Image(systemName: icon)
        .font(.system(size: 14, weight: .semibold))
        .foregroundColor(.white.opacity(0.85))
        .frame(width: 28, height: 28)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
            .fill(OmiColors.backgroundSecondary)
        )

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(title)
          .font(.system(size: 14, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)
        if !detail.isEmpty {
          Text(detail)
            .font(.system(size: 13))
            .foregroundColor(OmiColors.textSecondary)
        }
      }

      Spacer()
    }
    .padding(OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
        .fill(OmiColors.backgroundTertiary.opacity(0.55))
    )
  }
}
