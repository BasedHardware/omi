import OmiTheme
import SwiftUI

/// Onboarding step that shows what proactive notifications look like.
/// Uses a static example insight — no Gemini call needed.
struct OnboardingNotificationStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  var onContinue: () -> Void
  var onSkip: () -> Void

  @State private var showNotification = false
  @State private var notificationSent = false
  @State private var pulseAnimation = false

  private let insightHeadline = "Insight"
  private let insightText = "I'll watch your screen and send you proactive insights like this"

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        Text("Notifications")
          .font(.system(size: 18, weight: .semibold))
          .foregroundColor(Ink.primary)

        Spacer()

        // The escape hatch stays, and stays legible: this step cannot grant the permission
        // itself, so "Skip" is the only way past a machine that refuses the prompt.
        Button(action: onSkip) {
          Text("Skip")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.vertical, OmiSpacing.lg)

      GlassSeparator()

      Spacer()

      // Content
      VStack(spacing: OmiSpacing.section) {
        // Icon with glow
        ZStack {
          // A halo, not a glow: on the light panel the old `Color.white` bloom is the panel, so
          // the breathing circle darkens instead of lightens.
          Circle()
            .fill(Ink.primary.opacity(0.15))
            .frame(width: 100, height: 100)
            .blur(radius: 20)
            .scaleEffect(pulseAnimation ? 1.2 : 1.0)
            .animation(
              InkReduceMotion.animation(.easeInOut(duration: 2).repeatForever(autoreverses: true)),
              value: pulseAnimation)

          Image(systemName: "bell.badge.fill")
            .font(.system(size: 44))
            .foregroundStyle(
              LinearGradient(
                colors: [Ink.primary, Ink.secondary],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
              )
            )
        }
        .onAppear { pulseAnimation = true }

        VStack(spacing: OmiSpacing.sm) {
          Text("Proactive Intelligence")
            .inkStyle(InkType.stepHeadline, color: Ink.primary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)

          Text(
            "omi watches your screen and catches things you'd miss —\nwrong recipients, stale data, hidden shortcuts."
          )
          .inkStyle(InkType.prose, color: Ink.secondary)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
        }

        // Static notification preview
        if showNotification {
          notificationPreview
            .transition(
              .asymmetric(
                insertion: .move(edge: .top).combined(with: .opacity).combined(with: .scale(scale: 0.95)),
                removal: .opacity
              ))
        }
      }
      .padding(.horizontal, OmiSpacing.page)

      Spacer()

      // Bottom: confirmation + continue
      if notificationSent {
        VStack(spacing: OmiSpacing.md) {
          HStack(spacing: OmiSpacing.xs) {
            Image(systemName: "bell.badge.fill")
              .foregroundColor(Ink.primary)
              .font(.system(size: 12))
            Text("Notification shown below Ask omi")
              .inkStyle(InkType.statusLabel, color: Ink.secondary)
          }

          // A stadium capsule from the one button style — the hand-rolled white rounded rectangle
          // was the panel's own colour, so the CTA drew nothing at all on light glass.
          Button(action: onContinue) {
            Text("Continue")
              .frame(maxWidth: 280)
          }
          .buttonStyle(InkButtonStyle(kind: .primary))
          .keyboardShortcut(.defaultAction)
        }
        .padding(.bottom, OmiSpacing.section)
        .transition(.move(edge: .bottom).combined(with: .opacity))
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    // No ground: this step is hosted on the shell's one piece of glass, and a step that fills
    // itself is an opaque slab pasted over the panel. `glassContent()` pins the panel's light
    // appearance, because a first-run step is reached before any navigation stack has pinned it.
    .glassContent()
    .onAppear {
      let ownerID = RuntimeOwnerIdentity.currentOwnerId()
      FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
      FloatingControlBarManager.shared.showTemporarily()

      // Show the notification preview after a brief delay
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
        InkReduceMotion.perform(.spring(response: InkMotion.settle, dampingFraction: 0.8)) {
          showNotification = true
        }

        // Send a real macOS notification
        if let ownerID {
          NotificationService.shared.sendNotification(
            ownerID: ownerID,
            title: insightHeadline,
            message: insightText,
            assistantId: "onboarding",
            respectFrequency: false
          )
        }

        // Show "notification sent" + continue after a beat
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
          InkReduceMotion.perform(.easeInOut(duration: InkMotion.settle)) {
            notificationSent = true
          }
        }
      }
    }
  }

  // MARK: - macOS Notification Preview

  /// A picture of a macOS notification banner, and the one place in this file that keeps its own
  /// opaque surface.
  ///
  /// The same exemption `glassMediaMat` documents: this is a *depiction*, not a surface of ours. A
  /// Light Mode banner really is a white card with black type and two shadows, so redrawing it as a
  /// wash on the panel would make the preview stop looking like the thing it is previewing. Every
  /// colour below is therefore read against this card's own white, not against the glass.
  private var notificationPreview: some View {
    HStack(spacing: OmiSpacing.md) {
      // App icon
      ZStack {
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(
            LinearGradient(
              colors: [Color.black, Color.gray],
              startPoint: .topLeading,
              endPoint: .bottomTrailing
            )
          )
          .frame(width: 36, height: 36)

        Text("omi")
          .font(.system(size: 11, weight: .bold, design: .rounded))
          .foregroundColor(.white)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        HStack {
          Text("omi")
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(.black)

          Spacer()

          Text("now")
            .font(.system(size: 11))
            .foregroundColor(.gray)
        }

        Text(insightHeadline)
          .font(.system(size: 12, weight: .medium))
          .foregroundColor(.black.opacity(0.85))
          .lineLimit(1)

        Text(insightText)
          .font(.system(size: 12))
          .foregroundColor(.black.opacity(0.7))
          .lineLimit(2)
          .lineSpacing(1)
      }
    }
    .padding(OmiSpacing.md)
    .frame(maxWidth: 380, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.chipRadius)
        .fill(.white)
        .shadow(color: .black.opacity(0.15), radius: 12, x: 0, y: 4)
        .shadow(color: .black.opacity(0.05), radius: 1, x: 0, y: 1)
    )
  }
}
