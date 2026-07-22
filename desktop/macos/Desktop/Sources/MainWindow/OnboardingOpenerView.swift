import AppKit
import OmiTheme
import SwiftUI

/// The first beat after onboarding: Omi greets the user by name (and today's
/// calendar, when connected) and offers tappable starters that fire real queries.
/// Rendered in the empty-chat slot of both the Home chat and the Chat tab, so it
/// shows wherever the user lands post-onboarding and never pollutes history.
struct OnboardingOpenerView: View {
  let opener: OnboardingOpenerContent
  @ObservedObject var chatProvider: ChatProvider

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack(alignment: .top, spacing: OmiSpacing.sm) {
        if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
          let logoImage = NSImage(contentsOf: logoURL)
        {
          Image(nsImage: logoImage)
            .resizable()
            .scaledToFit()
            .frame(width: 28, height: 28)
        }
        Text(opener.greeting)
          .scaledFont(size: OmiType.subheading, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
          .fixedSize(horizontal: false, vertical: true)
        Spacer(minLength: 0)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        ForEach(opener.starters, id: \.self) { question in
          Button {
            startFromOpener(question)
          } label: {
            HStack(spacing: OmiSpacing.sm) {
              Text(question)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textPrimary)
                .multilineTextAlignment(.leading)
              Spacer(minLength: OmiSpacing.sm)
              Image(systemName: "arrow.up.right")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm + 2)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
              RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(OmiColors.border.opacity(0.5), lineWidth: 1)
            )
          }
          .buttonStyle(.plain)
        }
      }
    }
    .frame(maxWidth: 560, alignment: .leading)
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.vertical, 64)
  }

  private func startFromOpener(_ question: String) {
    AnalyticsManager.shared.chatMessageSent(
      messageLength: question.count, hasSelectedAppContext: false, source: "onboarding_opener")
    chatProvider.dismissOnboardingOpener()
    Task { await chatProvider.sendMainDraft(question) }
  }
}
