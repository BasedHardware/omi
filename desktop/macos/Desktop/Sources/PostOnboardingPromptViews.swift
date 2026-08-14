import OmiTheme
import SwiftUI

/// The first thing a new user sees once onboarding closes.
///
/// This used to be a bare list of questions, which answered "what could I ask"
/// but not the thing people actually get stuck on: the setup window vanishes and
/// the app becomes invisible, so they do not know where Omi went or how to bring
/// it back. The orientation cues above the questions name the real affordances —
/// the menu bar item, the chord the user picked minutes ago, whether the mic is
/// live — and each is emitted only when it genuinely exists.
///
/// Escapable three ways (Got it, the close button, tapping outside) and never
/// shown again once dismissed.
struct TryAskingPopupView: View {
  let suggestions: [String]
  let onAsk: (String) -> Void
  let onDismiss: () -> Void

  /// Three keeps the card readable at its minimum height; the rest stay on the
  /// dashboard banner and the home ask bar.
  private static let visibleSuggestionLimit = 3

  /// Read live rather than persisted: by the time this renders, `ShortcutSettings`
  /// and the microphone TCC state are the authorities on what the user can
  /// actually do, and a shortcut changed since onboarding must not be misreported.
  @MainActor
  private var cues: [SBOrientationCue] {
    var setup = SBSetupSnapshot()
    setup.canHear = AudioCaptureService.checkPermission()
    let recordingMode =
      AppState.current?.audioRecordingMode.rawValue
      ?? AssistantSettings.shared.audioRecordingMode.rawValue
    setup.listening = SBSetupSnapshot.Listening(
      audioRecordingModeRaw: recordingMode,
      canHear: setup.canHear)
    return SBPostOnboardingGuidance.orientationCues(
      openShortcutTokens: ShortcutSettings.shared.askOmiShortcut.displayTokens,
      talkShortcutTokens: ShortcutSettings.shared.pttShortcut.displayTokens,
      setup: setup)
  }

  var body: some View {
    GeometryReader { proxy in
      let popupWidth = min(max(proxy.size.width - 72, 560), 660)
      let popupHeight = min(max(proxy.size.height - 80, 360), 520)

      ZStack {
        // The dim belongs to the shell's surface, not to the window: this popup is an overlay on the
        // whole main window, which is transparent and much larger than the panels inside it, so a
        // full-bleed dim here was a dark rectangle stamped on the desktop. See `ShellModalScrim`.
        ShellModalScrim(onTap: onDismiss)

        VStack {
          popupContent
        }
        .frame(width: popupWidth, height: popupHeight)
        .padding(OmiSpacing.xxl)
        // The card paints no ground of its own: the glass owns the material, the 22 pt corner, the
        // faint edge and the one ambient shadow. It used to draw all four itself — an opaque near-
        // black fill, a 28 pt corner, a white stroke and a second shadow — which on a light-pinned
        // page is a dark slab with a bright outline where a pane of glass should be.
        .inkGlassPanel()
        .overlay(alignment: .topTrailing) {
          Button(action: onDismiss) {
            Image(systemName: "xmark")
              .font(.system(size: 12, weight: .bold))
              .foregroundColor(Ink.secondary)
              .frame(width: 28, height: 28)
              .background(
                Circle()
                  .fill(Ink.rowFill)
              )
          }
          .buttonStyle(.plain)
          .padding(OmiSpacing.lg)
        }
      }
    }
  }

  private var popupContent: some View {
    ScrollView(.vertical, showsIndicators: false) {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "checkmark.circle.fill")
            .font(.system(size: 11, weight: .semibold))
          Text("You're set up")
            .font(.system(size: 12, weight: .semibold))
        }
        .foregroundColor(Ink.secondary)
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.xs)
        .background(
          Capsule()
            .fill(Ink.rowFill)
        )

        // The system's display face, not a system serif: `InkType` carries the tracking and the
        // leading with the size, and a 32 pt run assembled by hand loses both.
        Text("Here's how to reach me.")
          .inkStyle(.stepHeadline, color: Ink.primary)

        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          ForEach(cues) { cue in
            orientationRow(cue)
          }
        }

        if !suggestions.isEmpty {
          Text("TRY ASKING")
            .font(.system(size: 11, weight: .semibold))
            .tracking(0.8)
            .foregroundColor(Ink.secondary)
            .padding(.top, OmiSpacing.xs)

          VStack(spacing: OmiSpacing.sm) {
            ForEach(Array(suggestions.prefix(Self.visibleSuggestionLimit)), id: \.self) { suggestion in
              suggestionRow(suggestion)
            }
          }
        }

        HStack {
          Spacer(minLength: 0)
          Button(action: onDismiss) {
            Text("Got it")
              .font(.system(size: 13, weight: .semibold))
              .foregroundColor(Ink.primary)
              .padding(.horizontal, OmiSpacing.lg)
              .padding(.vertical, OmiSpacing.sm)
              .background(
                Capsule()
                  .fill(Ink.rowFill)
              )
              .overlay(
                Capsule()
                  .stroke(Ink.separator, lineWidth: 1)
              )
          }
          .buttonStyle(.plain)
        }
        .padding(.top, OmiSpacing.xs)
      }
      .frame(maxWidth: .infinity, alignment: .topLeading)
      .padding(OmiSpacing.md)
    }
  }

  /// One "where I am / how you reach me" line. The chord chips render the user's
  /// real shortcut tokens, so a user who picked ⌘↩ is never told to press ⌘O.
  private func orientationRow(_ cue: SBOrientationCue) -> some View {
    HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.md) {
      Image(systemName: cue.symbol)
        .font(.system(size: 13, weight: .semibold))
        .foregroundColor(Ink.secondary)
        .frame(width: 18, alignment: .center)

      Text(cue.title)
        .font(.system(size: 14))
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .multilineTextAlignment(.leading)

      Spacer(minLength: OmiSpacing.sm)

      if !cue.keys.isEmpty {
        HStack(spacing: 4) {
          ForEach(Array(cue.keys.enumerated()), id: \.offset) { _, key in
            Text(key)
              .font(.system(size: 12, weight: .semibold, design: .rounded))
              .foregroundColor(Ink.primary)
              .padding(.horizontal, 7)
              .padding(.vertical, 3)
              .background(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                  .fill(Ink.rowFill)
              )
              .overlay(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                  .stroke(Ink.separator, lineWidth: 1)
              )
          }
        }
      }
    }
  }

  private func suggestionRow(_ suggestion: String) -> some View {
    Button {
      onAsk(suggestion)
    } label: {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "sparkles")
          .font(.system(size: 12, weight: .semibold))
          .foregroundColor(Ink.secondary)

        Text(suggestion)
          .font(.system(size: 15, weight: .medium))
          .multilineTextAlignment(.leading)

        Spacer(minLength: 0)

        Image(systemName: "arrow.up.right")
          .font(.system(size: 11, weight: .bold))
          .foregroundColor(Ink.secondary)
      }
      .contentShape(Rectangle())
      .foregroundColor(Ink.primary)
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
          .fill(Ink.rowFill.opacity(0.82))
      )
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
          .stroke(Ink.separator, lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
  }
}

struct PromptSuggestionBanner: View {
  let suggestions: [String]
  let onOpen: () -> Void
  let onAsk: (String) -> Void
  let onDismiss: () -> Void

  // Two rungs and two washes, straight off `Ink`. The surface, its gradient partner and the stroke
  // are gone with the hand-rolled ground above; what is left is type and fills, and every one of them
  // is an alpha on `labelColor` rather than a hex, so it composites correctly on the panel instead of
  // assuming a near-black page under it.
  private let bannerPrimaryText = Ink.primary
  private let bannerSecondaryText = Ink.secondary
  private let bannerChipFill = Ink.rowFill
  private let bannerChipStroke = Ink.separator

  /// Chip-length labels for the questions this product actually emits. Anything
  /// unmapped falls through verbatim — the chip clips with `lineLimit(1)` rather
  /// than showing a truncated guess.
  private static let compactLabels: [String: String] = [
    "What should I focus on today to achieve my goals?": "What should I focus on today?",
    "What email follow-ups matter most today?": "Which email follow-ups matter?",
    "Where can I find focus time this week?": "Where can I find focus time?",
    "Break my goal into the next 3 steps.": "Next 3 steps for my goal",
    "What on my screen matters most right now?": "What matters on my screen?",
    "What's the highest-leverage thing I can do next?": "What should I do next?",
    "What am I working on, based on my files?": "What am I working on?",
    "What did I commit to this week?": "What did I commit to?",
    "Who should I follow up with today?": "Who should I follow up with?",
  ]

  private func compactLabel(for suggestion: String) -> String {
    Self.compactLabels[suggestion] ?? suggestion
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Button(action: onOpen) {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          Text("Next step -> Ask omi")
            .inkStyle(.firstTitle, color: bannerPrimaryText)

          Text(
            "Use your real screen and your existing context to get value quickly. Tap to open a few suggested questions."
          )
          .font(.system(size: 14, weight: .medium))
          .foregroundColor(bannerSecondaryText)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      .buttonStyle(.plain)

      HStack(spacing: OmiSpacing.sm) {
        ForEach(Array(suggestions.prefix(3)), id: \.self) { suggestion in
          Button {
            onAsk(suggestion)
          } label: {
            Text(compactLabel(for: suggestion))
              .font(.system(size: 12, weight: .semibold))
              .foregroundColor(bannerPrimaryText)
              .lineLimit(1)
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.sm)
              .background(
                Capsule()
                  .fill(bannerChipFill)
              )
              .overlay(
                Capsule()
                  .stroke(bannerChipStroke, lineWidth: 1)
              )
          }
          .buttonStyle(.plain)
        }
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.horizontal, OmiSpacing.xl)
    .padding(.vertical, OmiSpacing.lg)
    // One glass, one corner, one shadow — see the popup above. The gradient fill, the second
    // gradient "sheen" overlay and the blurred corner bloom were three grounds stacked on one
    // another; `InkGlass` draws the specular top edge itself, once, at the alpha it was measured at.
    .inkGlassPanel()
    .overlay(alignment: .topTrailing) {
      ZStack(alignment: .topTrailing) {
        Button(action: onDismiss) {
          Image(systemName: "xmark")
            .font(.system(size: 11, weight: .bold))
            .foregroundColor(bannerSecondaryText)
            .frame(width: 24, height: 24)
            .background(
              Circle()
                .fill(Ink.rowFill)
            )
        }
        .buttonStyle(.plain)
        .padding(OmiSpacing.md)
      }
    }
  }
}
