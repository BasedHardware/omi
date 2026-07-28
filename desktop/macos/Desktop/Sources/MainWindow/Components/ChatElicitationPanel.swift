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
  @State private var windowHeight: CGFloat?
  @FocusState private var freeTextFocused: Bool

  private var staged: ElicitationAnswer? { elicitations.staged[elicitation.id] }

  /// Every option currently chosen. A single-select question holds at most one.
  private var stagedOptionIDs: [String] { staged?.optionIDs ?? [] }

  /// Whether the user's own words are part of the answer right now.
  private var customAnswerChosen: Bool {
    !(staged?.text?.isEmpty ?? true)
  }

  /// The custom answer sits after the listed options, so its number continues
  /// the same sequence and the key that picks it is the one shown on it.
  private var customAnswerNumber: Int? {
    let next = elicitation.options.count + 1
    return next <= 9 ? next : nil
  }

  private func isChosen(_ option: ElicitationOption) -> Bool {
    stagedOptionIDs.contains(option.id)
  }

  /// Numbers are what make an option list scannable and directly reachable:
  /// row 3 is "3", not "the one under the second one".
  private func optionNumber(_ option: ElicitationOption) -> Int? {
    guard let index = elicitation.options.firstIndex(where: { $0.id == option.id }) else { return nil }
    return index < 9 ? index + 1 : nil
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
    .omiAnimation(SBMotion.standard, value: stagedOptionIDs)
    .onAppear { restoreStagedText() }
    .onChange(of: elicitation.id) { _, _ in
      // Hover belongs to the row the pointer was over, not to the question that
      // replaced it.
      hoveredOptionID = nil
      restoreStagedText()
    }
    .accessibilityElement(children: .contain)
    .accessibilityLabel("\(elicitation.title). \(elicitation.prompt)")
    // Measured rather than assumed: the cap is a share of the window the card
    // sits in, and that window is resizable.
    .background(
      GeometryReader { proxy in
        Color.clear
          .onAppear { windowHeight = proxy.size.height }
          .onChange(of: proxy.size.height) { _, height in windowHeight = height }
      }
      .ignoresSafeArea()
    )
    .background(keyboardShortcuts)
  }

  /// Keyboard reach for everything the pointer can do.
  ///
  /// Left/right move between questions and 1-9 pick an option, but only while
  /// the free-text field is not focused — inside a text field those keys belong
  /// to the caret, and stealing them would make typing an answer impossible.
  @ViewBuilder
  private var keyboardShortcuts: some View {
    if !freeTextFocused {
      ZStack {
        Button("") { elicitations.focusPrevious() }
          .keyboardShortcut(.leftArrow, modifiers: [])
          .disabled(elicitations.waitingCount < 2)
        Button("") { elicitations.focusNext() }
          .keyboardShortcut(.rightArrow, modifiers: [])
          .disabled(elicitations.waitingCount < 2)
        ForEach(Array(elicitation.options.indices.prefix(9)), id: \.self) { index in
          Button("") { selectOption(number: index + 1) }
            .keyboardShortcut(KeyEquivalent(Character("\(index + 1)")), modifiers: [])
        }
      }
      .opacity(0)
      .accessibilityHidden(true)
      .frame(width: 0, height: 0)
    }
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

      countdown
    }
  }

  /// How long before the card answers for the user.
  ///
  /// Shown so the wait is never a surprise: a card that closes itself without
  /// warning reads as a bug. It goes quiet until the last stretch, because a
  /// clock ticking through the whole interaction is pressure the user has not
  /// earned, and turns urgent only when it is nearly out.
  @ViewBuilder
  private var countdown: some View {
    if let seconds = elicitations.secondsRemaining {
      let urgent = seconds <= 30
      Text(formattedRemaining(seconds))
        .scaledFont(size: OmiType.micro, weight: urgent ? .semibold : .regular)
        .monospacedDigit()
        .foregroundColor(urgent ? OmiColors.textPrimary : OmiColors.textQuaternary)
        .padding(.horizontal, OmiSpacing.xs)
        .padding(.vertical, OmiSpacing.hairline)
        .background(
          Capsule().fill(
            urgent ? OmiColors.backgroundQuaternary : OmiColors.backgroundQuaternary.opacity(0.5))
        )
        .help("Answers on their own in \(formattedRemaining(seconds)); anything you do resets it")
        .accessibilityLabel("\(seconds) seconds before this answers on its own")
    }
  }

  private func formattedRemaining(_ seconds: Int) -> String {
    String(format: "%d:%02d", seconds / 60, seconds % 60)
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
        VStack(spacing: OmiSpacing.xs) {
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
      if isChosen(option) {
        Image(systemName: "checkmark").scaledFont(size: OmiType.micro, weight: .bold)
      }
      Text(option.label).scaledFont(size: OmiType.caption, weight: .medium)
      if isRecommended(option) && !isChosen(option) {
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
        .stroke(optionStroke(option), lineWidth: isChosen(option) ? 1.5 : 1)
    }
  }

  private func optionRowLabel(_ option: ElicitationOption) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      // The number is the option's address: it labels the row and is the key
      // that picks it, so the two can never disagree.
      if let number = optionNumber(option) {
        Text("\(number)")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .monospacedDigit()
          .foregroundColor(isChosen(option) ? OmiColors.textPrimary : OmiColors.textTertiary)
          .frame(width: numberColumnWidth, alignment: .center)
          .accessibilityHidden(true)
      }

      Text(option.label)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textPrimary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)

      // A pick-many question shows a box that can hold several marks; a
      // pick-one shows the single answer it is committing to.
      if elicitation.allowsMultiple {
        Image(systemName: isChosen(option) ? "checkmark.square.fill" : "square")
          .scaledFont(size: OmiType.body)
          .foregroundColor(isChosen(option) ? OmiColors.accent : OmiColors.textQuaternary)
      } else if isChosen(option) {
        Image(systemName: "checkmark")
          .scaledFont(size: OmiType.caption, weight: .bold)
          .foregroundColor(OmiColors.accent)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.md)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
        .fill(optionFill(option))
    )
    .overlay {
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
        .stroke(optionStroke(option), lineWidth: isChosen(option) ? 1.5 : 1)
    }
    .contentShape(Rectangle())
    .accessibilityElement(children: .combine)
    .accessibilityLabel(optionNumber(option).map { "Option \($0), \(option.label)" } ?? option.label)
    .accessibilityAddTraits(isChosen(option) ? [.isButton, .isSelected] : .isButton)
  }

  /// Wide enough for a two-digit number so the labels stay on one left edge.
  private var numberColumnWidth: CGFloat { round(OmiType.body * fontScale) }

  private func optionFill(_ option: ElicitationOption) -> Color {
    if isChosen(option) { return OmiColors.backgroundQuaternary }
    if hoveredOptionID == option.id { return OmiColors.backgroundTertiary }
    return OmiColors.backgroundTertiary.opacity(0.55)
  }

  private func optionStroke(_ option: ElicitationOption) -> Color {
    if isChosen(option) { return OmiColors.accent.opacity(0.55) }
    if hoveredOptionID == option.id { return OmiColors.border.opacity(0.28) }
    return OmiColors.border.opacity(option.isPermanent ? 0.4 : 0.12)
  }

  /// The user's own words, presented as one more option rather than a stray
  /// field below them.
  ///
  /// It carries the next number in the sequence, and shows the same chosen mark
  /// the listed options do, so "what I typed" reads as an answer among the
  /// others instead of a separate control competing with them.
  private var freeTextField: some View {
    HStack(spacing: OmiSpacing.sm) {
      if let number = customAnswerNumber {
        Text("\(number)")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .monospacedDigit()
          .foregroundColor(customAnswerChosen ? OmiColors.textPrimary : OmiColors.textTertiary)
          .frame(width: numberColumnWidth, alignment: .center)
          .accessibilityHidden(true)
      }

      TextField(
        elicitation.options.isEmpty ? "Type your answer\u{2026}" : "Or type your own answer\u{2026}",
        text: $freeText
      )
      .textFieldStyle(.plain)
      .scaledFont(size: OmiType.body)
      .foregroundColor(OmiColors.textPrimary)
      .focused($freeTextFocused)
      .onChange(of: freeText) { _, value in
        // Typing is the user working on the answer, even before the field has
        // anything worth staging.
        elicitations.noteInteraction()
        stageFreeText(value)
      }
      .onSubmit(advance)

      if elicitation.allowsMultiple {
        Image(systemName: customAnswerChosen ? "checkmark.square.fill" : "square")
          .scaledFont(size: OmiType.body)
          .foregroundColor(customAnswerChosen ? OmiColors.accent : OmiColors.textQuaternary)
      } else if customAnswerChosen {
        Image(systemName: "checkmark")
          .scaledFont(size: OmiType.caption, weight: .bold)
          .foregroundColor(OmiColors.accent)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
        .fill(customAnswerChosen ? OmiColors.backgroundQuaternary : OmiColors.backgroundTertiary.opacity(0.55))
    )
    .overlay {
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
        .stroke(
          customAnswerChosen ? OmiColors.accent.opacity(0.55) : OmiColors.border.opacity(0.12),
          lineWidth: customAnswerChosen ? 1.5 : 1)
    }
    .accessibilityLabel(
      customAnswerNumber.map { "Option \($0), type your own answer" } ?? "Type your own answer"
    )
    .accessibilityAddTraits(customAnswerChosen ? .isSelected : [])
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
    round(OmiType.body * fontScale) + OmiSpacing.md * 2
  }

  /// Height for the option list: its natural size until it would crowd the
  /// transcript, then a scrolling cap.
  ///
  /// The row height is an estimate, and it degrades safely in both directions
  /// because the list scrolls: too small and the last row scrolls into reach,
  /// too large and the card carries a little slack. The previous fixed cap
  /// clipped instead, which put options permanently out of reach.
  private var optionListMaxHeight: CGFloat {
    let stride = optionRowHeight + OmiSpacing.xs
    let natural = CGFloat(elicitation.options.count) * stride - OmiSpacing.xs
    guard natural > halfTheWindow else { return natural }
    // Snap the cap to whole rows. Cutting one in half looks like a rendering
    // fault rather than a list that scrolls, and a row sliced at the boundary
    // gives the eye no reason to try scrolling it.
    let wholeRows = max(1, floor((halfTheWindow + OmiSpacing.xs) / stride))
    return wholeRows * stride - OmiSpacing.xs
  }

  /// Half the window, and never more.
  ///
  /// The card lives in the composer at the bottom, so every point it takes is a
  /// point of transcript the user loses. Past half the window the question
  /// stops being a control and becomes the screen, so the list scrolls from
  /// there. Falls back to a fixed cap when there is no window to measure.
  private var halfTheWindow: CGFloat {
    let height = windowHeight ?? 0
    return height > 0 ? height * 0.5 : 320
  }

  /// Choose an option.
  ///
  /// A pick-many question toggles and stays put, because the user is still
  /// building one answer. A pick-one question is finished the moment it is
  /// answered, so it moves to the next question the way Next would — but never
  /// sends, because sending the batch stays a deliberate act.
  private func stage(_ option: ElicitationOption) {
    if elicitation.allowsMultiple {
      var chosen = stagedOptionIDs
      if let existing = chosen.firstIndex(of: option.id) {
        chosen.remove(at: existing)
      } else {
        chosen.append(option.id)
      }
      // Keep card order so the answer reads the way the question was asked.
      let ordered = elicitation.options.map(\.id).filter { chosen.contains($0) }
      // Keep whatever the user typed: on a pick-many question the options and
      // their own words are parts of one answer.
      let typed = freeText.trimmingCharacters(in: .whitespacesAndNewlines)
      let answer = ElicitationAnswer.answer(optionIDs: ordered, text: typed.isEmpty ? nil : typed)
      if answer.isEmpty {
        elicitations.clearStaged(for: elicitation)
      } else {
        elicitations.stage(answer, for: elicitation)
      }
      return
    }

    // Pick-one: the option replaces whatever was typed, the same way it
    // replaces another option.
    elicitations.stage(.answer(optionIDs: [option.id], text: nil), for: elicitation)
    freeText = ""
    if !isLastQuestion { elicitations.focusNext() }
  }

  /// Pick an option by its number. Bound to 1-9 while the user is not typing.
  private func selectOption(number: Int) {
    guard !freeTextFocused else { return }
    let index = number - 1
    if elicitation.options.indices.contains(index) {
      stage(elicitation.options[index])
      return
    }
    // The number past the last option is the custom answer; choosing it means
    // putting the caret where the words go.
    if elicitation.allowsFreeText && number == customAnswerNumber {
      freeTextFocused = true
      elicitations.noteInteraction()
    }
  }

  /// Typing is choosing the custom answer.
  ///
  /// On a pick-many question it joins whatever options are already chosen, so
  /// "these three, plus this" is one answer. On a pick-one question it is the
  /// answer, and takes the place of any option that was chosen — the same way
  /// clicking a second option would.
  private func stageFreeText(_ value: String) {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    let keptOptions = elicitation.allowsMultiple ? stagedOptionIDs : []
    if trimmed.isEmpty {
      if keptOptions.isEmpty {
        elicitations.clearStaged(for: elicitation)
      } else {
        elicitations.stage(.answer(optionIDs: keptOptions, text: nil), for: elicitation)
      }
      return
    }
    elicitations.stage(.answer(optionIDs: keptOptions, text: trimmed), for: elicitation)
  }

  /// Typed answers survive moving between questions, so the field is refilled
  /// from what was staged rather than cleared.
  private func restoreStagedText() {
    freeText = staged?.text ?? ""
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
