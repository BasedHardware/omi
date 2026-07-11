import AppKit
import Foundation
import SwiftUI
import OmiTheme

@MainActor
final class DesktopUpdatePolicyManager: ObservableObject {
  static let shared = DesktopUpdatePolicyManager()

  @Published private(set) var policy: DesktopUpdatePolicyResponse?

  private var lastCheckAt = Date.distantPast
  private let minimumCheckInterval: TimeInterval = 5 * 60
  private let dismissedPrefix = "desktopUpdatePolicyDismissed."

  private init() {}

  var visiblePolicy: DesktopUpdatePolicyResponse? {
    guard let policy, policy.active, policy.severity != .none else { return nil }
    if policy.isRequired { return policy }
    return isDismissed(policy) ? nil : policy
  }

  func refresh(force: Bool = false) {
    let now = Date()
    guard force || now.timeIntervalSince(lastCheckAt) >= minimumCheckInterval else { return }
    lastCheckAt = now

    Task {
      do {
        let fetched = try await APIClient.shared.getDesktopUpdatePolicy(currentBuild: currentBuildNumber)
        await MainActor.run {
          self.policy = fetched.active ? fetched : nil
        }
      } catch {
        log("DesktopUpdatePolicy: failed to fetch policy: \(error.localizedDescription)")
      }
    }
  }

  func dismiss(_ policy: DesktopUpdatePolicyResponse) {
    guard policy.canDismiss, !policy.isRequired else { return }
    UserDefaults.standard.set(true, forKey: dismissedKey(for: policy))
    if self.policy?.id == policy.id {
      self.policy = nil
    }
  }

  func openDownload(_ policy: DesktopUpdatePolicyResponse) {
    guard let url = URL(string: policy.downloadURL),
      let scheme = url.scheme?.lowercased(),
      ["http", "https"].contains(scheme)
    else {
      log("DesktopUpdatePolicy: ignored invalid download URL")
      return
    }
    NSWorkspace.shared.open(url)
  }

  private var currentBuildNumber: Int? {
    guard let raw = Bundle.main.infoDictionary?["CFBundleVersion"] as? String else { return nil }
    return Int(raw)
  }

  private func isDismissed(_ policy: DesktopUpdatePolicyResponse) -> Bool {
    UserDefaults.standard.bool(forKey: dismissedKey(for: policy))
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
