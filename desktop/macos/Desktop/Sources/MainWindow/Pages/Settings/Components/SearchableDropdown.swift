import AppKit
import OmiTheme
import SwiftUI

struct SearchableDropdownOption: Identifiable, Hashable {
  let id: String
  let title: String
  let subtitle: String?

  init(id: String, title: String, subtitle: String? = nil) {
    self.id = id
    self.title = title
    self.subtitle = subtitle
  }
}

enum SearchableDropdownFiltering {
  static func filteredOptions(
    _ options: [SearchableDropdownOption],
    query: String
  ) -> [SearchableDropdownOption] {
    let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return options }

    return options.filter { option in
      option.title.localizedCaseInsensitiveContains(trimmed)
        || option.id.localizedCaseInsensitiveContains(trimmed)
        || (option.subtitle?.localizedCaseInsensitiveContains(trimmed) ?? false)
    }
  }

  static func usesSearchablePopover(optionCount: Int, threshold: Int = 8) -> Bool {
    optionCount > threshold
  }
}

struct SearchableDropdown: View {
  let title: String
  var label: String? = nil
  let options: [SearchableDropdownOption]
  let selectedId: String?
  var threshold = 8
  var minWidth: CGFloat = 0
  var maxWidth: CGFloat = 320
  var maxHeight: CGFloat = 300
  let onSelect: (SearchableDropdownOption) -> Void

  @State private var isPresented = false
  @State private var query = ""

  private var selectedTitle: String {
    guard let selectedId,
      let selected = options.first(where: { $0.id == selectedId })
    else {
      return label ?? title
    }
    return selected.title
  }

  private var popoverWidth: CGFloat {
    let titleWidth = Self.textWidth(title, font: .systemFont(ofSize: 13, weight: .semibold))
    let optionWidth =
      options
      .map { option in
        max(
          Self.textWidth(option.title, font: .systemFont(ofSize: 13, weight: .regular)),
          option.subtitle.map {
            Self.textWidth($0, font: .systemFont(ofSize: 11, weight: .regular))
          } ?? 0
        )
      }
      .max() ?? 0
    let minimumReadableSearchWidth: CGFloat = 170
    let contentWidth = max(titleWidth, optionWidth, minimumReadableSearchWidth) + 48
    return min(maxWidth, max(contentWidth, minWidth))
  }

  var body: some View {
    if options.count > threshold {
      Button {
        isPresented.toggle()
      } label: {
        dropdownLabel
      }
      .buttonStyle(.plain)
      .popover(isPresented: $isPresented, arrowEdge: .bottom) {
        SearchableDropdownPopover(
          title: title,
          options: options,
          selectedId: selectedId,
          query: $query,
          maxHeight: maxHeight
        ) { option in
          onSelect(option)
          query = ""
          isPresented = false
        }
        .frame(width: popoverWidth)
      }
      .onChange(of: isPresented) { _, presented in
        if !presented {
          query = ""
        }
      }
    } else {
      Menu {
        ForEach(options) { option in
          Button(option.title) {
            onSelect(option)
          }
        }
      } label: {
        dropdownLabel
      }
      .menuStyle(.borderlessButton)
      .fixedSize()
    }
  }

  private var dropdownLabel: some View {
    HStack(spacing: OmiSpacing.xs) {
      Text(selectedTitle)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
        .lineLimit(1)

      Image(systemName: "chevron.down")
        .scaledFont(size: OmiType.micro, weight: .semibold)
        .foregroundColor(OmiColors.textTertiary)
    }
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xs)
    .frame(minWidth: minWidth)
    .background(
      Capsule()
        .fill(OmiColors.backgroundSecondary.opacity(0.7))
        .overlay(Capsule().stroke(OmiColors.border.opacity(0.8), lineWidth: 1))
    )
  }

  private static func textWidth(_ text: String, font: NSFont) -> CGFloat {
    let attributes: [NSAttributedString.Key: Any] = [.font: font]
    return ceil((text as NSString).size(withAttributes: attributes).width)
  }
}

private struct SearchableDropdownPopover: View {
  let title: String
  let options: [SearchableDropdownOption]
  let selectedId: String?
  @Binding var query: String
  let maxHeight: CGFloat
  let onSelect: (SearchableDropdownOption) -> Void

  @FocusState private var searchIsFocused: Bool

  private var filteredOptions: [SearchableDropdownOption] {
    SearchableDropdownFiltering.filteredOptions(options, query: query)
  }

  private var listHeight: CGFloat {
    let singleLineRowHeight: CGFloat = 35
    let subtitleRowHeight: CGFloat = 45
    let spacing: CGFloat = 2
    let verticalPadding: CGFloat = 4
    let naturalHeight = options.reduce(verticalPadding) { height, option in
      height + (option.subtitle == nil ? singleLineRowHeight : subtitleRowHeight) + spacing
    }
    return min(maxHeight, naturalHeight)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text(title)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(OmiColors.textTertiary)

      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "magnifyingglass")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)

        TextField("Search", text: $query)
          .textFieldStyle(.plain)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textPrimary)
          .focused($searchIsFocused)
          .onSubmit {
            let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty, let first = filteredOptions.first {
              onSelect(first)
            }
          }

        if !query.isEmpty {
          Button {
            query = ""
          } label: {
            Image(systemName: "xmark.circle.fill")
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
          .help("Clear search")
        }
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
          .fill(OmiColors.backgroundTertiary)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
              .stroke(OmiColors.border.opacity(0.7), lineWidth: 1)
          )
      )

      if filteredOptions.isEmpty {
        Text("No matches")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
          .frame(maxWidth: .infinity, minHeight: listHeight)
      } else {
        ScrollView {
          LazyVStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            ForEach(filteredOptions) { option in
              SearchableDropdownRow(
                option: option,
                isSelected: option.id == selectedId,
                onSelect: onSelect
              )
            }
          }
          .padding(.vertical, OmiSpacing.hairline)
        }
        .frame(height: listHeight)
      }
    }
    .padding(OmiSpacing.md)
    .background(OmiColors.backgroundSecondary)
    .onAppear {
      DispatchQueue.main.async {
        searchIsFocused = true
      }
    }
  }
}

private struct SearchableDropdownRow: View {
  let option: SearchableDropdownOption
  let isSelected: Bool
  let onSelect: (SearchableDropdownOption) -> Void

  @State private var isHovered = false

  var body: some View {
    Button {
      onSelect(option)
    } label: {
      HStack(spacing: OmiSpacing.sm) {
        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(option.title)
            .scaledFont(size: OmiType.caption, weight: isSelected ? .semibold : .regular)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)

          if let subtitle = option.subtitle {
            Text(subtitle)
              .scaledFont(size: OmiType.micro)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(1)
          }
        }

        Spacer()

        if isSelected {
          Image(systemName: "checkmark")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
        }
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, option.subtitle == nil ? 7 : 6)
      .background(
        RoundedRectangle(cornerRadius: 7, style: .continuous)
          .fill(isHovered || isSelected ? OmiColors.backgroundTertiary : Color.clear)
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovered = hovering
    }
  }
}
