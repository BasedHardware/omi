import AppKit
import OmiTheme
import SwiftUI

// MARK: - Policy

/// Which remote prompt (if any) is due. Pure so the trigger contract is
/// unit-testable. One prompt at a time; unresolved prompts are ordered by id
/// so the choice is deterministic across polls.
enum RemotePromptPolicy {
  static func duePrompt(
    specs: [RemotePromptSpec],
    resolvedIds: Set<String>,
    questionCount: Int
  ) -> RemotePromptSpec? {
    specs
      .filter { !resolvedIds.contains($0.id) }
      .filter { spec in
        switch spec.triggerKind {
        case "question_count":
          return questionCount >= max(spec.triggerCount, 1)
        default:  // "app_launch" and forward-compatible unknown kinds
          return spec.triggerKind == "app_launch"
        }
      }
      .sorted { $0.id < $1.id }
      .first
  }
}

// MARK: - Engine

/// Renders prompts authored on admin.omi.me without app releases: polls
/// `GET /v2/desktop/prompts` (launch + every 5 minutes — deactivating a
/// prompt on admin hides it within one poll), evaluates triggers against the
/// same accepted-question ledger the built-in rating prompt uses, and reports
/// answers to PostHog (`Desktop Prompt Answered` / `Dismissed`).
@MainActor
final class RemotePromptEngine: ObservableObject {
  static let shared = RemotePromptEngine()

  @Published private(set) var current: RemotePromptSpec?

  private(set) var specs: [RemotePromptSpec] = []
  private var pollTask: Task<Void, Never>?
  private let defaults = UserDefaults.standard
  static let pollInterval: TimeInterval = 300

  /// Seam for tests and the automation bridge; production uses APIClient.
  var fetch: () async throws -> [RemotePromptSpec]
  /// Injectable for tests; production reads the real auth state.
  var isSignedInCheck: () -> Bool = { AuthState.shared.isSignedIn }

  private init() {
    fetch = {
      try await APIClient.shared.getDesktopPrompts(
        channel: AppBuild.currentUpdateChannel,
        build: Int(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "") ?? 0
      ).prompts
    }
  }

  func start() {
    guard pollTask == nil else { return }
    pollTask = Task { @MainActor [weak self] in
      while !Task.isCancelled {
        await self?.refreshFromServer()
        try? await Task.sleep(nanoseconds: UInt64(Self.pollInterval * 1_000_000_000))
      }
    }
  }

  func refreshFromServer() async {
    guard isSignedInCheck() else { return }
    do {
      specs = try await fetch()
    } catch {
      // Fail closed to "no new prompts"; an already-visible prompt stays so a
      // transient network error does not flicker the bar away mid-answer.
      log("RemotePromptEngine: fetch failed: \(error.localizedDescription)")
      return
    }
    // A prompt deactivated on admin disappears from the payload — drop it
    // even if currently showing (this is the no-release kill path).
    if let showing = current, !specs.contains(where: { $0.id == showing.id }) {
      current = nil
    }
    evaluate()
  }

  /// The accepted-question ledger IS the persisted rating-prompt counter —
  /// one source of truth, so relaunches and the history seed carry over to
  /// "after Nth question" remote prompts instead of restarting at zero.
  private var questionCount: Int {
    defaults.integer(forKey: DefaultsKey.ratingPromptQuestionCount.rawValue)
  }

  /// Notification from the accepted-question seam (the manager increments the
  /// persisted counter before calling this).
  func recordQuestionAsked() {
    evaluate()
  }

  /// The built-in rating ask owns the bottom slot whenever it is visible.
  /// A remote prompt that was already on screen is SUSPENDED (cleared without
  /// a resolution) and re-offered by evaluate() once the ask resolves — the
  /// same third question that arms the rating bar must never leave two bars
  /// stacked in one overlay.
  func builtInAskChanged() {
    let askActive =
      RatingPromptManager.shared.isVisible || RatingPromptManager.shared.thankYouRating != nil
    if askActive {
      current = nil
    } else {
      evaluate()
    }
  }

  func answer(value: String) {
    guard let spec = current else { return }
    markResolved(spec.id, outcome: "answered")
    AnalyticsManager.shared.desktopPromptAnswered(
      promptId: spec.id, promptType: spec.type, value: value)
    current = nil
    evaluate()
  }

  func openCTA() {
    guard let spec = current else { return }
    if let raw = spec.ctaURL, let url = URL(string: raw) {
      NSWorkspace.shared.open(url)
    }
    markResolved(spec.id, outcome: "answered")
    AnalyticsManager.shared.desktopPromptAnswered(
      promptId: spec.id, promptType: spec.type, value: "cta_clicked")
    current = nil
    evaluate()
  }

  func dismissCurrent() {
    guard let spec = current else { return }
    markResolved(spec.id, outcome: "dismissed")
    AnalyticsManager.shared.desktopPromptDismissed(promptId: spec.id, promptType: spec.type)
    current = nil
    evaluate()
  }

  /// Automation/testing hook: forget local resolutions and counters so the
  /// real trigger path can be exercised repeatedly on a dev bundle.
  func resetForTesting() {
    for spec in specs {
      defaults.removeObject(forKey: ScopedDefaultsKey.remotePromptResolution(promptId: spec.id))
    }
    current = nil
    evaluate()
  }

  private func evaluate() {
    // The built-in rating ask keeps right of way; remote prompts wait.
    guard RatingPromptManager.shared.isVisible == false,
      RatingPromptManager.shared.thankYouRating == nil
    else { return }
    guard current == nil else { return }
    let resolved = Set(
      specs.map(\.id).filter {
        defaults.object(forKey: ScopedDefaultsKey.remotePromptResolution(promptId: $0)) != nil
      })
    if let due = RemotePromptPolicy.duePrompt(
      specs: specs, resolvedIds: resolved, questionCount: questionCount)
    {
      current = due
      AnalyticsManager.shared.desktopPromptShown(promptId: due.id, promptType: due.type)
    }
  }

  private func markResolved(_ id: String, outcome: String) {
    defaults.set(outcome, forKey: ScopedDefaultsKey.remotePromptResolution(promptId: id))
  }
}

// MARK: - View

/// Closable sticky bar above the composer rendering the active remote prompt.
struct RemotePromptBar: View {
  @ObservedObject private var engine = RemotePromptEngine.shared
  @State private var hoveredStar = 0

  var body: some View {
    if let spec = engine.current {
      HStack(spacing: OmiSpacing.lg) {
        Text(spec.question)
          .font(.system(size: 13, weight: .medium))
          .foregroundColor(.primary)

        switch spec.type {
        case "stars":
          starsRow
        case "nps":
          npsRow
        case "choice":
          choiceRow(spec.options)
        default:  // banner
          if let label = spec.ctaLabel {
            Button(label) { engine.openCTA() }
              .buttonStyle(.borderedProminent)
              .controlSize(.small)
              .tint(.primary)
          }
        }

        Button {
          engine.dismissCurrent()
        } label: {
          Image(systemName: "xmark")
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(.secondary)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Dismiss prompt")
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.vertical, OmiSpacing.md)
      .background(
        RoundedRectangle(cornerRadius: 10)
          .fill(.regularMaterial)
          .overlay(
            RoundedRectangle(cornerRadius: 10)
              .stroke(Color.primary.opacity(0.08), lineWidth: 1)
          )
      )
      // Clears the chat composer row pinned to the window's bottom edge.
      .padding(.bottom, 76)
      .transition(.move(edge: .bottom).combined(with: .opacity))
    }
  }

  private var starsRow: some View {
    HStack(spacing: OmiSpacing.xs) {
      ForEach(1...5, id: \.self) { star in
        Button {
          engine.answer(value: "\(star)")
        } label: {
          Image(systemName: star <= hoveredStar ? "star.fill" : "star")
            .font(.system(size: 15))
            .foregroundColor(star <= hoveredStar ? .yellow : .secondary)
        }
        .buttonStyle(.plain)
        .onHover { inside in
          if inside {
            hoveredStar = star
          } else if hoveredStar == star {
            hoveredStar = star - 1
          }
        }
        .accessibilityLabel("Answer \(star)")
      }
    }
  }

  private var npsRow: some View {
    HStack(spacing: 2) {
      ForEach(0...10, id: \.self) { n in
        Button("\(n)") { engine.answer(value: "\(n)") }
          .buttonStyle(.bordered)
          .controlSize(.mini)
      }
    }
  }

  private func choiceRow(_ options: [String]) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      ForEach(options, id: \.self) { option in
        Button(option) { engine.answer(value: option) }
          .buttonStyle(.bordered)
          .controlSize(.small)
      }
    }
  }
}
