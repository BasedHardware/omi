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

  /// Leading glyphs cycle task → insight → question, echoing the reference
  /// composition; content strings stay untouched.
  private static let starterIcons = ["circle", "lightbulb", "bubble.left"]

  var body: some View {
    VStack(spacing: OmiSpacing.xl) {
      VStack(spacing: OmiSpacing.md) {
        if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
          let logoImage = NSImage(contentsOf: logoURL)
        {
          Image(nsImage: logoImage)
            .resizable()
            .scaledToFit()
            .frame(width: 44, height: 44)
        }
        // The greeting is the largest thing in the empty chat, so it takes the system's headline
        // role rather than a serif face borrowed from the dark chrome.
        Text(opener.greeting)
          .inkStyle(InkType.stepHeadline, color: Ink.primary)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)

        Text(opener.subline)
          .inkStyle(InkType.prose, color: Ink.secondary)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
      }

      VStack(spacing: OmiSpacing.sm) {
        ForEach(Array(opener.starters.enumerated()), id: \.element) { index, question in
          OpenerStarterCard(
            question: question,
            icon: Self.starterIcons[index % Self.starterIcons.count]
          ) {
            startFromOpener(question)
          }
        }
      }
    }
    .frame(maxWidth: 680)
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.vertical, 64)
  }

  private func startFromOpener(_ question: String) {
    PostOnboardingPromptSuggestions.consume()
    chatProvider.dismissOnboardingOpener()
    Task {
      await chatProvider.sendMainDraft(
        question,
        onAccepted: {
          AnalyticsManager.shared.chatMessageSent(
            messageLength: question.count, hasSelectedAppContext: false, source: "onboarding_opener")
        })
    }
  }
}

/// One tappable starter: slim full-width row — leading glyph, single-line
/// question, trailing chevron — with a filled surface and hover highlight.
private struct OpenerStarterCard: View {
  let question: String
  let icon: String
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.md) {
        Image(systemName: icon)
          .scaledFont(size: OmiType.subheading)
          .foregroundColor(Ink.secondary)
          .frame(width: 22)
        Text(question)
          .inkStyle(InkType.rowCopy, color: Ink.primary)
          // A starter is a one-line prompt by construction; the row is a fixed-height list item,
          // not a paragraph, so this truncation is the intended shape.
          .lineLimit(1)
          .truncationMode(.tail)
        Spacer(minLength: OmiSpacing.sm)
        // Two rungs, so the chevron's rest state is the reading rung and hover promotes it —
        // there is no third step to fade to on glass.
        Image(systemName: "chevron.right")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(isHovering ? Ink.primary : Ink.secondary)
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.lg)
      .frame(maxWidth: .infinity, alignment: .leading)
      .glassCard(cornerRadius: PageGlass.rowRadius, emphasized: isHovering)
      .contentShape(.rect(cornerRadius: PageGlass.rowRadius))
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }
}
