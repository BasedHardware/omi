import OmiTheme
import SwiftUI

/// Onboarding step explaining that omi auto-creates tasks.
struct OnboardingTasksStepView: View {
  var onComplete: () -> Void
  var onSkip: (() -> Void)? = nil
  var onForceComplete: (() -> Void)?

  @State private var pulseAnimation = false
  @State private var showTasks = false

  private let mockTasks: [(String, String, Bool)] = [
    ("Task 1", "From today's meeting", false),
    ("Task 2", "Mentioned in Slack", false),
    ("Task 3", "Getting started", true),
  ]

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        OnboardingLogoMark(onForceComplete: onForceComplete)
        Spacer()
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.vertical, OmiSpacing.lg)

      Divider()
        .background(OmiColors.backgroundTertiary)

      Spacer()

      VStack(spacing: OmiSpacing.xxl) {
        // Icon with glow
        ZStack {
          Circle()
            .fill(Color.white.opacity(0.15))
            .frame(width: 100, height: 100)
            .blur(radius: 20)
            .scaleEffect(pulseAnimation ? 1.2 : 1.0)
            .omiAnimation(.easeInOut(duration: 2).repeatForever(autoreverses: true), value: pulseAnimation)

          Image(systemName: "checklist")
            .font(.system(size: 44))
            .foregroundStyle(
              LinearGradient(
                colors: [Color.white, Color.gray],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
              )
            )
        }
        .onAppear { pulseAnimation = true }

        VStack(spacing: OmiSpacing.sm) {
          Text("Auto-created Tasks")
            .font(.system(size: 24, weight: .bold))
            .foregroundColor(OmiColors.textPrimary)

          Text(
            "omi listens to your conversations and automatically\ncreates tasks, action items, and follow-ups for you."
          )
          .font(.system(size: 14))
          .foregroundColor(OmiColors.textSecondary)
          .multilineTextAlignment(.center)
          .lineSpacing(4)
        }

        // Mock task cards
        if showTasks {
          VStack(spacing: OmiSpacing.sm) {
            ForEach(Array(mockTasks.enumerated()), id: \.offset) { index, task in
              mockTaskRow(title: task.0, subtitle: task.1, checked: task.2)
                .transition(
                  .asymmetric(
                    insertion: .move(edge: .bottom).combined(with: .opacity),
                    removal: .opacity
                  ))
            }
          }
          .frame(maxWidth: 420)
        }
      }
      .padding(.horizontal, OmiSpacing.page)

      Spacer()

      VStack(spacing: OmiSpacing.md) {
        Button(action: onComplete) {
          Text("Take me to Omi")
            .font(.system(size: 15, weight: .semibold))
            .foregroundColor(.black)
            .frame(maxWidth: 280)
            .padding(.vertical, OmiSpacing.md)
            .background(Color.white)
            .cornerRadius(OmiChrome.smallControlRadius)
        }
        .buttonStyle(.plain)
        .keyboardShortcut(.defaultAction)

      }
      .padding(.bottom, OmiSpacing.section)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(OmiColors.backgroundPrimary)
    .onAppear {
      // Stagger task card appearance
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
        OmiMotion.withGated(.spring(response: 0.5, dampingFraction: 0.8)) {
          showTasks = true
        }
      }
    }
  }

  private func mockTaskRow(title: String, subtitle: String, checked: Bool) -> some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: checked ? "checkmark.circle.fill" : "circle")
        .font(.system(size: 18))
        .foregroundColor(checked ? .green : OmiColors.textTertiary)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(title)
          .font(.system(size: 13))
          .foregroundColor(checked ? OmiColors.textTertiary : OmiColors.textPrimary)
          .strikethrough(checked)
          .lineLimit(1)

        Text(subtitle)
          .font(.system(size: 11))
          .foregroundColor(OmiColors.textTertiary)
      }

      Spacer()
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(OmiColors.backgroundSecondary)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .stroke(OmiColors.backgroundTertiary.opacity(0.5), lineWidth: 1)
        )
    )
  }
}
