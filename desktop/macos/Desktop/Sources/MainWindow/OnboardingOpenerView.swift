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

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        ForEach(opener.starters, id: \.self) { question in
          OpenerStarterCard(question: question) {
            startFromOpener(question)
          }
        }
      }
    }
    .frame(maxWidth: 640, alignment: .leading)
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

/// One tappable starter. Filled surface + hover highlight so the three cards
/// read as the obvious next click, not passive text rows.
private struct OpenerStarterCard: View {
  let question: String
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.md) {
        Text(question)
          .scaledFont(size: OmiType.subheading, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
          .multilineTextAlignment(.leading)
        Spacer(minLength: OmiSpacing.sm)
        Image(systemName: "arrow.up.right")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(isHovering ? OmiColors.textPrimary : OmiColors.textTertiary)
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md + 2)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: 14, style: .continuous)
          .fill(isHovering ? OmiColors.backgroundSecondary : OmiColors.backgroundPrimary)
      )
      .overlay(
        RoundedRectangle(cornerRadius: 14, style: .continuous)
          .stroke(OmiColors.border.opacity(isHovering ? 0.9 : 0.5), lineWidth: 1)
      )
      // The stroke leaves a transparent interior, so without an explicit
      // hit shape only the text/icon were clickable — make the whole row tap.
      .contentShape(.rect(cornerRadius: 14))
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }
}
