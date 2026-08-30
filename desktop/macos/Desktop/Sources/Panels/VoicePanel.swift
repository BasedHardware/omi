import AppKit
import Foundation

/// One entry on a voice-requested panel: a value with a name, or a passage without one.
struct VoicePanelItem: Sendable, Equatable {
  let label: String
  let text: String
}

/// The voice tools' view of the shared panel.
///
/// `PanelSession` owns the card on screen and how long it lives; this is the part that
/// belongs to the voice surface — turning loosely-typed items into rows, and deciding
/// that a panel of the user's own details is about the user rather than about the tab
/// they happen to be looking at.
@MainActor
enum VoicePanel {
  /// Enough rows to answer with, few enough to read. Past this the model is writing a
  /// document, not putting something on screen to copy.
  nonisolated static let maxItems = 12
  nonisolated static let maxTextLength = 4_000
  /// Beyond one line at the card's width, a value reads as a passage and is wrapped.
  private nonisolated static let wrapThreshold = 56

  /// A panel of plain values, from `show_panel`. About the user, not the screen: it
  /// survives tab changes and leaves with the app.
  @discardableResult
  static func present(title: String, items: [VoicePanelItem]) -> Int? {
    let fields = copyFields(from: items)
    guard !fields.isEmpty else { return nil }
    PanelSession.present(
      title: title, subtitle: subtitle(for: fields), fields: fields, grain: .app,
      origin: .requested)
    return fields.count
  }

  @discardableResult
  static func reopen() -> Int? { PanelSession.reopen() }

  @discardableResult
  static func dismiss() -> Bool { PanelSession.dismiss() }

  /// Whether a model-supplied string is fit to head a panel the user reads.
  ///
  /// Measured live: a `update_panel` call arrived with `"title": "floating_chat"` — an
  /// internal surface token the model picked up from its own tool vocabulary — which
  /// would have renamed the user's card to that. A heading someone reads is prose; an
  /// identifier is not, and there is no title so urgent that it is worth showing one.
  nonisolated static func isReadableTitle(_ title: String) -> Bool {
    let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return false }
    guard !trimmed.contains(" ") else { return true }
    return !trimmed.contains("_")
  }

  /// What the panel could not take, said plainly, or nil when it took everything.
  ///
  /// The caps are silent: 20 items become 12 and a 9,000-character value becomes 4,000,
  /// with nothing in the tool result saying so. The model then tells the user their list
  /// is on screen while eight rows of it are not. Naming the loss is what lets it say
  /// "the first twelve are up" instead.
  nonisolated static func shortfall(from items: [VoicePanelItem]) -> String? {
    let usable = items.filter {
      !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    var notes: [String] = []
    if usable.count > maxItems {
      notes.append(
        "Only the first \(maxItems) of \(usable.count) items fit; the rest are not on screen.")
    }
    let clipped = usable.prefix(maxItems).filter { $0.text.count > maxTextLength }.count
    if clipped > 0 {
      notes.append(
        "\(clipped) value\(clipped == 1 ? " was" : "s were") too long and \(clipped == 1 ? "was" : "were") cut to \(maxTextLength) characters."
      )
    }
    let dropped = items.count - usable.count
    if dropped > 0 {
      notes.append(
        "\(dropped) item\(dropped == 1 ? "" : "s") had no text and \(dropped == 1 ? "was" : "were") dropped.")
    }
    return notes.isEmpty ? nil : notes.joined(separator: " ")
  }

  nonisolated static func copyFields(from items: [VoicePanelItem]) -> [CloudConnectorCopyField] {
    items
      .map {
        (
          label: $0.label.trimmingCharacters(in: .whitespacesAndNewlines),
          text: String($0.text.prefix(maxTextLength)).trimmingCharacters(in: .whitespacesAndNewlines)
        )
      }
      .filter { !$0.text.isEmpty }
      .prefix(maxItems)
      .enumerated()
      .map { index, item in
        CloudConnectorCopyField(
          // Labels repeat and may be empty; the position is the only unique id.
          id: "voice-\(index)",
          label: item.label,
          value: item.text,
          // Nothing here came from the user's credential store — masking a value the
          // model was asked to show would hide the answer behind its own label.
          masksValue: false,
          wraps: item.label.isEmpty || item.text.count > wrapThreshold
        )
      }
  }

  private static func subtitle(for fields: [CloudConnectorCopyField]) -> String {
    fields.count == 1 ? "Copy it with the button." : "Copy each with its button."
  }
}
