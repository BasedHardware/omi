import OmiTheme
import SwiftUI

/// The card that replaces the composer while an agent is waiting on the user.
///
/// It occupies the composer's own shell rather than sitting above it, so the
/// input row is unmounted for as long as a question is open. That is why the
/// stop control lives here: an elicitation only ever appears mid-run, and
/// removing the input row removes the Stop button that would otherwise be the
/// user's way out of a run they no longer want.
struct ChatElicitationPanel: View {
  let elicitation: PendingElicitation
  let waitingCount: Int
  let onAnswer: (ElicitationAnswer) -> Void
  let onStopRun: () -> Void

  @Environment(\.fontScale) private var fontScale
  @State private var freeText: String = ""
  @FocusState private var freeTextFocused: Bool

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
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .accessibilityElement(children: .contain)
    .accessibilityLabel("\(elicitation.title). \(elicitation.prompt)")
  }

  private var header: some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: elicitation.mode == .permission ? "exclamationmark.shield" : "questionmark.circle")
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

      // Recovers the Stop affordance the unmounted input row would have shown.
      Button(action: onStopRun) {
        Image(systemName: "stop.circle")
          .scaledFont(size: OmiType.heading)
          .foregroundColor(OmiColors.textTertiary)
      }
      .buttonStyle(.plain)
      .help("Stop this run")
      .accessibilityLabel("Stop this run")
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

  /// Permissions read as a decision row; questions read as a list to pick from.
  @ViewBuilder
  private var options: some View {
    if elicitation.mode == .permission {
      HStack(spacing: OmiSpacing.sm) {
        ForEach(elicitation.options) { option in
          Button {
            onAnswer(.option(option.id))
          } label: {
            Text(option.label)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(option.isRejection ? OmiColors.textSecondary : OmiColors.textPrimary)
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.xs)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                  .fill(
                    option.isRejection
                      ? OmiColors.backgroundTertiary
                      : OmiColors.backgroundQuaternary.opacity(0.9))
              )
              .overlay {
                RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                  .stroke(OmiColors.border.opacity(option.isPermanent ? 0.4 : 0.16), lineWidth: 1)
              }
          }
          .buttonStyle(.plain)
          .help(option.isPermanent ? "Remembered for future requests" : option.label)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    } else if !elicitation.options.isEmpty {
      VStack(spacing: 1) {
        ForEach(elicitation.options) { option in
          Button {
            onAnswer(.option(option.id))
          } label: {
            Text(option.label)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textPrimary)
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.horizontal, OmiSpacing.sm)
              .padding(.vertical, OmiSpacing.xs)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
        }
      }
      .background(OmiColors.backgroundTertiary)
      .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous))
      // A long enum stays inside the card instead of pushing the transcript
      // off screen.
      .frame(maxHeight: 168)
      .fixedSize(horizontal: false, vertical: true)
    }
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

  private func sendFreeText() {
    let trimmed = freeText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    onAnswer(.text(trimmed))
  }
}
