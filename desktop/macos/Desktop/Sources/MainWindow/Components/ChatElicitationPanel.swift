import OmiTheme
import SwiftUI

/// The card that replaces the composer while an agent is waiting on the user.
///
/// It occupies the composer's own shell rather than sitting above it, so the
/// input row is unmounted for as long as a question is open.
///
/// Escape cancels the item on screen, and what that means depends on the
/// protocol underneath: a cancelled question returns to the model as a tool
/// result it can act on, while a cancelled ACP permission is answered with the
/// protocol's `cancelled` outcome and ends that agent's turn. The card says
/// which, rather than describing both as harmless.
///
/// Choosing and sending are separate. A click stages the answer and nothing
/// leaves until Send, so a mis-click costs a second click rather than an
/// irreversible answer, and a queued question can be revisited before sending.
struct ChatElicitationPanel: View {
  @ObservedObject var elicitations: ElicitationStore
  let elicitation: PendingElicitation

  @Environment(\.fontScale) private var fontScale
  @State private var freeText: String = ""
  @State private var hoveredOptionID: String?
  @FocusState private var freeTextFocused: Bool

  private var staged: ElicitationAnswer? { elicitations.staged[elicitation.id] }

  private var stagedOptionID: String? {
    if case .option(let id) = staged { return id }
    return nil
  }

  /// The last question in the queue is where the batch is sent; before that
  /// the primary action moves on, so a user can walk the whole set once.
  private var isLastQuestion: Bool {
    elicitations.focusedIndex >= elicitations.waitingCount - 1
  }

  /// Always available. Skipping a question is a legitimate answer — the agent
  /// is told the user declined — so there is nothing to disable.
  private var primaryTitle: String { isLastQuestion ? "Send" : "Next" }

  /// Cancelling means different things to the two protocols underneath, so the
  /// card must not describe them the same way.
  ///
  /// A cancelled question comes back to the model as a tool result and it
  /// carries on. A cancelled ACP permission is answered with the protocol's
  /// `cancelled` outcome, which ends the agent's current turn — the deny
  /// options on the card are what refuse an action without stopping the turn.
  private var cancelHelp: String {
    elicitation.mode == .permission
      ? "Cancel this request and stop what the agent is doing. To refuse just this action and let it continue, choose a deny option above."
      : "Cancel this question. The agent keeps working."
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      header
      prompt
      if let subject = elicitation.subject { subjectBlock(subject) }
      if let context = elicitation.context, !context.isEmpty { contextLine(context) }
      options
      if elicitation.allowsFreeText { freeTextField }
      footer
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    // The card persists across a switch, so its own layout changes — a
    // different prompt length, a different option count — are what the user
    // sees move. Animating on the id keeps that a glide rather than a snap.
    .omiAnimation(SBMotion.standard, value: elicitation.id)
    .omiAnimation(SBMotion.standard, value: stagedOptionID)
    .onAppear { restoreStagedText() }
    .onChange(of: elicitation.id) { _, _ in
      // Hover belongs to the row the pointer was over, not to the question that
      // replaced it.
      hoveredOptionID = nil
      restoreStagedText()
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

      if elicitations.waitingCount > 1 { queueStepper }

      Spacer()
    }
  }

  /// Move between pending questions without answering the one on screen.
  private var queueStepper: some View {
    HStack(spacing: OmiSpacing.xxs) {
      Button {
        elicitations.focusPrevious()
      } label: {
        Image(systemName: "chevron.left").scaledFont(size: OmiType.micro, weight: .bold)
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Previous question")

      Text("\(elicitations.focusedIndex + 1) of \(elicitations.waitingCount)")
        .scaledFont(size: OmiType.micro)
        .monospacedDigit()

      Button {
        elicitations.focusNext()
      } label: {
        Image(systemName: "chevron.right").scaledFont(size: OmiType.micro, weight: .bold)
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Next question")
    }
    .foregroundColor(OmiColors.textTertiary)
    .padding(.horizontal, OmiSpacing.xs)
    .padding(.vertical, OmiSpacing.hairline)
    .background(OmiColors.backgroundQuaternary.opacity(0.7))
    .clipShape(Capsule())
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
            stage(option)
          } label: {
            optionChipLabel(option)
          }
          .buttonStyle(.plain)
          .onHover { hoveredOptionID = $0 ? option.id : nil }
          .help(optionHelp(option))
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    } else if !elicitation.options.isEmpty {
      // A long enum stays inside the card instead of pushing the transcript off
      // screen, and scrolls rather than clipping: `maxHeight` alone hid the
      // options past the cap with no way to reach them, and how many options a
      // question offers is the model's call, not a number the card can assume.
      ScrollView(.vertical) {
        VStack(spacing: OmiSpacing.xxs) {
          ForEach(elicitation.options) { option in
            Button {
              stage(option)
            } label: {
              optionRowLabel(option)
            }
            .buttonStyle(.plain)
            .onHover { hoveredOptionID = $0 ? option.id : nil }
          }
        }
      }
      .frame(maxHeight: optionListMaxHeight)
      .scrollBounceBehavior(.basedOnSize)
    }
  }

  /// The agent's own recommendation, shown but never acted on. It tells the
  /// user which answer the agent expects without choosing for them.
  private func isRecommended(_ option: ElicitationOption) -> Bool {
    elicitation.recommendedDefault == option.id
  }

  private func optionHelp(_ option: ElicitationOption) -> String {
    var parts: [String] = []
    if isRecommended(option) { parts.append("Suggested by the agent") }
    parts.append(option.isPermanent ? "Remembered for future requests" : option.label)
    return parts.joined(separator: " · ")
  }

  private func optionChipLabel(_ option: ElicitationOption) -> some View {
    HStack(spacing: OmiSpacing.xxs) {
      if stagedOptionID == option.id {
        Image(systemName: "checkmark").scaledFont(size: OmiType.micro, weight: .bold)
      }
      Text(option.label).scaledFont(size: OmiType.caption, weight: .medium)
      if isRecommended(option) && stagedOptionID != option.id {
        Text("suggested")
          .scaledFont(size: OmiType.micro, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
      }
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
        .stroke(optionStroke(option), lineWidth: stagedOptionID == option.id ? 1.5 : 1)
    }
  }

  private func optionRowLabel(_ option: ElicitationOption) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      Text(option.label)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textPrimary)
        .frame(maxWidth: .infinity, alignment: .leading)
      if stagedOptionID == option.id {
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
        .stroke(optionStroke(option), lineWidth: stagedOptionID == option.id ? 1.5 : 1)
    }
    .contentShape(Rectangle())
  }

  private func optionFill(_ option: ElicitationOption) -> Color {
    if stagedOptionID == option.id { return OmiColors.backgroundQuaternary }
    if hoveredOptionID == option.id { return OmiColors.backgroundTertiary }
    return OmiColors.backgroundTertiary.opacity(0.55)
  }

  private func optionStroke(_ option: ElicitationOption) -> Color {
    if stagedOptionID == option.id { return OmiColors.accent.opacity(0.55) }
    if hoveredOptionID == option.id { return OmiColors.border.opacity(0.28) }
    return OmiColors.border.opacity(option.isPermanent ? 0.4 : 0.12)
  }

  private var freeTextField: some View {
    TextField("Type a different answer\u{2026}", text: $freeText)
      .textFieldStyle(.plain)
      .scaledFont(size: OmiType.body)
      .foregroundColor(OmiColors.textPrimary)
      .focused($freeTextFocused)
      .onChange(of: freeText) { _, value in stageFreeText(value) }
      .onSubmit(advance)
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .background(OmiColors.backgroundTertiary)
      .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous))
  }

  /// Both actions sit under the options on the left, so the eye travels
  /// prompt -> options -> what to do about them without crossing the card.
  private var footer: some View {
    HStack(spacing: OmiSpacing.sm) {
      Button(action: advance) {
        actionLabel(
          primaryTitle, key: "\u{21A9}", enabled: true,
          fill: OmiColors.backgroundQuaternary)
      }
      .buttonStyle(.plain)
      .keyboardShortcut(.return, modifiers: [])
      .help(primaryHelp)

      Button(action: dismiss) {
        actionLabel(
          "Cancel", key: "esc", enabled: true,
          fill: OmiColors.backgroundTertiary.opacity(0.5))
      }
      .buttonStyle(.plain)
      .keyboardShortcut(.cancelAction)
      .help(cancelHelp)

      Spacer()

      if elicitations.waitingCount > 1 {
        // Send cancels whatever is still unanswered, so the count has to name
        // that rather than leave the user to discover it after the fact.
        Text(batchStatus)
          .scaledFont(size: OmiType.micro)
          .foregroundColor(unansweredCount > 0 ? OmiColors.textTertiary : OmiColors.textQuaternary)
          .accessibilityLabel(batchStatus)
      }
    }
  }

  /// Send is a batch action: it answers what was chosen and cancels the rest.
  /// Saying so on the control is the difference between a deliberate skip and
  /// silently declining questions the user never saw.
  private var primaryHelp: String {
    guard isLastQuestion else { return "Move to the next question" }
    if unansweredCount == 0 {
      return elicitations.waitingCount > 1 ? "Send every answer you have chosen" : "Send your answer"
    }
    return unansweredCount == 1
      ? "Send your answers and cancel the 1 question you did not answer"
      : "Send your answers and cancel the \(unansweredCount) questions you did not answer"
  }

  private var batchStatus: String {
    unansweredCount == 0
      ? "\(answeredCount) of \(elicitations.waitingCount) answered"
      : "\(answeredCount) of \(elicitations.waitingCount) answered · Send cancels the rest"
  }

  private func actionLabel(
    _ title: String, key: String, enabled: Bool, fill: Color
  ) -> some View {
    HStack(spacing: OmiSpacing.xs) {
      Text(title).scaledFont(size: OmiType.caption, weight: .semibold)
      Text(key)
        .scaledFont(size: OmiType.micro, weight: .medium)
        .padding(.horizontal, OmiSpacing.xs)
        .padding(.vertical, OmiSpacing.hairline)
        .background(OmiColors.backgroundQuaternary.opacity(0.7))
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.badgeRadius, style: .continuous))
    }
    .foregroundColor(enabled ? OmiColors.textPrimary : OmiColors.textQuaternary)
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.xs)
    .background(RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous).fill(fill))
  }

  private var answeredCount: Int {
    elicitations.queue.filter { elicitations.staged[$0.id] != nil }.count
  }

  private var unansweredCount: Int {
    elicitations.waitingCount - answeredCount
  }

  /// One option row: a line of body text plus its vertical padding. Scales with
  /// the user's font size so the cap stays honest at larger text.
  private var optionRowHeight: CGFloat {
    round(OmiType.body * fontScale) + OmiSpacing.sm * 2
  }

  /// Height for the option list: its natural size until it would crowd the
  /// transcript, then a scrolling cap.
  ///
  /// The row height is an estimate, and it degrades safely in both directions
  /// because the list scrolls: too small and the last row scrolls into reach,
  /// too large and the card carries a little slack. The previous fixed cap
  /// clipped instead, which put options permanently out of reach.
  private var optionListMaxHeight: CGFloat {
    let rows = CGFloat(elicitation.options.count)
    let natural = rows * optionRowHeight + max(0, rows - 1) * OmiSpacing.xxs
    return min(natural, 260)
  }

  private func stage(_ option: ElicitationOption) {
    elicitations.stage(.option(option.id), for: elicitation)
    freeText = ""
  }

  private func stageFreeText(_ value: String) {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty {
      if case .text = staged { elicitations.clearStaged(for: elicitation) }
      return
    }
    elicitations.stage(.text(trimmed), for: elicitation)
  }

  /// Typed answers survive moving between questions, so the field is refilled
  /// from what was staged rather than cleared.
  private func restoreStagedText() {
    if case .text(let text) = staged { freeText = text } else { freeText = "" }
  }

  /// Move through the batch, then send it. A question the user passes over
  /// without choosing is carried as a skip and cancelled when the batch goes.
  private func advance() {
    if isLastQuestion {
      elicitations.submitAll()
    } else {
      elicitations.focusNext()
    }
  }

  private func dismiss() {
    elicitations.answer(elicitation, with: .cancel)
  }
}
