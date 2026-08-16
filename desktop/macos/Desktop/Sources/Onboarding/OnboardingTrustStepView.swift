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
          .buttonStyle(InkButtonStyle(kind: .primary))
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
        // `secondary` and not a fainter step: glass carries two rungs, so the arrow sits on the
        // same one as the words it belongs to.
        Text("↗")
          .font(.system(size: 12))
      }
      .foregroundColor(Ink.secondary)
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, 9)
      .glassChip()
    }
    .buttonStyle(.plain)
    .onHover { inside in
      if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() }
    }
    .accessibilityLabel("Open source and private by design — view the code on GitHub")
  }

  /// One capability, described rather than requested — this step only introduces them.
  ///
  /// Not `InkPermissionRow`: that row is a *control* (a checkbox, a live status word, a whole-row
  /// button that opens System Settings), and nothing here is grantable yet. The card metrics are
  /// shared instead, so this row and the real one read as the same object.
  private func permissionRow(icon: String, title: String, detail: String) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      Image(systemName: icon)
        .font(.system(size: 14, weight: .semibold))
        .foregroundColor(Ink.primary)
        .frame(width: 28, height: 28)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
            .fill(Ink.rowFill)
        )

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(title)
          .inkStyle(InkType.rowCopy, color: Ink.primary)
          // The row wraps; it never truncates. A `Text` given less height than it needs ends in
          // "…", and a capability the user is being asked to trust must not disappear.
          .fixedSize(horizontal: false, vertical: true)
        if !detail.isEmpty {
          Text(detail)
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
      }

      Spacer()
    }
    .padding(OmiSpacing.md)
    .glassCard(cornerRadius: PageGlass.rowRadius)
  }
}
