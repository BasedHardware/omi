import OmiTheme
import SwiftUI

/// The new-user Home surface, shown until activation (first conversation
/// captured + first question asked — the two first-48h behaviors that
/// separate retained users from churned ones in the July 2026 usage study).
///
/// Leads with proof Omi already delivered: real memories ingested during
/// onboarding. Below, two ambient pipeline pills show capture working (or the
/// honest fix when a permission was skipped — never a fake checkmark). The
/// ask bar rendered underneath by `DashboardPage` is the single ask
/// affordance; the keycap row teaches the floating-bar shortcut.
struct HomeFirstWinSection: View {
  /// Honest pipeline state per capture lane. Permission granted is NOT the
  /// same as capture running — `paused` renders the truthful resume
  /// affordance instead of a fake pulsing dot.
  enum PipelineState: Equatable {
    case blocked
    case paused
    case waiting
    case live
    case done
  }

  let memories: [String]
  let memoryCount: Int
  let shortcutTokens: [String]
  let conversationState: PipelineState
  let firstConversationTitle: String?
  let screenState: PipelineState
  let screenshotsToday: Int?
  let onOpenMemories: () -> Void
  let onFixPermissions: () -> Void
  let onResumeListening: () -> Void
  let onResumeCapture: () -> Void
  let onOpenConversations: () -> Void

  var body: some View {
    VStack(spacing: OmiSpacing.lg) {
      VStack(spacing: OmiSpacing.xs) {
        Text("Omi already knows you.")
          .font(.system(size: 34, weight: .medium, design: .serif))
          .foregroundStyle(HomeStagePalette.ink)
          .lineLimit(1)
          .minimumScaleFactor(0.7)

        Text("Learned during setup — before your first conversation.")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundStyle(HomeStagePalette.muted)
      }

      if !memories.isEmpty {
        VStack(spacing: OmiSpacing.xs) {
          ForEach(Array(memories.enumerated()), id: \.offset) { _, memory in
            HomeFirstWinMemoryRow(text: memory, onTap: onOpenMemories)
          }

          if memoryCount > memories.count {
            Button(action: onOpenMemories) {
              Text("…and \(memoryCount - memories.count) more — see everything Omi learned")
                .scaledFont(size: OmiType.caption, weight: .medium)
                .foregroundStyle(HomeStagePalette.muted)
                .underline(false)
            }
            .buttonStyle(.plain)
            .padding(.top, OmiSpacing.xxs)
          }
        }
      } else {
        Text("Omi starts learning the moment you do anything.")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundStyle(HomeStagePalette.secondary)
      }

      HStack(spacing: OmiSpacing.sm) {
        conversationPill
        screenPill
      }

      if !shortcutTokens.isEmpty {
        HStack(spacing: OmiSpacing.xs) {
          Text("Ask from anywhere")
            .scaledFont(size: OmiType.micro, weight: .medium)
            .foregroundStyle(HomeStagePalette.faint)
          ForEach(Array(shortcutTokens.enumerated()), id: \.offset) { _, token in
            HomeFirstWinKeycap(token: token)
          }
        }
      }
    }
    .frame(maxWidth: .infinity)
    .accessibilityIdentifier("home-first-win")
  }

  // MARK: Pipeline pills

  @ViewBuilder
  private var conversationPill: some View {
    switch conversationState {
    case .done:
      HomeFirstWinPill(
        state: .done,
        text: firstConversationTitle.map { "First conversation: \($0)" }
          ?? "First conversation captured",
        actionLabel: nil,
        action: onOpenConversations
      )
    case .blocked:
      HomeFirstWinPill(
        state: .blocked,
        text: "First conversation",
        actionLabel: "Enable microphone →",
        action: onFixPermissions
      )
    case .paused:
      HomeFirstWinPill(
        state: .blocked,
        text: "Listening is off",
        actionLabel: "Turn on →",
        action: onResumeListening
      )
    case .live:
      HomeFirstWinPill(
        state: .active(pulsing: true),
        text: "Listening — your first conversation lands here",
        actionLabel: nil,
        action: nil
      )
    case .waiting:
      HomeFirstWinPill(
        state: .active(pulsing: false),
        text: "First conversation — start talking or join a meeting",
        actionLabel: nil,
        action: nil
      )
    }
  }

  @ViewBuilder
  private var screenPill: some View {
    switch screenState {
    case .blocked:
      HomeFirstWinPill(
        state: .blocked,
        text: "Screen memory",
        actionLabel: "Turn on →",
        action: onFixPermissions
      )
    case .paused:
      HomeFirstWinPill(
        state: .blocked,
        text: "Screen memory is paused",
        actionLabel: "Resume →",
        action: onResumeCapture
      )
    case .live, .waiting, .done:
      HomeFirstWinPill(
        state: .active(pulsing: true),
        text: screenshotsToday.map { $0 > 0 ? "Screen memory — \($0) screens so far" : "Screen memory — capturing" }
          ?? "Screen memory — capturing",
        actionLabel: nil,
        action: nil
      )
    }
  }
}

// MARK: - Pieces

private struct HomeFirstWinMemoryRow: View {
  let text: String
  let onTap: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onTap) {
      HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
        Image(systemName: "brain")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(HomeStagePalette.secondary)
          .frame(width: 18)

        Text(text)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundStyle(HomeStagePalette.ink)
          .lineLimit(2)
          .multilineTextAlignment(.leading)

        Spacer(minLength: 0)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
          .fill(isHovering ? HomeStagePalette.tileHover : HomeStagePalette.tile.opacity(0.85))
      )
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
          .stroke(HomeStagePalette.hairline.opacity(0.8), lineWidth: 1)
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }
}

private struct HomeFirstWinKeycap: View {
  let token: String

  var body: some View {
    Text(token)
      .scaledFont(size: OmiType.caption, weight: .semibold)
      .foregroundStyle(HomeStagePalette.secondary)
      .padding(.horizontal, 7)
      .padding(.vertical, 3)
      .background(
        RoundedRectangle(cornerRadius: 5, style: .continuous)
          .fill(HomeStagePalette.tile)
      )
      .overlay(
        RoundedRectangle(cornerRadius: 5, style: .continuous)
          .stroke(HomeStagePalette.hairline, lineWidth: 1)
      )
  }
}

private struct HomeFirstWinPill: View {
  enum PillState {
    case active(pulsing: Bool)
    case blocked
    case done
  }

  let state: PillState
  let text: String
  let actionLabel: String?
  let action: (() -> Void)?

  @State private var isHovering = false

  var body: some View {
    Button {
      action?()
    } label: {
      HStack(spacing: OmiSpacing.xs) {
        indicator

        Text(text)
          .scaledFont(size: OmiType.micro, weight: .medium)
          .foregroundStyle(HomeStagePalette.secondary)
          .lineLimit(1)

        if let actionLabel {
          Text(actionLabel)
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(isHovering ? HomeStagePalette.ink : HomeStagePalette.secondary)
        }
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, 5)
      .background(Capsule().fill(HomeStagePalette.tile.opacity(0.9)))
      .overlay(Capsule().stroke(HomeStagePalette.hairline, lineWidth: 1))
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .disabled(action == nil)
    .onHover { isHovering = $0 }
  }

  @ViewBuilder
  private var indicator: some View {
    switch state {
    case .active:
      Circle()
        .fill(HomeStagePalette.green)
        .frame(width: 6, height: 6)
    case .blocked:
      Circle()
        .stroke(HomeStagePalette.muted, lineWidth: 1.2)
        .frame(width: 6, height: 6)
    case .done:
      Image(systemName: "checkmark.circle.fill")
        .scaledFont(size: OmiType.micro, weight: .semibold)
        .foregroundStyle(HomeStagePalette.green)
    }
  }
}
