import OmiTheme
import SwiftUI

/// One search interaction for the desktop's list surfaces.
///
/// Queries commit after a short pause while clearing commits immediately. The
/// coordinator keeps that timing and cancellation behavior identical across
/// Memories and Conversations without coupling either page to the other's data.
@MainActor
final class DebouncedSearchCoordinator: ObservableObject {
  typealias Sleeper = @Sendable (UInt64) async throws -> Void

  static let standardDelayNanoseconds: UInt64 = 250_000_000

  private let delayNanoseconds: UInt64
  private let sleeper: Sleeper
  private var pendingTask: Task<Void, Never>?

  init(
    delayNanoseconds: UInt64 = DebouncedSearchCoordinator.standardDelayNanoseconds,
    sleeper: @escaping Sleeper = { try await Task.sleep(nanoseconds: $0) }
  ) {
    self.delayNanoseconds = delayNanoseconds
    self.sleeper = sleeper
  }

  deinit {
    pendingTask?.cancel()
  }

  func submit(
    _ rawQuery: String,
    perform: @escaping @MainActor (String) async -> Void
  ) {
    pendingTask?.cancel()

    let query = Self.normalized(rawQuery)
    guard !query.isEmpty else {
      pendingTask = Task { await perform("") }
      return
    }

    let delayNanoseconds = delayNanoseconds
    let sleeper = sleeper
    pendingTask = Task {
      do {
        try await sleeper(delayNanoseconds)
      } catch {
        return
      }
      guard !Task.isCancelled else { return }
      await perform(query)
    }
  }

  static func normalized(_ query: String) -> String {
    query.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  static func isActive(_ query: String) -> Bool {
    !normalized(query).isEmpty
  }
}

/// Shared search chrome for desktop list pages.
struct OmiSearchField: View {
  let placeholder: String
  @Binding var text: String
  var isLoading = false

  @FocusState private var isFocused: Bool

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      Group {
        if isLoading {
          ProgressView()
            .controlSize(.small)
        } else {
          Image(systemName: "magnifyingglass")
            .scaledFont(size: OmiType.body, weight: .medium)
        }
      }
      .frame(width: 16, height: 16)
      .foregroundStyle(isFocused ? OmiColors.textPrimary : OmiColors.textTertiary)

      TextField(placeholder, text: $text)
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body)
        .foregroundStyle(OmiColors.textPrimary)
        .focused($isFocused)

      if !text.isEmpty {
        Button {
          text = ""
        } label: {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: OmiType.body)
            .foregroundStyle(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
        .help("Clear search")
        .accessibilityLabel("Clear search")
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .frame(minHeight: 40)
    .omiControlSurface(
      fill: OmiColors.backgroundRaised,
      radius: OmiChrome.controlRadius,
      stroke: isFocused
        ? OmiColors.accent.opacity(0.32)
        : OmiColors.border.opacity(0.40)
    )
    .accessibilityElement(children: .contain)
  }
}
