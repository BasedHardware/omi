import AppKit
import Foundation
import OmiTheme
import SwiftUI

@MainActor
final class DesktopUpdatePolicyManager: ObservableObject {
  static let shared = DesktopUpdatePolicyManager()

  @Published private(set) var policy: DesktopUpdatePolicyResponse?

  private var lastCheckAt = Date.distantPast
  private let minimumCheckInterval: TimeInterval = 5 * 60
  private let dismissedPrefix = "desktopUpdatePolicyDismissed."
  private let fetchPolicy: (Int?) async throws -> DesktopUpdatePolicyResponse
  private let currentBuildProvider: () -> Int?
  private let now: () -> Date
  private let defaults: UserDefaults

  private init() {
    fetchPolicy = { currentBuild in
      try await APIClient.shared.getDesktopUpdatePolicy(currentBuild: currentBuild)
    }
    currentBuildProvider = {
      guard let raw = Bundle.main.infoDictionary?["CFBundleVersion"] as? String else { return nil }
      return Int(raw)
    }
    now = Date.init
    defaults = .standard
  }

  init(
    fetchPolicy: @escaping (Int?) async throws -> DesktopUpdatePolicyResponse,
    currentBuildProvider: @escaping () -> Int? = { nil },
    now: @escaping () -> Date = Date.init,
    defaults: UserDefaults = .standard
  ) {
    self.fetchPolicy = fetchPolicy
    self.currentBuildProvider = currentBuildProvider
    self.now = now
    self.defaults = defaults
  }

  var visiblePolicy: DesktopUpdatePolicyResponse? {
    guard let policy, policy.active, policy.severity != .none else { return nil }
    if policy.isRequired { return policy }
    return isDismissed(policy) ? nil : policy
  }

  func refresh(force: Bool = false) {
    Task { await refreshNow(force: force) }
  }

  func refreshNow(force: Bool = false) async {
    let currentTime = now()
    guard force || currentTime.timeIntervalSince(lastCheckAt) >= minimumCheckInterval else { return }
    lastCheckAt = currentTime

    do {
      let fetched = try await fetchPolicy(currentBuildProvider())
      policy = fetched.active ? fetched : nil
    } catch {
      // Never preserve a stale required prompt when its control plane is down.
      // Sparkle and the stable manual download path remain available independently.
      policy = nil
      log("DesktopUpdatePolicy: unavailable error_type=\(String(reflecting: type(of: error)))")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "desktop_update",
        from: "desktop_update_policy",
        to: "desktop_update_appcast",
        reason: "other",
        outcome: .recovered,
        extra: ["user_visible": false]
      )
    }
  }

  func dismiss(_ policy: DesktopUpdatePolicyResponse) {
    guard policy.canDismiss, !policy.isRequired else { return }
    defaults.set(true, forKey: dismissedKey(for: policy))
    if self.policy?.id == policy.id {
      self.policy = nil
    }
  }

  func openDownload(_ policy: DesktopUpdatePolicyResponse) {
    NSWorkspace.shared.open(DesktopUpdatePolicyResponse.resolvedDownloadURL(from: policy.downloadURL))
  }

  private func isDismissed(_ policy: DesktopUpdatePolicyResponse) -> Bool {
    defaults.bool(forKey: dismissedKey(for: policy))
  }

  private func dismissedKey(for policy: DesktopUpdatePolicyResponse) -> String {
    dismissedPrefix + policy.id
  }
}

struct DesktopUpdatePolicyBanner: View {
  let policy: DesktopUpdatePolicyResponse
  let onDownload: () -> Void
  let onDismiss: () -> Void

  var body: some View {
    HStack(alignment: .center, spacing: OmiSpacing.md) {
      Image(systemName: "arrow.down.circle.fill")
        .scaledFont(size: OmiType.subheading)
        .foregroundColor(.white)
        .frame(width: 22)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(policy.title ?? "Update Omi")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(.white)
          .lineLimit(1)
        if let message = policy.message {
          Text(message)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(.white.opacity(0.82))
            .lineLimit(2)
            .truncationMode(.tail)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
      .frame(maxWidth: 400, alignment: .leading)
      .layoutPriority(1)

      Button(policy.ctaText) {
        onDownload()
      }
      .buttonStyle(.plain)
      .scaledFont(size: OmiType.caption, weight: .semibold)
      .foregroundColor(Color(red: 0.08, green: 0.09, blue: 0.10))
      .padding(.horizontal, OmiSpacing.md)
      .frame(height: 32)
      .background(Color.white.opacity(0.94))
      .clipShape(RoundedRectangle(cornerRadius: 7))
      .fixedSize(horizontal: true, vertical: false)
      .layoutPriority(2)

      if policy.canDismiss {
        Button {
          onDismiss()
        } label: {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.caption, weight: .semibold)
        }
        .buttonStyle(.plain)
        .foregroundColor(.white.opacity(0.72))
        .frame(width: 24, height: 24)
        .help("Dismiss")
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.md)
    .background(Color(red: 0.10, green: 0.12, blue: 0.14).opacity(0.98))
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
        .stroke(Color.white.opacity(0.12), lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))
    .shadow(color: Color.black.opacity(0.28), radius: 18, x: 0, y: 8)
  }
}

struct DesktopRequiredUpdatePrompt: View {
  let policy: DesktopUpdatePolicyResponse
  let onDownload: () -> Void

  var body: some View {
    VStack(spacing: OmiSpacing.lg) {
      Image(systemName: "arrow.down.circle.fill")
        .scaledFont(size: 30)
        .foregroundColor(.white)

      VStack(spacing: OmiSpacing.sm) {
        Text(policy.title ?? "Update Required")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(.white)
        Text(policy.message ?? "Please install the latest Omi desktop app to continue.")
          .scaledFont(size: OmiType.body)
          .foregroundColor(.white.opacity(0.72))
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
      }

      Button(policy.ctaText) {
        onDownload()
      }
      .buttonStyle(.borderedProminent)
      .controlSize(.large)
    }
    .frame(width: 420)
    .padding(OmiSpacing.xxl)
    .background(Color(red: 0.08, green: 0.09, blue: 0.10))
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .stroke(Color.white.opacity(0.14), lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))
    .shadow(color: Color.black.opacity(0.36), radius: 24, x: 0, y: 14)
  }
}
