import OmiTheme
import SwiftUI

/// Search bar component for Rewind with app filter and date picker
struct RewindSearchBar: View {
  @Binding var searchQuery: String
  @Binding var selectedApp: String?
  @Binding var selectedDate: Date
  let availableApps: [String]
  let isSearching: Bool
  let onAppFilterChanged: (String?) -> Void
  let onDateChanged: (Date) -> Void

  @FocusState private var isSearchFocused: Bool

  var body: some View {
    VStack(spacing: OmiSpacing.md) {
      // Search field
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "magnifyingglass")
          .foregroundColor(isSearchFocused ? OmiColors.accent : OmiColors.textTertiary)
          .omiAnimation(.easeInOut(duration: 0.15), value: isSearchFocused)

        TextField("Search your screen history...", text: $searchQuery)
          .textFieldStyle(.plain)
          .foregroundColor(OmiColors.textPrimary)
          .focused($isSearchFocused)

        if isSearching {
          ProgressView()
            .progressViewStyle(.circular)
            .scaleEffect(0.7)
        }

        if !searchQuery.isEmpty {
          Button {
            searchQuery = ""
          } label: {
            Image(systemName: "xmark.circle.fill")
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }

        // Keyboard shortcut hint
        if searchQuery.isEmpty && !isSearchFocused {
          Text("⌘F")
            .scaledFont(size: OmiType.micro, weight: .medium, design: .monospaced)
            .foregroundColor(OmiColors.textQuaternary)
            .padding(.horizontal, OmiSpacing.xs)
            .padding(.vertical, OmiSpacing.hairline)
            .background(OmiColors.backgroundQuaternary)
            .cornerRadius(OmiChrome.stripRadius)
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.md)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(OmiColors.backgroundTertiary)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .stroke(isSearchFocused ? OmiColors.accent.opacity(0.5) : Color.clear, lineWidth: 1)
          )
      )

      // Filters row
      HStack(spacing: OmiSpacing.md) {
        // App filter
        Menu {
          Button {
            selectedApp = nil
            onAppFilterChanged(nil)
          } label: {
            HStack {
              Image(systemName: "square.grid.2x2")
              Text("All Apps")
              if selectedApp == nil {
                Spacer()
                Image(systemName: "checkmark")
              }
            }
          }

          Divider()

          ForEach(availableApps, id: \.self) { app in
            Button {
              selectedApp = app
              onAppFilterChanged(app)
            } label: {
              HStack {
                // Note: Menu doesn't support custom views well, so we use Label
                Label(app, systemImage: "app")
                if selectedApp == app {
                  Spacer()
                  Image(systemName: "checkmark")
                }
              }
            }
          }
        } label: {
          HStack(spacing: OmiSpacing.xs) {
            if let app = selectedApp {
              AppIconView(appName: app, size: 14)
            } else {
              Image(systemName: "square.grid.2x2")
                .scaledFont(size: OmiType.caption)
            }

            Text(selectedApp ?? "All Apps")
              .scaledFont(size: OmiType.body)
              .lineLimit(1)

            Image(systemName: "chevron.down")
              .scaledFont(size: OmiType.micro)
          }
          .foregroundColor(selectedApp != nil ? OmiColors.textPrimary : OmiColors.textSecondary)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, OmiSpacing.xs)
          .background(selectedApp != nil ? Color.white : OmiColors.backgroundTertiary)
          .cornerRadius(OmiChrome.elementRadius)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
              .stroke(selectedApp != nil ? OmiColors.border : Color.clear, lineWidth: 1)
          )
        }
        .menuStyle(.borderlessButton)

        // Date picker
        DatePicker(
          "",
          selection: $selectedDate,
          displayedComponents: [.date]
        )
        .datePickerStyle(.compact)
        .labelsHidden()
        .onChange(of: selectedDate) { _, newDate in
          onDateChanged(newDate)
        }

        Spacer()

        // Quick date buttons
        HStack(spacing: OmiSpacing.sm) {
          quickDateButton("Today", date: Date())
          quickDateButton("Yesterday", date: Calendar.current.date(byAdding: .day, value: -1, to: Date())!)
          quickDateButton("This Week", date: Calendar.current.date(byAdding: .day, value: -7, to: Date())!)
        }

        // Clear all filters
        if selectedApp != nil || !Calendar.current.isDateInToday(selectedDate) {
          Button {
            selectedApp = nil
            selectedDate = Date()
            onAppFilterChanged(nil)
            onDateChanged(Date())
          } label: {
            HStack(spacing: OmiSpacing.xxs) {
              Image(systemName: "xmark")
              Text("Clear")
            }
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xxs)
            .background(OmiColors.backgroundQuaternary)
            .cornerRadius(OmiChrome.stripRadius)
          }
          .buttonStyle(.plain)
        }
      }
    }
  }

  private func quickDateButton(_ title: String, date: Date) -> some View {
    let isSelected = Calendar.current.isDate(selectedDate, inSameDayAs: date)

    return Button {
      selectedDate = date
      onDateChanged(date)
    } label: {
      Text(title)
        .scaledFont(size: OmiType.caption, weight: isSelected ? .semibold : .regular)
        .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.xxs)
        .background(isSelected ? Color.white : Color.clear)
        .cornerRadius(OmiChrome.badgeRadius)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
            .stroke(isSelected ? OmiColors.border : Color.clear, lineWidth: 1)
        )
    }
    .buttonStyle(.plain)
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    VStack {
      RewindSearchBar(
        searchQuery: .constant(""),
        selectedApp: .constant(nil),
        selectedDate: .constant(Date()),
        availableApps: ["Safari", "Xcode", "Slack", "Terminal"],
        isSearching: false,
        onAppFilterChanged: { _ in },
        onDateChanged: { _ in }
      )

      RewindSearchBar(
        searchQuery: .constant("meeting notes"),
        selectedApp: .constant("Slack"),
        selectedDate: .constant(Date()),
        availableApps: ["Safari", "Xcode", "Slack", "Terminal"],
        isSearching: true,
        onAppFilterChanged: { _ in },
        onDateChanged: { _ in }
      )
    }
    .padding()
    .background(OmiColors.backgroundPrimary)
  }
#endif
