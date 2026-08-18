import OmiTheme
import SwiftUI

// MARK: - App Selector Sheet

struct AppSelectorSheet: View {
  let apps: [OmiApp]
  let isLoading: Bool
  /// App behind the current primary summary (apps_results[0]); the row shows a
  /// checkmark so the picker opens on the active summarization app.
  var selectedAppId: String? = nil
  /// Locally mirrored preferred app; its row is badged "Default".
  var preferredAppId: String? = nil
  let onSelect: (OmiApp) -> Void
  var onSetPreferred: ((OmiApp) -> Void)? = nil
  let onDismiss: () -> Void

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        Text("Select App")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)

        Spacer()

        Button(action: onDismiss) {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: OmiType.heading)
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }
      .padding()

      Divider()
        .background(Ink.rowFillHover)

      // Apps list
      if apps.isEmpty {
        VStack(spacing: OmiSpacing.md) {
          Image(systemName: "square.grid.2x2")
            .scaledFont(size: OmiType.hero)
            .foregroundColor(Ink.secondary)

          Text("No Apps Available")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.secondary)

          Text("Enable apps with memory capability to reprocess conversations")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
      } else {
        ScrollView {
          LazyVStack(spacing: OmiSpacing.hairline) {
            ForEach(apps) { app in
              AppSelectorRow(
                app: app,
                isSelected: selectedAppId == app.id,
                isPreferred: preferredAppId == app.id,
                isLoading: isLoading && selectedAppId == app.id,
                onSelect: { onSelect(app) },
                onSetPreferred: onSetPreferred == nil ? nil : { onSetPreferred?(app) }
              )
            }
          }
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.sm)
        }
      }
    }
    .frame(width: 320, height: 400)
    .background(Ink.surface)
  }
}

struct AppSelectorRow: View {
  let app: OmiApp
  let isSelected: Bool
  var isPreferred: Bool = false
  let isLoading: Bool
  let onSelect: () -> Void
  var onSetPreferred: (() -> Void)? = nil

  @State private var isHovering = false

  var body: some View {
    Button(action: onSelect) {
      HStack(spacing: OmiSpacing.md) {
        AsyncImage(url: URL(string: app.image)) { phase in
          switch phase {
          case .success(let image):
            image
              .resizable()
              .aspectRatio(contentMode: .fill)
          default:
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(Ink.rowFillHover)
          }
        }
        .frame(width: 44, height: 44)
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(app.name)
            .scaledFont(size: OmiType.body, weight: .medium)
          HStack(spacing: OmiSpacing.xxs) {
            Text(app.author)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)

            if isPreferred {
              Image(systemName: "star.fill")
                .scaledFont(size: OmiType.micro)
                .foregroundColor(PageGlass.starred)
              Text("Default")
                .scaledFont(size: OmiType.micro)
                .foregroundColor(Ink.secondary)
            }
          }
        }

        Spacer()

        if isLoading {
          ProgressView()
            .scaleEffect(0.7)
        } else if isSelected {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: OmiType.heading)
            .foregroundColor(Ink.primary)
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(isSelected || isHovering ? Ink.rowFillHover : Color.clear)
      )
    }
    .buttonStyle(.plain)
    .disabled(isLoading)
    .onHover { isHovering = $0 }
    // macOS analog of mobile's swipe-to-set-default: right-click a row to pin
    // the preferred summarization app for future conversations.
    .contextMenu {
      if let onSetPreferred {
        Button {
          onSetPreferred()
        } label: {
          Label(
            isPreferred ? "Default App" : "Set as Default",
            systemImage: isPreferred ? "star.fill" : "star"
          )
        }
        .disabled(isPreferred)
      }
    }
  }
}
