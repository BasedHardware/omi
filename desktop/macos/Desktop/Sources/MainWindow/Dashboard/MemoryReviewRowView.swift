import OmiTheme
import SwiftUI

/// "Things I learned today" — the memories the day produced, each one correctable.
///
/// The section is the whole point of the contract behind it. A summary that only *tells* the owner
/// what Omi thinks it learned is a claim they cannot answer; three rows with ✓ / ✗ / Fix make the
/// claim answerable, and every answer is a real mutation on the memory it names. Rejection is not
/// cosmetic — it feeds bounded negative feedback back into extraction — so the copy under a dropped
/// row is true rather than reassuring.
///
/// Empty renders nothing at all: no header, no frame, no "nothing yet". A quiet day is not a
/// broken card.
struct MemoryReviewSection: View {
  @StateObject private var store: MemoryReviewCardStore
  @State private var reportedImpression = false

  private let title: String

  init(
    items: [MemoryReviewItem],
    source: MemoryReviewSource,
    title: String = "Things I learned today",
    store: MemoryReviewCardStore? = nil
  ) {
    self.title = title
    self._store = StateObject(
      wrappedValue: store ?? MemoryReviewCardStore(items: items, source: source))
  }

  /// Up to three. More than that is a queue, and a queue at the top of Chat is a chore.
  /// `nonisolated` so the card's pure row projection can bound itself by the same number the
  /// section renders, rather than the two drifting apart.
  nonisolated static let maxRows = 3

  private var rows: [MemoryReviewItem] { Array(store.items.prefix(Self.maxRows)) }

  var body: some View {
    Group {
      if !rows.isEmpty {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          Text(title)
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(HomePalette.muted)
            .tracking(0.6)
          ForEach(rows) { item in
            MemoryReviewRowView(item: item, model: store.row(item.memoryID)) { event in
              store.send(event, to: item)
            }
          }
        }
        .accessibilityIdentifier("memory-review-section")
        .task {
          // Non-production only, and a no-op on a shipped bundle: this is how the automation
          // bridge reaches the rows a real card bound, so `memory-review.yaml` can assert them
          // and vote through the same `store.send` the ✓ / ✗ buttons below call.
          MemoryReviewCardRegistry.register(store)
          reportImpression()
          await store.loadLiveStateIfNeeded()
        }
        .onDisappear { MemoryReviewCardRegistry.unregister(store) }
      }
    }
  }

  private func reportImpression() {
    guard !reportedImpression else { return }
    reportedImpression = true
    AnalyticsManager.shared.trackMemoryReviewCardShown(source: store.source, itemCount: rows.count)
  }
}

/// One memory, one verdict.
///
/// The row never owns the verdict: it draws `model.displayed`, which is the memory's own state with
/// an optimistic override held only while a request is in flight. A failed request clears the
/// override and says so inline; nothing is written to defaults, and nothing about the vote lives in
/// the chat row.
struct MemoryReviewRowView: View {
  let item: MemoryReviewItem
  let model: MemoryReviewRowModel
  let send: (MemoryReviewEvent) -> Void

  @FocusState private var isRowFocused: Bool
  @FocusState private var isEditorFocused: Bool
  @State private var draft: String = ""

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      if model.isEditing {
        editor
      } else {
        HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
          VStack(alignment: .leading, spacing: 1) {
            Text(item.content)
              .scaledFont(size: OmiType.body)
              .foregroundStyle(HomePalette.ink)
              .fixedSize(horizontal: false, vertical: true)
            if let category = item.categoryLabel {
              Text(category)
                .scaledFont(size: OmiType.micro, weight: .medium)
                .foregroundStyle(HomePalette.muted)
                .tracking(0.4)
            }
          }
          Spacer(minLength: OmiSpacing.sm)
          if !model.isSettled {
            controls
          }
        }
      }

      if let status = model.statusText {
        Text(status)
          .scaledFont(size: OmiType.micro)
          .foregroundStyle(HomePalette.muted)
          .accessibilityIdentifier("memory-review-status")
      }

      if let error = model.errorMessage {
        Text(error)
          .scaledFont(size: OmiType.micro)
          .foregroundStyle(Ink.errorRed)
          .accessibilityIdentifier("memory-review-error")
      }
    }
    .padding(.vertical, OmiSpacing.xxs)
    // A dropped row fades where it stands. Removing it would reflow every row below the one the
    // reader just clicked, so it stays until the card is next refreshed.
    .opacity(model.isFaded ? 0.45 : 1)
    .contentShape(.rect)
    .focusable(!model.isEditing)
    .focused($isRowFocused)
    .onKeyPress(.return) { keyAction(.accept) }
    .onKeyPress(.delete) { keyAction(.reject) }
    .onKeyPress(KeyEquivalent("e")) { keyAction(.beginEdit(prefill: item.content)) }
    // Voice hook (not wired in this PR): hold ⌥ over a focused row to correct it by speaking would
    // attach here, sending the transcript through `.beginEdit` + `.saveEdit` like the inline editor.
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("memory-review-row")
  }

  private var controls: some View {
    HStack(spacing: OmiSpacing.xs) {
      control("checkmark", label: "Right", identifier: "memory-review-accept") {
        send(.accept)
      }
      control("xmark", label: "Wrong", identifier: "memory-review-reject") {
        send(.reject)
      }
      control("pencil", label: "Fix", identifier: "memory-review-edit") {
        send(.beginEdit(prefill: item.content))
      }
    }
    .disabled(model.isBusy)
  }

  private func control(
    _ symbol: String, label: String, identifier: String, action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      HStack(spacing: 3) {
        Image(systemName: symbol)
          .scaledFont(size: OmiType.micro, weight: .semibold)
        Text(label)
          .scaledFont(size: OmiType.micro, weight: .medium)
      }
      .foregroundStyle(HomePalette.secondary)
      .padding(.horizontal, OmiSpacing.xs + 1)
      .padding(.vertical, 2)
      .background(Capsule().fill(Ink.rowFill))
      .overlay(Capsule().stroke(Ink.separator, lineWidth: 1))
    }
    .buttonStyle(.plain)
    .accessibilityLabel(label)
    .accessibilityIdentifier(identifier)
  }

  /// Single line by design: the reader is correcting one fact, not drafting. Enter saves, Esc
  /// cancels and leaves the memory exactly as it was.
  private var editor: some View {
    HStack(spacing: OmiSpacing.xs) {
      TextField("", text: $draft)
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body)
        .foregroundStyle(HomePalette.ink)
        .focused($isEditorFocused)
        .lineLimit(1)
        .onSubmit { commitEdit() }
        .onChange(of: draft) { _, newValue in send(.draftChanged(newValue)) }
        .onKeyPress(.escape) {
          send(.cancelEdit)
          return .handled
        }
        .accessibilityIdentifier("memory-review-editor")
      Button("Save") { commitEdit() }
        .buttonStyle(.plain)
        .scaledFont(size: OmiType.micro, weight: .semibold)
        .foregroundStyle(HomePalette.secondary)
        .accessibilityIdentifier("memory-review-save")
    }
    .padding(.horizontal, OmiSpacing.xs)
    .padding(.vertical, OmiSpacing.xxs)
    .background(RoundedRectangle(cornerRadius: 7, style: .continuous).fill(Ink.rowFill))
    .overlay(
      RoundedRectangle(cornerRadius: 7, style: .continuous).stroke(Ink.separator, lineWidth: 1)
    )
    .onAppear {
      draft = model.draft ?? item.content
      isEditorFocused = true
    }
  }

  private func commitEdit() {
    send(.draftChanged(draft))
    send(.saveEdit)
  }

  private func keyAction(_ event: MemoryReviewEvent) -> KeyPress.Result {
    guard !model.isSettled, !model.isEditing, !model.isBusy else { return .ignored }
    send(event)
    return .handled
  }
}
