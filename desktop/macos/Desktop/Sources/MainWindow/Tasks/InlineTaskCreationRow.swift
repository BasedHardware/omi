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

  var body: some View {
    HStack(alignment: .center, spacing: 0) {
      // Task rows open with a drag-handle column. The composer has no handle,
      // so it reserves the same gutter to keep one checkbox column down the list.
      RigidLeadingGutter(width: TaskRowChrome.leadingHandleWidth)
        .frame(width: TaskRowChrome.leadingHandleWidth, height: 24)
        .accessibilityHidden(true)
        .allowsHitTesting(false)

      HStack(alignment: .center, spacing: OmiSpacing.md) {
        // Geometry copied from TaskRow's checkbox — a 20pt circle centred in a
        // 24pt frame — so the composer's text sits on the task text's column.
        Circle()
          .stroke(Ink.secondary.opacity(0.5), lineWidth: 1.5)
          .frame(width: 20, height: 20)
          .frame(width: 24, height: 24)

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

        if let onCommitToday {
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
      // TaskRow puts this inset inside its handle column, so the composer does too.
      .padding(.leading, OmiSpacing.md)
    }
    .padding(.trailing, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.xs)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
        .fill(Ink.rowFill)
    )
    .contentShape(Rectangle())
    .onTapGesture { isFocused = true }
  }
}
