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
        VStack(spacing: 12) {
            // Search field
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(isSearchFocused ? OmiColors.purplePrimary : OmiColors.textTertiary)
                    .animation(.easeInOut(duration: 0.15), value: isSearchFocused)

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
                        .scaledFont(size: 10, weight: .medium, design: .monospaced)
                        .foregroundColor(OmiColors.textQuaternary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(OmiColors.backgroundQuaternary)
                        .cornerRadius(3)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(OmiColors.backgroundTertiary)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(isSearchFocused ? OmiColors.purplePrimary.opacity(0.5) : Color.clear, lineWidth: 1)
                    )
            )

            // Filters row
            HStack(spacing: 12) {
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
                    HStack(spacing: 6) {
                        if let app = selectedApp {
                            AppIconView(appName: app, size: 14)
                        } else {
                            Image(systemName: "square.grid.2x2")
                                .scaledFont(size: 12)
                        }

                        Text(selectedApp ?? "All Apps")
                            .scaledFont(size: 13)
                            .lineLimit(1)

                        Image(systemName: "chevron.down")
                            .scaledFont(size: 10)
                    }
                    .foregroundColor(selectedApp != nil ? OmiColors.textPrimary : OmiColors.textSecondary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background(selectedApp != nil ? Color.white : OmiColors.backgroundTertiary)
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
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
                HStack(spacing: 8) {
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
                        HStack(spacing: 4) {
                            Image(systemName: "xmark")
                            Text("Clear")
                        }
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(OmiColors.backgroundQuaternary)
                        .cornerRadius(4)
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
                .scaledFont(size: 12, weight: isSelected ? .semibold : .regular)
                .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(isSelected ? Color.white : Color.clear)
                .cornerRadius(6)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(isSelected ? OmiColors.border : Color.clear, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}

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
