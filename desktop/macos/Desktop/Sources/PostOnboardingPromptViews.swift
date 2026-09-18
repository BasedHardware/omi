import OmiTheme
import SwiftUI

/// The first thing a new user sees once onboarding closes.
///
/// Modelled on the "How would you like to use Flow first?" card: pick one of the things people
/// actually come to Omi for, see where it happens, press one button and be there. It used to list
/// orientation cues and generic questions, which told the user what they *could* ask and left them on
/// an empty Home to work out where. Every case here is a concrete place — a Minecraft world, a Figma
/// file, a compose box, a product page — and "Try it now" opens it with the question already in the
/// bar, so the first ask is grounded in a screen with something on it.
///
/// Escapable three ways (the close button, tapping outside, or trying a case) and never shown again
/// once dismissed.
struct TryAskingPopupView: View {
  let onTry: (FirstUseCase) -> Void
  let onDismiss: () -> Void

  @State private var selected: FirstUseCase = .game

  /// The user's real "bring me back" chord, read live from `ShortcutSettings` so a chord changed
  /// since onboarding is never misreported. Empty when none is set, in which case the line is
  /// simply not shown.
  private var openShortcutKeys: [String] {
    ShortcutSettings.shared.askOmiShortcut.displayTokens
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
  }

  var body: some View {
    GeometryReader { proxy in
      let popupWidth = min(max(proxy.size.width - 72, 640), 820)
      let popupHeight = min(max(proxy.size.height - 96, 400), 470)

      ZStack {
        // The dim belongs to the shell's surface, not to the window: this popup is an overlay on the
        // whole main window, which is transparent and much larger than the panels inside it, so a
        // full-bleed dim here was a dark rectangle stamped on the desktop. See `ShellModalScrim`.
        ShellModalScrim(onTap: onDismiss)

        HStack(alignment: .top, spacing: OmiSpacing.xxl) {
          chooser
            .frame(width: 272)
            .frame(maxHeight: .infinity, alignment: .top)

          FirstUseCasePreview(useCase: selected)
            .animation(.easeOut(duration: 0.22), value: selected)
        }
        .frame(width: popupWidth, height: popupHeight)
        .padding(OmiSpacing.xxl)
        // The card paints no ground of its own: the glass owns the material, the 22 pt corner, the
        // faint edge and the one ambient shadow.
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
          .accessibilityLabel("Close")
          .padding(OmiSpacing.lg)
        }
      }
    }
    // The automation bridge drives the same two controls a click does (`first_use_popup_select`,
    // `first_use_popup_try`), so a flow can exercise the real handlers without the cursor.
    .onReceive(NotificationCenter.default.publisher(for: .firstUsePopupSelect)) { note in
      guard let id = note.userInfo?["id"] as? String, let useCase = FirstUseCase.named(id) else { return }
      selected = useCase
    }
    .onReceive(NotificationCenter.default.publisher(for: .firstUsePopupTry)) { _ in
      log("TryAskingPopupView: try received, selected=\(selected.id)")
      onTry(selected)
    }
  }

  private var chooser: some View {
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

      Text("How would you like to use Omi first?")
        .inkStyle(.stepHeadline, color: Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      VStack(spacing: OmiSpacing.sm) {
        ForEach(FirstUseCase.all) { useCase in
          useCaseChip(useCase)
        }
      }

      Spacer(minLength: OmiSpacing.md)

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        Button {
          onTry(selected)
        } label: {
          Text("Try it now")
        }
        .buttonStyle(OmiButtonStyle(.primary))
        .accessibilityIdentifier("first_use_popup_try")

        Text("Opens \(selected.siteName).")
          .font(.system(size: 12))
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)

        if !openShortcutKeys.isEmpty {
          HStack(spacing: OmiSpacing.xs) {
            Text("Bring me back anytime with")
              .font(.system(size: 12))
              .foregroundColor(Ink.secondary)
              .lineLimit(1)
            HStack(spacing: 3) {
              ForEach(Array(openShortcutKeys.enumerated()), id: \.offset) { _, key in
                Text(key)
                  .font(.system(size: 11, weight: .semibold, design: .rounded))
                  .foregroundColor(Ink.primary)
                  .padding(.horizontal, 5)
                  .padding(.vertical, 2)
                  .background(
                    RoundedRectangle(cornerRadius: 5, style: .continuous)
                      .fill(Ink.rowFill)
                  )
                  .overlay(
                    RoundedRectangle(cornerRadius: 5, style: .continuous)
                      .stroke(Ink.separator, lineWidth: 1)
                  )
              }
            }
          }
        }
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .padding(.top, OmiSpacing.xs)
    .padding(.leading, OmiSpacing.xs)
  }

  /// One selectable case. The selected chip inverts the label ladder — `Ink.primary` fill,
  /// `Ink.surface` label — the same contrast pair the primary button uses, so "which one is chosen"
  /// reads at a glance without an accent colour.
  private func useCaseChip(_ useCase: FirstUseCase) -> some View {
    let isSelected = useCase == selected
    return Button {
      selected = useCase
    } label: {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: useCase.symbol)
          .font(.system(size: 12, weight: .semibold))
          .frame(width: 16, alignment: .center)
        Text(useCase.label)
          .font(.system(size: 14, weight: .medium))
        Spacer(minLength: 0)
      }
      .contentShape(Rectangle())
      .foregroundColor(isSelected ? Ink.surface : Ink.primary)
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
          .fill(isSelected ? Ink.primary : Ink.rowFill.opacity(0.82))
      )
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
          .stroke(isSelected ? Color.clear : Ink.separator, lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
    .accessibilityIdentifier("first_use_popup_case_\(useCase.id)")
    .accessibilityAddTraits(isSelected ? .isSelected : [])
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
