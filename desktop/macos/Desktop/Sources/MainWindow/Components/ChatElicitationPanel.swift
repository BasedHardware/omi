import OmiTheme
import SwiftUI

/// The card that replaces the composer while an agent is waiting on the user.
///
/// It occupies the composer's own shell rather than sitting above it, so the
/// input row is unmounted for as long as a question is open. Escape dismisses
/// the question rather than the run: the agent is told the user declined to
/// choose and carries on, which is also why there is no stop control here —
/// declining one question should not end everything else in flight.
struct ChatElicitationPanel: View {
  let elicitation: PendingElicitation
  let waitingCount: Int
  /// Questions queued behind this one, oldest first, so the user can see what
  /// answering leads to instead of being surprised by the next card.
  var upcoming: [PendingElicitation] = []
  let onAnswer: (ElicitationAnswer) -> Void

  @Environment(\.fontScale) private var fontScale
  @State private var freeText: String = ""
  /// Held briefly after a click so the choice is visibly acknowledged before
  /// the card collapses; a card that vanishes on click leaves the user unsure
  /// which row they actually hit.
  @State private var selectedOptionID: String?
  @State private var hoveredOptionID: String?
  @FocusState private var freeTextFocused: Bool

  /// How long the tick stays on screen before the card collapses.
  private static let selectionAcknowledgementSeconds: Double = 0.22

  private var canSendFreeText: Bool {
    !freeText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      header
      prompt
      if let subject = elicitation.subject { subjectBlock(subject) }
      if let context = elicitation.context, !context.isEmpty { contextLine(context) }
      options
      if elicitation.allowsFreeText { freeTextField }
      if !upcoming.isEmpty { upcomingQueue }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .background {
      // Escape works without the card holding focus, so a user who has clicked
      // into the transcript can still dismiss the question.
      Button("", action: cancel)
        .keyboardShortcut(.cancelAction)
        .opacity(0)
        .accessibilityHidden(true)
    }
    .accessibilityElement(children: .contain)
    .accessibilityLabel("\(elicitation.title). \(elicitation.prompt)")
  }

  private var header: some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(
        systemName: elicitation.mode == .permission
          ? "exclamationmark.shield" : "questionmark.circle"
      )
      .scaledFont(size: OmiType.subheading, weight: .medium)
      .foregroundColor(OmiColors.textSecondary)

      Text(elicitation.title)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(OmiColors.textSecondary)

      if waitingCount > 1 {
        Text("1 of \(waitingCount)")
          .scaledFont(size: OmiType.micro)
          .foregroundColor(OmiColors.textTertiary)
          .padding(.horizontal, OmiSpacing.xs)
          .padding(.vertical, OmiSpacing.hairline)
          .background(OmiColors.backgroundQuaternary.opacity(0.7))
          .clipShape(Capsule())
      }

      Spacer()

      // The way out is stated rather than implied: without the input row there
      // is no other visible affordance for leaving the question alone.
      Button(action: cancel) {
        HStack(spacing: OmiSpacing.xxs) {
          Text("esc")
            .scaledFont(size: OmiType.micro, weight: .medium)
            .padding(.horizontal, OmiSpacing.xs)
            .padding(.vertical, OmiSpacing.hairline)
            .background(OmiColors.backgroundQuaternary.opacity(0.7))
            .clipShape(RoundedRectangle(cornerRadius: OmiChrome.badgeRadius, style: .continuous))
          Text("dismiss")
            .scaledFont(size: OmiType.micro)
        }
        .foregroundColor(OmiColors.textTertiary)
      }
      .buttonStyle(.plain)
      .help("Dismiss this question. The agent keeps working.")
      .accessibilityLabel("Dismiss this question")
    }
  }

  private var prompt: some View {
    Text(elicitation.prompt)
      .scaledFont(size: OmiType.body)
      .foregroundColor(OmiColors.textPrimary)
      .fixedSize(horizontal: false, vertical: true)
      .frame(maxWidth: .infinity, alignment: .leading)
  }

  /// The literal thing being approved. Monospaced and never truncated to a
  /// single line: an approval the user cannot fully read is not consent.
  private func subjectBlock(_ subject: String) -> some View {
    Text(subject)
      .font(.system(size: round(OmiType.body * fontScale), design: .monospaced))
      .foregroundColor(OmiColors.textSecondary)
      .textSelection(.enabled)
      .fixedSize(horizontal: false, vertical: true)
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(OmiColors.backgroundTertiary)
      .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous))
  }

  private func contextLine(_ context: String) -> some View {
    Text(context)
      .scaledFont(size: OmiType.caption)
      .foregroundColor(OmiColors.textTertiary)
      .lineLimit(2)
      .frame(maxWidth: .infinity, alignment: .leading)
  }

  /// Permissions read as a decision row; questions read as a list of separate
  /// rows, each its own hit target, so a five-option list is not one grey slab.
  @ViewBuilder
  private var options: some View {
    if elicitation.mode == .permission {
      HStack(spacing: OmiSpacing.sm) {
        ForEach(elicitation.options) { option in
          Button {
            select(option)
          } label: {
            HStack(spacing: OmiSpacing.xxs) {
              if selectedOptionID == option.id {
                Image(systemName: "checkmark")
                  .scaledFont(size: OmiType.micro, weight: .bold)
              }
              Text(option.label)
                .scaledFont(size: OmiType.caption, weight: .medium)
            }
            .foregroundColor(option.isRejection ? OmiColors.textSecondary : OmiColors.textPrimary)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.xs)
            .background(
              RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                .fill(optionFill(option))
            )
            .overlay {
              RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                .stroke(
                  OmiColors.border.opacity(option.isPermanent ? 0.4 : 0.16), lineWidth: 1)
            }
          }
          .buttonStyle(.plain)
          .onHover { hoveredOptionID = $0 ? option.id : nil }
          .help(option.isPermanent ? "Remembered for future requests" : option.label)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    } else if !elicitation.options.isEmpty {
      VStack(spacing: OmiSpacing.xxs) {
        ForEach(elicitation.options) { option in
          Button {
            select(option)
          } label: {
            HStack(spacing: OmiSpacing.sm) {
              Text(option.label)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textPrimary)
                .frame(maxWidth: .infinity, alignment: .leading)
              if selectedOptionID == option.id {
                Image(systemName: "checkmark")
                  .scaledFont(size: OmiType.caption, weight: .bold)
                  .foregroundColor(OmiColors.accent)
              }
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
                .fill(optionFill(option))
            )
            .overlay {
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
                .stroke(
                  OmiColors.border.opacity(hoveredOptionID == option.id ? 0.28 : 0.12),
                  lineWidth: 1)
            }
            .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .onHover { hoveredOptionID = $0 ? option.id : nil }
        }
      }
      // A long enum stays inside the card instead of pushing the transcript
      // off screen.
      .frame(maxHeight: 220)
      .fixedSize(horizontal: false, vertical: true)
    }
  }

  private func optionFill(_ option: ElicitationOption) -> Color {
    if selectedOptionID == option.id {
      return OmiColors.backgroundQuaternary
    }
    if hoveredOptionID == option.id {
      return OmiColors.backgroundTertiary.opacity(1)
    }
    return OmiColors.backgroundTertiary.opacity(0.55)
  }

  private var freeTextField: some View {
    HStack(spacing: OmiSpacing.xs) {
      TextField("Type a different answer\u{2026}", text: $freeText)
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textPrimary)
        .focused($freeTextFocused)
        .onSubmit { sendFreeText() }

      Button(action: sendFreeText) {
        Image(systemName: "arrow.up.circle.fill")
          .scaledFont(size: OmiType.heading)
          .foregroundColor(canSendFreeText ? OmiColors.accent : OmiColors.textQuaternary)
      }
      .buttonStyle(.plain)
      .disabled(!canSendFreeText)
    }
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xs)
    .background(OmiColors.backgroundTertiary)
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous))
  }

  /// What answering this one leads to. Prompts only — the queued cards render
  /// in full when their turn comes.
  private var upcomingQueue: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      Divider().overlay(OmiColors.border.opacity(0.14))
      ForEach(upcoming) { pending in
        HStack(spacing: OmiSpacing.xs) {
          Text("next")
            .scaledFont(size: OmiType.micro, weight: .medium)
            .foregroundColor(OmiColors.textQuaternary)
          Text(pending.prompt)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
        }
      }
    }
    .padding(.top, OmiSpacing.xxs)
  }

  /// Acknowledge the click, then answer. The delay is presentation only: the
  /// store still receives exactly one answer.
  private func select(_ option: ElicitationOption) {
    guard selectedOptionID == nil else { return }
    OmiMotion.withGated(.easeOut(duration: 0.12)) { selectedOptionID = option.id }
    Task {
      try? await Task.sleep(for: .seconds(Self.selectionAcknowledgementSeconds))
      onAnswer(.option(option.id))
    }
  }

  private func cancel() {
    guard selectedOptionID == nil else { return }
    onAnswer(.cancel)
  }

  private func sendFreeText() {
    let trimmed = freeText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty, selectedOptionID == nil else { return }
    onAnswer(.text(trimmed))
  }
}
