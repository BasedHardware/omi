import SwiftUI
import AppKit
import OmiTheme

struct ExcludedAppRow: View {
  let appName: String
  let onRemove: () -> Void

  @State var isHovered = false

  var body: some View {
    HStack(spacing: OmiSpacing.md) {
      AppIconView(appName: appName, size: 24)

      Text(appName)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textPrimary)

      Spacer()

      Button(action: onRemove) {
        Image(systemName: "xmark.circle.fill")
          .scaledFont(size: OmiType.subheading)
          .foregroundColor(isHovered ? OmiColors.error : OmiColors.textTertiary)
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
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
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text(title)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)

      HStack(spacing: OmiSpacing.sm) {
        TextField(placeholder, text: $newAppName)
          .settingsTextInputStyle()
          .onSubmit { addApp() }

        Button(addButtonTitle) { addApp() }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          .disabled(newAppName.trimmingCharacters(in: .whitespaces).isEmpty)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack {
          Text("Currently Running Apps")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
          Spacer()
          Button {
            refreshRunningApps()
          } label: {
            Image(systemName: "arrow.clockwise")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }

        ScrollView(.horizontal, showsIndicators: false) {
          HStack(spacing: OmiSpacing.sm) {
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
      .padding(.top, OmiSpacing.xxs)
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
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      // Filter field
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "line.3.horizontal.decrease")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
        TextField("Filter keywords...", text: $filterText)
          .textFieldStyle(.plain)
          .scaledFont(size: OmiType.caption)
        if !filterText.isEmpty {
          Button {
            filterText = ""
          } label: {
            Image(systemName: "xmark.circle.fill")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xxs)
      .background(OmiColors.backgroundTertiary)
      .cornerRadius(OmiChrome.badgeRadius)

      // Keyword chips in a wrapping flow layout
      ScrollView {
        FlowLayout(spacing: OmiSpacing.xs) {
          ForEach(filteredKeywords, id: \.self) { keyword in
            HStack(spacing: OmiSpacing.xxs) {
              Text(keyword)
                .scaledFont(size: OmiType.caption)
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
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xxs)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(OmiChrome.badgeRadius)
          }
        }
        .padding(.vertical, OmiSpacing.hairline)
      }
      .frame(maxHeight: 150)

      // Add new keyword
      HStack(spacing: OmiSpacing.sm) {
        TextField("Add keyword...", text: $newKeyword)
          .settingsTextInputStyle()
          .onSubmit { addKeyword() }

        Button("Add") { addKeyword() }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          .disabled(newKeyword.trimmingCharacters(in: .whitespaces).isEmpty)
      }

      Text("\(keywords.count) keywords")
        .scaledFont(size: OmiType.caption)
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
      HStack(spacing: OmiSpacing.xs) {
        AppIconView(appName: appName, size: 16)

        Text(appName)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textSecondary)

        Image(systemName: "plus.circle.fill")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(isHovered ? OmiColors.accent : OmiColors.textTertiary)
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
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
