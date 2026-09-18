//
//  MemoryEditorSheets.swift — the two small text sheets that create and edit a memory.
//
//  A memory is one string, so both sheets are the same form twice: a title, a `TextEditor` bound to
//  the view model's draft, and Cancel/Save. They are presented from `MemoriesPage` and from the
//  memory detail panel, and own no state of their own beyond the dismiss they were handed.
//

import OmiTheme
import SwiftUI

// MARK: - Add Memory Sheet

struct AddMemorySheet: View {
  @ObservedObject var viewModel: MemoriesViewModel
  var onDismiss: (() -> Void)? = nil

  @Environment(\.dismiss) private var environmentDismiss

  private func dismissSheet() {
    viewModel.newMemoryText = ""
    if let onDismiss = onDismiss {
      onDismiss()
    } else {
      environmentDismiss()
    }
  }

  var body: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Header with close button
      HStack {
        Text("Add Memory")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(Ink.primary)
        Spacer()
        DismissButton(action: dismissSheet)
      }

      TextEditor(text: $viewModel.newMemoryText)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.primary)
        .scrollContentBackground(.hidden)
        .padding(OmiSpacing.md)
        .background(Ink.rowFillHover)
        .cornerRadius(OmiChrome.elementRadius)
        .frame(height: 150)

      HStack(spacing: OmiSpacing.md) {
        // Cancel button
        Button(action: dismissSheet) {
          Text("Cancel")
            .foregroundColor(Ink.secondary)
        }

        Spacer()

        Button {
          Task { await viewModel.createMemory() }
        } label: {
          Text("Save")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(viewModel.newMemoryText.isEmpty ? Ink.secondary : Ink.surface)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .background(
              // Ink.surface is this label's own colour, so filling with it painted white on
              // white and the button read as blank the moment the field had text. The edit
              // sheet's identical button already fills with Ink.primary.
              viewModel.newMemoryText.isEmpty ? Ink.rowFillHover : Ink.primary
            )
            .cornerRadius(OmiChrome.elementRadius)
            .overlay(
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                .stroke(
                  viewModel.newMemoryText.isEmpty ? Color.clear : Ink.separator, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(viewModel.newMemoryText.isEmpty)
      }
    }
    .padding(OmiSpacing.xxl)
    .frame(width: 400)
    .background(Ink.rowFill)
  }
}

// MARK: - Edit Memory Sheet

struct EditMemorySheet: View {
  let memory: ServerMemory
  @ObservedObject var viewModel: MemoriesViewModel
  var onDismiss: (() -> Void)? = nil

  @Environment(\.dismiss) private var environmentDismiss

  private func dismissSheet() {
    viewModel.editText = ""
    if let onDismiss = onDismiss {
      onDismiss()
    } else {
      environmentDismiss()
    }
  }

  var body: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Header with close button
      HStack {
        Text("Edit Memory")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(Ink.primary)
        Spacer()
        DismissButton(action: dismissSheet)
      }

      TextEditor(text: $viewModel.editText)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.primary)
        .scrollContentBackground(.hidden)
        .padding(OmiSpacing.md)
        .background(Ink.rowFillHover)
        .cornerRadius(OmiChrome.elementRadius)
        .frame(height: 150)

      HStack(spacing: OmiSpacing.md) {
        // Cancel button
        Button(action: dismissSheet) {
          Text("Cancel")
            .foregroundColor(Ink.secondary)
        }

        Spacer()

        Button {
          Task { await viewModel.saveEditedMemory(memory) }
        } label: {
          Text("Save")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(viewModel.editText.isEmpty ? Ink.secondary : Ink.surface)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .background(viewModel.editText.isEmpty ? Ink.rowFillHover : Ink.primary)
            .cornerRadius(OmiChrome.elementRadius)
            .overlay(
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                .stroke(viewModel.editText.isEmpty ? Color.clear : Ink.separator, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(viewModel.editText.isEmpty)
      }
    }
    .padding(OmiSpacing.xxl)
    .frame(width: 400)
    .background(Ink.rowFill)
  }
}
