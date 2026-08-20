//
//  SecondBrainHome.swift — the proof of value before the first question.
//
//  Home used to open directly on a transcript. That is useful after somebody already knows what to
//  ask, but it makes the full app explain none of the reason Omi exists. This canvas shows the
//  product loop with the person's real corpus: what they heard, what appeared on their screen and
//  what Omi remembers flow into one personal answer. Its prompt rows call the host's one send path;
//  it owns no provider, transcript, draft or route (INV-6).
//
//  Brand: one neutral ink ladder and the shared glass only (INV-UI-1).
//

import OmiTheme
import SwiftUI

/// The value canvas reduced to data and copy so new, returning and temporarily-unavailable context
/// states can be verified without mounting a window.
struct SecondBrainHomeSnapshot: Equatable {
  struct Source: Equatable, Identifiable {
    enum Kind: Equatable {
      case conversations
      case screen
      case memories
      case tasks
    }

    let kind: Kind
    let title: String
    let detail: String
    let systemImage: String

    var id: String { title }
  }

  let greeting: String?
  let headline: String
  let supportingCopy: String
  let sources: [Source]
  let prompts: [String]
  let total: Int?

  static func compose(
    conversations: Int,
    memories: Int,
    tasks: Int,
    screenCount: Int?,
    personalizedPrompts: [String],
    onboardingPrompts: [String],
    opener: OnboardingOpenerContent?
  ) -> SecondBrainHomeSnapshot {
    let safeConversations = max(0, conversations)
    let safeMemories = max(0, memories)
    let safeTasks = max(0, tasks)
    let safeScreenCount = screenCount.map { max(0, $0) }
    let total = safeScreenCount.map { safeConversations + safeMemories + safeTasks + $0 }
    let hasKnownContext = safeConversations + safeMemories + safeTasks + (safeScreenCount ?? 0) > 0

    let prompts: [String]
    let returningPrompts = HomeSuggestionComposer.compose(
      personalized: personalizedPrompts,
      onboarding: onboardingPrompts)
    if let opener, !opener.starters.isEmpty {
      prompts = uniquePrompts(opener.starters + returningPrompts)
    } else {
      prompts = returningPrompts
    }

    return SecondBrainHomeSnapshot(
      greeting: opener?.greeting,
      headline: hasKnownContext ? "Your life, ready to answer." : "Your second brain starts here.",
      supportingCopy: opener?.subline
        ?? "Omi connects what you heard, saw, and decided — then answers with your context, not the internet's.",
      sources: [
        Source(
          kind: .conversations,
          title: "Heard",
          detail: count(safeConversations, singular: "conversation"),
          systemImage: "waveform"),
        Source(
          kind: .screen,
          title: "Seen",
          detail: safeScreenCount.map { count($0, singular: "screen moment") } ?? "Counting moments…",
          systemImage: "rectangle.on.rectangle"),
        Source(
          kind: .memories,
          title: "Remembered",
          detail: count(safeMemories, singular: "memory", plural: "memories"),
          systemImage: "brain.head.profile"),
        Source(
          kind: .tasks,
          title: "Decided",
          detail: count(safeTasks, singular: "open task"),
          systemImage: "checkmark.circle"),
      ],
      prompts: Array(prompts.prefix(3)),
      total: total)
  }

  private static func count(_ value: Int, singular: String, plural: String? = nil) -> String {
    "\(QueryShellCount.number(value)) \(value == 1 ? singular : (plural ?? singular + "s"))"
  }

  private static func uniquePrompts(_ candidates: [String]) -> [String] {
    var seen = Set<String>()
    return candidates.compactMap { candidate in
      let prompt = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
      let key = prompt.lowercased()
      guard !prompt.isEmpty, !seen.contains(key) else { return nil }
      seen.insert(key)
      return prompt
    }
  }
}

/// A landing state inside the established answer panel. Asking and continuing both replace this
/// view with `QueryAnswerThread`; the shared composer remains mounted below it the entire time.
struct SecondBrainHome: View {
  let snapshot: SecondBrainHomeSnapshot
  let hasConversation: Bool
  let onAsk: (String) -> Void
  let onContinueConversation: () -> Void

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
        HStack(alignment: .top, spacing: OmiSpacing.page) {
          promise
            .frame(maxWidth: .infinity, alignment: .leading)
          contextFlow
            .frame(maxWidth: .infinity, alignment: .leading)
        }

        questions
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.top, OmiSpacing.lg)
      .padding(.bottom, OmiSpacing.xxl)
    }
    .scrollIndicators(.hidden)
    .accessibilityIdentifier("second-brain-home")
  }

  private var promise: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(spacing: OmiSpacing.sm) {
        SBLogo(size: 18)
        Text(snapshot.greeting ?? "YOUR SECOND BRAIN")
          .geistMono(size: OmiType.caption, weight: .medium, tracking: OmiType.caption * 0.08)
          .foregroundStyle(Ink.secondary)
          .lineLimit(1)
      }

      Text(snapshot.headline)
        .inkStyle(InkType.introHero, color: Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      Text("The second brain you trust more than your first.")
        .inkStyle(InkType.rowCopy, color: Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      Text(snapshot.supportingCopy)
        .inkStyle(InkType.statusLabel, color: Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: 360, alignment: .leading)

      if hasConversation {
        Button(action: onContinueConversation) {
          HStack(spacing: OmiSpacing.xs) {
            Text("Continue last conversation")
            Image(systemName: "arrow.right")
          }
        }
        .buttonStyle(InkButtonStyle(kind: .secondary))
        .accessibilityIdentifier("second-brain-continue")
      }
    }
  }

  /// A single diagram, rather than three feature cards: personal context converges on Omi, and one
  /// grounded answer comes out. The relationship is the product value.
  private var contextFlow: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack {
        Text("YOUR CONTEXT")
          .geistMono(size: OmiType.caption, weight: .medium, tracking: OmiType.caption * 0.08)
          .foregroundStyle(Ink.secondary)
        Spacer(minLength: OmiSpacing.sm)
        if let total = snapshot.total {
          Text("\(QueryShellCount.number(total)) moments")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
            .monospacedDigit()
        }
      }

      HStack(spacing: OmiSpacing.md) {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          ForEach(snapshot.sources) { source in
            SecondBrainSourceRow(source: source)
          }
        }

        ZStack {
          Rectangle()
            .fill(Ink.separator)
            .frame(width: 28, height: 1)
          Circle()
            .fill(Ink.surface)
            .frame(width: 34, height: 34)
            .overlay(Circle().strokeBorder(Ink.hairline, lineWidth: 1))
            .overlay(SBLogo(size: 16))
        }
        .accessibilityHidden(true)

        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("One personal answer")
            .inkStyle(InkType.rowCopy, color: Ink.primary)
          Text("with sources\nand a next step")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
      .padding(OmiSpacing.lg)
      .glassCard(cornerRadius: PageGlass.cardRadius)
    }
  }

  private var questions: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text("TRY YOUR SECOND BRAIN")
        .geistMono(size: OmiType.caption, weight: .medium, tracking: OmiType.caption * 0.08)
        .foregroundStyle(Ink.secondary)

      HStack(spacing: OmiSpacing.sm) {
        ForEach(Array(snapshot.prompts.enumerated()), id: \.element) { index, prompt in
          SecondBrainPromptButton(prompt: prompt, index: index, isPrimary: index == 0) {
            onAsk(prompt)
          }
        }
      }
    }
  }
}

private struct SecondBrainSourceRow: View {
  let source: SecondBrainHomeSnapshot.Source

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: source.systemImage)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(Ink.primary)
        .frame(width: 20)
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(source.title)
          .inkStyle(InkType.rowCopy, color: Ink.primary)
        Text(source.detail)
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
          .monospacedDigit()
          .lineLimit(1)
      }
    }
  }
}

private struct SecondBrainPromptButton: View {
  let prompt: String
  let index: Int
  let isPrimary: Bool
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.sm) {
        Text(prompt)
          .inkStyle(InkType.statusLabel, color: isPrimary ? Ink.surface : Ink.primary)
          .multilineTextAlignment(.leading)
          .lineLimit(2)
        Spacer(minLength: 0)
        Image(systemName: "arrow.up.right")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(isPrimary ? Ink.surface : Ink.secondary)
      }
      .padding(.horizontal, OmiSpacing.md)
      .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
      .background(
        Capsule(style: .continuous)
          .fill(isPrimary ? Ink.primary : (isHovering ? Ink.rowFillHover : Ink.rowFill))
      )
      .overlay(
        Capsule(style: .continuous)
          .strokeBorder(isPrimary ? Color.clear : Ink.hairline, lineWidth: 1)
      )
      .contentShape(Capsule(style: .continuous))
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .accessibilityIdentifier("second-brain-prompt-\(index)")
  }
}
