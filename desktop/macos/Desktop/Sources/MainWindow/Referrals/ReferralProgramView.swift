import AppKit
import OmiTheme
import SwiftUI

@MainActor
final class ReferralViewModel: ObservableObject {
  enum State: Equatable {
    case idle
    case loading
    case loaded(String)
    case failed
  }

  @Published private(set) var state: State = .idle
  private let loadLink: () async throws -> ReferralLinkResponse

  init() {
    self.loadLink = {
      try await APIClient.shared.getReferralLink()
    }
  }

  init(loadLink: @escaping () async throws -> ReferralLinkResponse) {
    self.loadLink = loadLink
  }

  func load() async {
    guard state == .idle || state == .failed else { return }
    state = .loading
    do {
      state = .loaded(try await loadLink().referralURL)
    } catch {
      state = .failed
    }
  }
}

struct ReferralProgramView: View {
  @StateObject private var viewModel: ReferralViewModel
  @State private var copied = false
  private let showsIntroduction: Bool

  init(showsIntroduction: Bool = true) {
    self.showsIntroduction = showsIntroduction
    _viewModel = StateObject(wrappedValue: ReferralViewModel())
  }

  init(viewModel: ReferralViewModel, showsIntroduction: Bool = true) {
    self.showsIntroduction = showsIntroduction
    _viewModel = StateObject(wrappedValue: viewModel)
  }

  var body: some View {
    VStack(spacing: OmiSpacing.xl) {
      if showsIntroduction {
        Image(systemName: "gift")
          .scaledFont(size: 28, weight: .semibold)
          .foregroundColor(Ink.primary)
          .frame(width: 52, height: 52)
          .background(Circle().fill(Ink.wash))
          .accessibilityHidden(true)

        VStack(spacing: OmiSpacing.sm) {
          Text("Give a friend one free month of Operator")
            .scaledFont(size: OmiType.title, weight: .semibold)
            .foregroundColor(Ink.primary)
            .multilineTextAlignment(.center)

          Text("Share your unique link. When a friend joins Omi, they'll get one month of Operator free.")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
        }
      }

      referralControl
    }
    .frame(maxWidth: .infinity)
    .task { await viewModel.load() }
  }

  @ViewBuilder
  private var referralControl: some View {
    switch viewModel.state {
    case .idle, .loading:
      ProgressView("Getting your link…")
        .controlSize(.small)
        .foregroundColor(Ink.secondary)
        .frame(minHeight: 44)
    case .loaded(let link):
      HStack(spacing: OmiSpacing.sm) {
        Text(link)
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)
          .truncationMode(.middle)
          .textSelection(.enabled)
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(.horizontal, OmiSpacing.md)
          .frame(height: 38)
          .settingsGlassWell(radius: SettingsGlassMetrics.controlRadius)
          .accessibilityIdentifier("referral-link")

        Button {
          copy(link)
        } label: {
          Label(copied ? "Copied" : "Copy link", systemImage: copied ? "checkmark" : "doc.on.doc")
        }
        .buttonStyle(OmiButtonStyle(.primary, size: .compact))
        .accessibilityIdentifier("copy-referral-link")
      }
    case .failed:
      VStack(spacing: OmiSpacing.sm) {
        Text("We couldn't get your referral link.")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
        Button("Try again") {
          Task { await viewModel.load() }
        }
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        .accessibilityIdentifier("retry-referral-link")
      }
      .frame(minHeight: 44)
    }
  }

  private func copy(_ link: String) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(link, forType: .string)
    copied = true
    Task {
      try? await Task.sleep(for: .seconds(2))
      copied = false
    }
  }
}

struct ReferralSheetView: View {
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    VStack(alignment: .trailing, spacing: 0) {
      Button {
        dismiss()
      } label: {
        Image(systemName: "xmark")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(Ink.secondary)
          .frame(width: 28, height: 28)
          .background(Circle().fill(Ink.wash))
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Close")

      ReferralProgramView()
        .padding(.horizontal, OmiSpacing.xxl)
        .padding(.bottom, OmiSpacing.xxl)
    }
    .padding(OmiSpacing.lg)
    .frame(width: 540, height: 340)
    .background(Ink.surface)
  }
}

struct ReferralTopBarButton: View {
  let action: () -> Void
  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "gift")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .frame(width: TopNavigationPillMetrics.iconWidth)
        Text("Refer")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .lineLimit(1)
          .fixedSize()
      }
      .foregroundStyle(Ink.primary)
      .padding(.horizontal, TopNavigationPillMetrics.horizontalPadding)
      .frame(height: TopNavigationPillMetrics.height)
      .background {
        Capsule(style: .continuous)
          .fill(isHovering ? Ink.wash : Color.clear)
      }
      .overlay {
        Capsule(style: .continuous).strokeBorder(Ink.hairline, lineWidth: 1)
      }
      .contentShape(Capsule(style: .continuous))
      .fixedSize()
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .help("Refer a friend")
    .accessibilityLabel("Refer a friend")
    .accessibilityIdentifier("top-navigation-refer")
  }
}

extension SettingsContentView {
  var referralSection: some View {
    settingsCard(settingId: "referral.link") {
      ReferralProgramView()
        .padding(.vertical, OmiSpacing.xl)
    }
  }
}
