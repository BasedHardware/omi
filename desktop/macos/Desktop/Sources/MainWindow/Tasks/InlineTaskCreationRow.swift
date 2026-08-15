import OmiTheme
import SwiftUI

// MARK: - Inline Task Creation Row

struct InlineTaskCreationRow: View {
  @Binding var text: String
  @FocusState.Binding var isFocused: Bool
  let onCommit: (String) -> Void
  let onCancel: () -> Void
  var onCommitToday: ((String) -> Void)? = nil

  private var isTextEmpty: Bool {
    text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  /// A pinned composer rests as a plain affordance and only dresses up as an
  /// editor once the user is actually entering a task.
  private var isActive: Bool {
    isFocused || !isTextEmpty
  }

  var body: some View {
    HStack(alignment: .center, spacing: OmiSpacing.md) {
      // Circle placeholder (matches TaskRow checkbox)
      Circle()
        .stroke(Ink.hairline, lineWidth: 1.5)
        .frame(width: 20, height: 20)
        .padding(.leading, OmiSpacing.md)

      TextField("Add a task", text: $text)
        .accessibilityIdentifier("tasks-composer-field")
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.primary)
        .focused($isFocused)
        .onSubmit {
          onCommit(text)
        }
        .onKeyPress(.escape) {
          onCancel()
          return .handled
        }

      Spacer()

      if let onCommitToday, isActive {
        Button {
          onCommitToday(text)
        } label: {
          HStack(spacing: OmiSpacing.xs) {
            Image(systemName: "sun.max")
              .scaledFont(size: OmiType.caption)
            Text("Today")
              .scaledFont(size: OmiType.caption, weight: .medium)
          }
          .foregroundColor(Ink.primary)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(Capsule().fill(Ink.rowFillHover))
        }
        .buttonStyle(.plain)
        .disabled(isTextEmpty)
        .opacity(isTextEmpty ? 0.4 : 1)
        .help("Create task due today")
        .accessibilityIdentifier("tasks-composer-today")
      }
    }
    .padding(.trailing, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.xs)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
        .fill(isActive ? Ink.rowFill : Color.clear)
    )
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
        .stroke(Ink.hairline, lineWidth: 1)
    )
    .overlay(alignment: .leading) {
      // The accent bar marks an in-progress entry. A resting row is an
      // affordance, not an editor, so it stays quiet until focused.
      if isActive {
        RoundedRectangle(cornerRadius: 2)
          .fill(Ink.primary)
          .frame(width: 3)
          .padding(.vertical, OmiSpacing.xxs)
      }
    }
    .contentShape(Rectangle())
    .onTapGesture { isFocused = true }
  }
}
