//
//  TextPromptSheet.swift — "Edit Title", as a sheet the shell draws.
//
//  Renaming used to be a system `.alert` with a text field, which dims the whole transparent window
//  onto the wallpaper (see `ShellConfirmationDialog.swift`) and gives Return no clear owner. This is
//  the one prompt-for-a-line-of-text surface: present it with `dismissableSheet`, which supplies the
//  bounded dim, click-outside and Esc.
//

import OmiTheme
import SwiftUI

struct TextPromptSheet: View {
  let title: String
  var message: String?
  var placeholder: String = ""
  @Binding var text: String
  var confirmTitle: String = "Save"
  var isBusy: Bool = false
  let onConfirm: () -> Void
  let onCancel: () -> Void

  @FocusState private var isFocused: Bool

  private var canConfirm: Bool {
    !isBusy && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack(alignment: .top) {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          Text(title)
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(Ink.primary)
          if let message {
            Text(message)
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
        Spacer(minLength: OmiSpacing.md)
        DismissButton(action: onCancel)
      }

      TextField(placeholder, text: $text)
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .background(
          RoundedRectangle(cornerRadius: PageGlass.fieldRadius, style: .continuous)
            .fill(Ink.rowFill)
        )
        .focused($isFocused)
        .onSubmit { if canConfirm { onConfirm() } }

      HStack(spacing: OmiSpacing.sm) {
        Spacer(minLength: 0)
        Button("Cancel", action: onCancel)
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
          .keyboardShortcut(.cancelAction)
        Button(confirmTitle, action: onConfirm)
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          .keyboardShortcut(.defaultAction)
          .disabled(!canConfirm)
      }
    }
    .padding(OmiSpacing.xxl)
    .frame(width: 400)
    .onAppear { isFocused = true }
  }
}
