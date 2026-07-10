import SwiftUI
import AppKit
import OmiTheme

struct ExcludedAppRow: View {
  let appName: String
  let onRemove: () -> Void

  @State var isHovered = false

  var body: some View {
    HStack(spacing: 12) {
      AppIconView(appName: appName, size: 24)

      Text(appName)
        .scaledFont(size: 14)
        .foregroundColor(OmiColors.textPrimary)

      Spacer()

      Button(action: onRemove) {
        Image(systemName: "xmark.circle.fill")
          .scaledFont(size: 16)
          .foregroundColor(isHovered ? OmiColors.error : OmiColors.textTertiary)
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, 12)
    .padding(.vertical, 8)
    .background(
      RoundedRectangle(cornerRadius: 8)
        .fill(isHovered ? OmiColors.backgroundQuaternary.opacity(0.5) : Color.clear)
    )
    .onHover { hovering in
      isHovered = hovering
    }
  }
}



struct AppRuleEditorView: View {
  let title: String
  let placeholder: String
  let addButtonTitle: String
  let existingApps: Set<String>
  let builtInApps: Set<String>
  let onAdd: (String) -> Void

  @State var newAppName: String = ""
  @State var runningApps: [String] = []

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text(title)
        .scaledFont(size: 13, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)

      HStack(spacing: 8) {
        TextField(placeholder, text: $newAppName)
          .textFieldStyle(.roundedBorder)
          .onSubmit { addApp() }

        Button(addButtonTitle) { addApp() }
          .buttonStyle(.bordered)
          .disabled(newAppName.trimmingCharacters(in: .whitespaces).isEmpty)
      }

      VStack(alignment: .leading, spacing: 8) {
        HStack {
          Text("Currently Running Apps")
            .scaledFont(size: 12, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
          Spacer()
          Button {
            refreshRunningApps()
          } label: {
            Image(systemName: "arrow.clockwise")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }

        ScrollView(.horizontal, showsIndicators: false) {
          HStack(spacing: 8) {
            ForEach(
              runningApps.filter { !existingApps.contains($0) && !builtInApps.contains($0) },
              id: \.self
            ) { appName in
              RunningAppChip(appName: appName) {
                onAdd(appName)
              }
            }
          }
        }
      }
      .padding(.top, 4)
    }
    .onAppear { refreshRunningApps() }
  }

  func addApp() {
    let trimmed = newAppName.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    onAdd(trimmed)
    newAppName = ""
  }

  func refreshRunningApps() {
    let apps = NSWorkspace.shared.runningApplications
      .compactMap { $0.localizedName }
      .filter { !$0.isEmpty }
      .sorted()

    var seen = Set<String>()
    runningApps = apps.filter { seen.insert($0).inserted }
  }
}

struct BrowserKeywordListView: View {
  @Binding var keywords: [String]
  let onAdd: (String) -> Void
  let onRemove: (String) -> Void

  @State var newKeyword: String = ""
  @State var filterText: String = ""

  var filteredKeywords: [String] {
    if filterText.isEmpty {
      return keywords
    }
    return keywords.filter { $0.lowercased().contains(filterText.lowercased()) }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      // Filter field
      HStack(spacing: 8) {
        Image(systemName: "line.3.horizontal.decrease")
          .scaledFont(size: 11)
          .foregroundColor(OmiColors.textTertiary)
        TextField("Filter keywords...", text: $filterText)
          .textFieldStyle(.plain)
          .scaledFont(size: 12)
        if !filterText.isEmpty {
          Button {
            filterText = ""
          } label: {
            Image(systemName: "xmark.circle.fill")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }
      }
      .padding(.horizontal, 8)
      .padding(.vertical, 4)
      .background(OmiColors.backgroundTertiary)
      .cornerRadius(6)

      // Keyword chips in a wrapping flow layout
      ScrollView {
        FlowLayout(spacing: 6) {
          ForEach(filteredKeywords, id: \.self) { keyword in
            HStack(spacing: 4) {
              Text(keyword)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textPrimary)
              Button {
                onRemove(keyword)
              } label: {
                Image(systemName: "xmark")
                  .scaledFont(size: 8, weight: .bold)
                  .foregroundColor(OmiColors.textTertiary)
              }
              .buttonStyle(.plain)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(6)
          }
        }
        .padding(.vertical, 2)
      }
      .frame(maxHeight: 150)

      // Add new keyword
      HStack(spacing: 8) {
        TextField("Add keyword...", text: $newKeyword)
          .textFieldStyle(.roundedBorder)
          .scaledFont(size: 12)
          .onSubmit { addKeyword() }

        Button("Add") { addKeyword() }
          .buttonStyle(.bordered)
          .controlSize(.small)
          .disabled(newKeyword.trimmingCharacters(in: .whitespaces).isEmpty)
      }

      Text("\(keywords.count) keywords")
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textTertiary)
    }
  }

  func addKeyword() {
    let trimmed = newKeyword.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    onAdd(trimmed)
    newKeyword = ""
  }
}

// MARK: - Running App Chip

struct RunningAppChip: View {
  let appName: String
  let onTap: () -> Void

  @State var isHovered = false

  var body: some View {
    Button(action: onTap) {
      HStack(spacing: 6) {
        AppIconView(appName: appName, size: 16)

        Text(appName)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textSecondary)

        Image(systemName: "plus.circle.fill")
          .scaledFont(size: 12)
          .foregroundColor(isHovered ? OmiColors.purplePrimary : OmiColors.textTertiary)
      }
      .padding(.horizontal, 10)
      .padding(.vertical, 6)
      .background(
        RoundedRectangle(cornerRadius: 6)
          .fill(
            isHovered ? OmiColors.backgroundQuaternary : OmiColors.backgroundTertiary.opacity(0.5))
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovered = hovering
    }
  }
}

#if canImport(PreviewsMacros)
#Preview {
  SettingsPage(
    appState: AppState(),
    selectedSection: .constant(.advanced),
    highlightedSettingId: .constant(nil)
  )
}
#endif
