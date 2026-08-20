//
//  SecondBrainHome.swift — a useful first question, backed by the user's real context.
//
//  This is a landing state inside the established answer panel, not a second chat. Its one primary
//  question, secondary suggestions, and Continue control all hand back to `QueryShellHome`, which
//  owns the only provider, draft, transcript, and route (INV-6).
//
//  The experience leads with proof rather than product architecture: a just-onboarded person sees
//  the answer Omi produced from their screen; a returning person sees real recent context and a
//  personalized question; a thin account sees readiness copy instead of a wall of zeroes.
//

import OmiTheme
import SwiftUI

/// The overview is an activation/empty-state layer, never an interstitial over a conversation the
/// user already started. The onboarding opener is the one exception because it is the explicit
/// handoff from setup into Home.
enum SecondBrainHomePresentationPolicy {
  static func showsOverview(
    requested: Bool,
    hasMessages: Bool,
    hasOnboardingOpener: Bool,
    isSending: Bool
  ) -> Bool {
    guard requested, !isSending else { return false }
    return hasOnboardingOpener || !hasMessages
  }
}

/// Suggestions never replace words the user has already put in the shared composer.
enum SecondBrainPromptPolicy {
  static func canUseSuggestion(draft: String) -> Bool {
    draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }
}

enum HomeSearchPresentationPolicy {
  static func isCompact(mode: QueryShellMode, isExpanded: Bool) -> Bool {
    mode == .answer && !isExpanded
  }
}

/// The value experience reduced to data and copy so activation, returning, loading, and thin-context
/// states can be verified without mounting a window.
struct SecondBrainHomeSnapshot: Equatable {
  enum Phase: Equatable {
    case activation
    case ready
    case gathering
  }

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

  struct Evidence: Equatable, Identifiable {
    enum Kind: Equatable {
      case conversation
      case memory
      case task

      var label: String {
        switch self {
        case .conversation: "Recent conversation"
        case .memory: "Remembered"
        case .task: "Open task"
        }
      }

      var systemImage: String {
        switch self {
        case .conversation: "waveform"
        case .memory: "brain.head.profile"
        case .task: "checkmark.circle"
        }
      }
    }

    let kind: Kind
    let text: String

    var id: String { "\(kind.label)-\(text)" }
  }

  let phase: Phase
  let headline: String
  let supportingCopy: String
  let promptLabel: String
  let heroPrompt: String
  let secondaryPrompts: [String]
  let sources: [Source]
  let sourceSummary: String
  let evidence: [Evidence]
  let proofReceipt: OnboardingProofReceipt?
  let total: Int?

  static func compose(
    conversations: Int,
    memories: Int,
    tasks: Int,
    screenCount: Int?,
    personalizedPrompts: [String],
    onboardingPrompts: [String],
    opener: OnboardingOpenerContent?,
    contextEvidence: [Evidence] = []
  ) -> SecondBrainHomeSnapshot {
    let safeConversations = max(0, conversations)
    let safeMemories = max(0, memories)
    let safeTasks = max(0, tasks)
    let safeScreenCount = screenCount.map { max(0, $0) }
    let knownWithoutScreen = safeConversations + safeMemories + safeTasks
    let total = safeScreenCount.map { knownWithoutScreen + $0 }
    let hasKnownContext = knownWithoutScreen + (safeScreenCount ?? 0) > 0

    let cleanedPersonalized = HomeSuggestionComposer.sanitize(personalizedPrompts)
    let returningFallbacks = HomeSuggestionComposer.compose(
      personalized: [], onboarding: onboardingPrompts)
    let rawPromptCandidates: [String]
    if let opener, opener.proofReceipt != nil {
      rawPromptCandidates =
        ["What should I focus on based on what's on my screen?"] + opener.starters
        + cleanedPersonalized + returningFallbacks
    } else if let opener, !opener.starters.isEmpty {
      rawPromptCandidates = opener.starters + cleanedPersonalized + returningFallbacks
    } else if !cleanedPersonalized.isEmpty {
      // Personal context earns the primary position. The universal question is a fallback, not the
      // face of a product whose entire promise is that it knows this particular person.
      rawPromptCandidates =
        cleanedPersonalized + [HomeSuggestionComposer.universalFirstQuestion] + returningFallbacks
    } else {
      rawPromptCandidates = returningFallbacks
    }
    let promptCandidates = uniquePrompts(rawPromptCandidates).filter {
      hasKnownContext || $0 != "What did I spend my time on this week?"
    }

    let heroPrompt = promptCandidates.first ?? HomeSuggestionComposer.universalFirstQuestion
    let proofReceipt = opener?.proofReceipt
    let phase: Phase = opener != nil ? .activation : (hasKnownContext ? .ready : .gathering)

    let headline: String
    let supportingCopy: String
    let promptLabel: String
    switch phase {
    case .activation:
      if proofReceipt != nil {
        headline = "You asked. Omi answered."
        supportingCopy = ""
        promptLabel = "Keep going"
      } else {
        headline = "\(opener?.greeting ?? "You're ready")."
        supportingCopy = opener?.subline ?? "Your context starts building as you talk and work."
        promptLabel = "START WITH WHAT'S AHEAD"
      }
    case .ready:
      headline = "What do you want to know?"
      supportingCopy =
        "Ask across your conversations, screen, memories, and tasks. When Omi uses your context, the answer links back to it."
      promptLabel =
        cleanedPersonalized.contains(heroPrompt)
        ? "Suggested question" : "Ask across your day"
    case .gathering:
      headline = "Your second brain starts with one question."
      supportingCopy =
        "Ask about what is on your screen or what happened today. Omi builds useful context as you work."
      promptLabel = "A good first question"
    }

    var sources: [Source] = []
    if safeConversations > 0 {
      sources.append(
        Source(
          kind: .conversations,
          title: "Conversations",
          detail: count(safeConversations, singular: "conversation"),
          systemImage: "waveform"))
    }
    if let safeScreenCount, safeScreenCount > 0 {
      sources.append(
        Source(
          kind: .screen,
          title: "Screen",
          detail: count(safeScreenCount, singular: "screen moment"),
          systemImage: "rectangle.on.rectangle"))
    } else if screenCount == nil {
      sources.append(
        Source(
          kind: .screen,
          title: "Screen",
          detail: "Screen history isn't ready yet",
          systemImage: "rectangle.on.rectangle"))
    }
    if safeMemories > 0 {
      sources.append(
        Source(
          kind: .memories,
          title: "Memories",
          detail: count(safeMemories, singular: "memory", plural: "memories"),
          systemImage: "brain.head.profile"))
    }
    if safeTasks > 0 {
      sources.append(
        Source(
          kind: .tasks,
          title: "Tasks",
          detail: count(safeTasks, singular: "open task"),
          systemImage: "checkmark.circle"))
    }

    let sourceSummary: String
    let knownParts = sources.filter { $0.detail != "Screen history isn't ready yet" }.map(\.detail)
    if !knownParts.isEmpty {
      sourceSummary = "Ready to answer from \(naturalList(knownParts))."
    } else if screenCount == nil {
      sourceSummary = "Screen history isn't ready yet. Conversations, memories, and tasks join as they arrive."
    } else {
      sourceSummary = "Your context starts building from the conversations you have and the work on your screen."
    }

    return SecondBrainHomeSnapshot(
      phase: phase,
      headline: headline,
      supportingCopy: supportingCopy,
      promptLabel: promptLabel,
      heroPrompt: heroPrompt,
      secondaryPrompts: Array(promptCandidates.dropFirst().prefix(2)),
      sources: sources,
      sourceSummary: sourceSummary,
      evidence: Array(cleanEvidence(contextEvidence).prefix(3)),
      proofReceipt: proofReceipt,
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

  private static func cleanEvidence(_ candidates: [Evidence]) -> [Evidence] {
    var seen = Set<String>()
    return candidates.compactMap { item in
      let collapsed = item.text
        .components(separatedBy: .whitespacesAndNewlines)
        .filter { !$0.isEmpty }
        .joined(separator: " ")
      guard !collapsed.isEmpty else { return nil }
      let key = collapsed.lowercased()
      guard !seen.contains(key) else { return nil }
      seen.insert(key)
      let text = collapsed.count <= 96 ? collapsed : String(collapsed.prefix(95)) + "…"
      return Evidence(kind: item.kind, text: text)
    }
  }

  private static func naturalList(_ values: [String]) -> String {
    switch values.count {
    case 0: return ""
    case 1: return values[0]
    case 2: return "\(values[0]) and \(values[1])"
    default: return values.dropLast().joined(separator: ", ") + ", and \(values.last ?? "")"
    }
  }
}

/// A quiet daily doorway into the established answer thread. There is one obvious action, followed
/// by evidence and two lower-weight alternatives; the shared composer remains mounted below it.
struct SecondBrainHome: View {
  let snapshot: SecondBrainHomeSnapshot
  let hasConversation: Bool
  let canUsePrompts: Bool
  let onAsk: (String) -> Void
  let onContinueConversation: () -> Void

  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @State private var hasRevealed = false
  /// Suggestions may refresh asynchronously. Freeze this presentation so a question cannot change
  /// under the pointer; newly generated ideas appear the next time the overview is mounted.
  @State private var frozenPrompts: [String]?

  private var presentedPrompts: [String] {
    frozenPrompts ?? [snapshot.heroPrompt] + snapshot.secondaryPrompts
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: OmiSpacing.xl) {
        identity
        promise

        if let proofReceipt = snapshot.proofReceipt {
          proof(proofReceipt)
        }

        SecondBrainHeroQuestion(
          label: snapshot.promptLabel,
          prompt: presentedPrompts[0],
          isEnabled: canUsePrompts,
          action: { onAsk(presentedPrompts[0]) }
        )

        ViewThatFits(in: .horizontal) {
          HStack(alignment: .top, spacing: OmiSpacing.page) {
            context
              .frame(minWidth: 360, maxWidth: .infinity, alignment: .leading)
            moreQuestions
              .frame(minWidth: 260, maxWidth: 320, alignment: .leading)
          }
          VStack(alignment: .leading, spacing: OmiSpacing.xl) {
            context
            moreQuestions
          }
        }
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.top, OmiSpacing.md)
      .padding(.bottom, OmiSpacing.xxl)
      .opacity(hasRevealed ? 1 : 0)
      .offset(y: hasRevealed || reduceMotion ? 0 : 7)
    }
    .scrollIndicators(.hidden)
    .accessibilityIdentifier("second-brain-home")
    .onAppear {
      if frozenPrompts == nil {
        frozenPrompts = [snapshot.heroPrompt] + snapshot.secondaryPrompts
      }
      if reduceMotion {
        hasRevealed = true
      } else {
        withAnimation(SBMotion.message) { hasRevealed = true }
      }
    }
  }

  private var identity: some View {
    HStack(spacing: OmiSpacing.sm) {
      SBLogo(size: 18)
      Text("Omi")
        .inkStyle(InkType.statusLabel, color: Ink.secondary)
      Spacer(minLength: OmiSpacing.md)
      if hasConversation {
        Button(action: onContinueConversation) {
          HStack(spacing: OmiSpacing.xs) {
            Text("Continue conversation")
            Image(systemName: "arrow.right")
          }
          .inkStyle(InkType.statusLabel, color: Ink.primary)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("second-brain-continue")
      }
    }
  }

  private var promise: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text(snapshot.headline)
        .inkStyle(InkType.introHero, color: Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      if !snapshot.supportingCopy.isEmpty {
        Text(snapshot.supportingCopy)
          .inkStyle(InkType.rowCopy, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: 660, alignment: .leading)
      }
    }
  }

  private func proof(_ receipt: OnboardingProofReceipt) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      Rectangle()
        .fill(Ink.primary)
        .frame(width: 2)
        .accessibilityHidden(true)

      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text("Your first Omi answer")
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
        Text(receipt.answerExcerpt)
          .inkStyle(InkType.rowCopy, color: Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
        Label(receipt.sourceLabel, systemImage: "rectangle.on.rectangle")
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
      }
    }
    .padding(.vertical, OmiSpacing.xs)
    .accessibilityElement(children: .combine)
    .accessibilityIdentifier("second-brain-proof")
  }

  @ViewBuilder
  private var context: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text(snapshot.evidence.isEmpty ? "What Omi can use" : "Recently available to Omi")
        .inkStyle(InkType.statusLabel, color: Ink.secondary)

      if !snapshot.evidence.isEmpty {
        VStack(alignment: .leading, spacing: 0) {
          ForEach(Array(snapshot.evidence.enumerated()), id: \.element.id) { index, item in
            if index > 0 { Divider().overlay(Ink.separator) }
            SecondBrainEvidenceRow(item: item)
          }
        }
      } else if !snapshot.sources.isEmpty {
        ViewThatFits(in: .horizontal) {
          HStack(alignment: .top, spacing: OmiSpacing.lg) {
            ForEach(snapshot.sources) { source in
              SecondBrainSourceSummary(source: source)
            }
          }
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            ForEach(snapshot.sources) { source in
              SecondBrainSourceSummary(source: source)
            }
          }
        }
      }

      if snapshot.sources.isEmpty {
        Text(snapshot.sourceSummary)
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      } else if !snapshot.evidence.isEmpty {
        Label("Private context from your Omi account", systemImage: "lock")
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
      }
    }
    .accessibilityElement(children: .contain)
  }

  @ViewBuilder
  private var moreQuestions: some View {
    if presentedPrompts.count > 1 {
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text("More to ask")
          .inkStyle(InkType.statusLabel, color: Ink.secondary)

        ForEach(Array(presentedPrompts.dropFirst().enumerated()), id: \.element) { index, prompt in
          SecondBrainTextQuestion(
            prompt: prompt,
            index: index + 1,
            isEnabled: canUsePrompts,
            action: { onAsk(prompt) }
          )
        }

        if !canUsePrompts {
          Text("Finish or clear your draft to use a suggestion.")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
    }
  }
}

private struct SecondBrainHeroQuestion: View {
  let label: String
  let prompt: String
  let isEnabled: Bool
  let action: () -> Void

  @State private var isHovering = false
  @FocusState private var isFocused: Bool

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      Text(label)
        .inkStyle(InkType.statusLabel, color: Ink.secondary)

      Button(action: action) {
        HStack(alignment: .center, spacing: OmiSpacing.lg) {
          Text(prompt)
            .scaledFont(size: OmiType.title, weight: .semibold)
            .foregroundStyle(Ink.primary)
            .multilineTextAlignment(.leading)
            .fixedSize(horizontal: false, vertical: true)
          Spacer(minLength: OmiSpacing.md)
          HStack(spacing: OmiSpacing.xs) {
            Text("Ask")
            Image(systemName: "arrow.right")
          }
          .inkStyle(InkType.statusLabel, color: Ink.surface)
          .padding(.horizontal, OmiSpacing.md)
          .frame(minHeight: 36)
          .background(Capsule().fill(Ink.primary))
          .accessibilityHidden(true)
        }
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.md)
        .frame(maxWidth: .infinity, minHeight: 76, alignment: .leading)
        .background(isHovering && isEnabled ? Ink.rowFillHover : Color.clear)
        .overlay(alignment: .top) { Divider().overlay(Ink.separator) }
        .overlay(alignment: .bottom) { Divider().overlay(Ink.separator) }
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .disabled(!isEnabled)
      .opacity(isEnabled ? 1 : 0.52)
      .focused($isFocused)
      .onHover { isHovering = $0 }
      .overlay(
        RoundedRectangle(cornerRadius: PageGlass.chipRadius, style: .continuous)
          .strokeBorder(isFocused ? Ink.primary : Color.clear, lineWidth: 2)
      )
      .help(isEnabled ? "Ask Omi: \(prompt)" : "Finish or clear your draft first")
      .accessibilityLabel("Ask Omi: \(prompt)")
      .accessibilityIdentifier("second-brain-prompt-0")
    }
  }
}

private struct SecondBrainTextQuestion: View {
  let prompt: String
  let index: Int
  let isEnabled: Bool
  let action: () -> Void

  @State private var isHovering = false
  @FocusState private var isFocused: Bool

  var body: some View {
    Button(action: action) {
      HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
        Text(prompt)
          .inkStyle(InkType.statusLabel, color: Ink.primary)
          .multilineTextAlignment(.leading)
          .fixedSize(horizontal: false, vertical: true)
        Spacer(minLength: OmiSpacing.sm)
        Image(systemName: "arrow.right")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(Ink.secondary)
          .accessibilityHidden(true)
      }
      .padding(.vertical, OmiSpacing.sm)
      .padding(.horizontal, OmiSpacing.xs)
      .background(
        RoundedRectangle(cornerRadius: PageGlass.chipRadius, style: .continuous)
          .fill(isHovering && isEnabled ? Ink.rowFillHover : Color.clear)
      )
      .overlay(
        RoundedRectangle(cornerRadius: PageGlass.chipRadius, style: .continuous)
          .strokeBorder(isFocused ? Ink.primary : Color.clear, lineWidth: 2)
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .disabled(!isEnabled)
    .opacity(isEnabled ? 1 : 0.45)
    .focused($isFocused)
    .onHover { isHovering = $0 }
    .help(isEnabled ? "Ask Omi: \(prompt)" : "Finish or clear your draft first")
    .accessibilityLabel("Ask Omi: \(prompt)")
    .accessibilityIdentifier("second-brain-prompt-\(index)")
  }
}

private struct SecondBrainEvidenceRow: View {
  let item: SecondBrainHomeSnapshot.Evidence

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      Image(systemName: item.kind.systemImage)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(Ink.primary)
        .frame(width: 20)
        .accessibilityHidden(true)
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(item.kind.label)
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
        Text(item.text)
          .inkStyle(InkType.rowCopy, color: Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .padding(.vertical, OmiSpacing.sm)
    .accessibilityElement(children: .combine)
  }
}

private struct SecondBrainSourceSummary: View {
  let source: SecondBrainHomeSnapshot.Source

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.sm) {
      Image(systemName: source.systemImage)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(Ink.primary)
        .frame(width: 20)
        .accessibilityHidden(true)
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(source.title)
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
        Text(source.detail)
          .inkStyle(InkType.rowCopy, color: Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
          .monospacedDigit()
      }
    }
    .accessibilityElement(children: .combine)
  }
}
