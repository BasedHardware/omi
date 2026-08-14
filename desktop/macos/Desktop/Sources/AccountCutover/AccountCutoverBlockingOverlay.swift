import SwiftUI

/// Fail-closed force-upgrade / migration-maintenance overlays for account cutover.
///
/// LIFECYCLE: permanent
struct AccountCutoverBlockingOverlay: View {
  let decision: AccountCutoverGateDecision
  let strandedNewData: Bool
  let onOpenDownload: (DesktopUpdatePolicyResponse) -> Void

  static func host(onOpenDownload: @escaping (DesktopUpdatePolicyResponse) -> Void) -> some View {
    AccountCutoverBlockingOverlayHost(onOpenDownload: onOpenDownload)
  }

  var body: some View {
    switch decision {
    case .allowProductTraffic:
      EmptyView()
    case .forceUpgrade:
      let policy = DesktopUpdatePolicyResponse(
        id: "account-cutover-force-upgrade",
        active: true,
        severity: .required,
        maximumBuildNumber: nil,
        latestBuildNumber: nil,
        title: "Update Required",
        message: "Install the latest Omi desktop app to continue after account migration.",
        ctaText: "Download latest",
        downloadURL: DesktopUpdatePolicyResponse.stableManualDownloadURL.absoluteString,
        canDismiss: false
      )
      overlay(policy: policy, onDownload: { onOpenDownload(policy) })
    case .migrationMaintenance:
      let policy = DesktopUpdatePolicyResponse(
        id: "account-cutover-migration-maintenance",
        active: true,
        severity: .required,
        maximumBuildNumber: nil,
        latestBuildNumber: nil,
        title: "Migration in Progress",
        message: strandedNewData
          ? "Your account is in maintenance after a migration rollback. Some newer data may be stranded."
          : "Your account is migrating. Product features are paused until migration finishes.",
        ctaText: "OK",
        downloadURL: DesktopUpdatePolicyResponse.stableManualDownloadURL.absoluteString,
        canDismiss: false
      )
      overlay(policy: policy, onDownload: {})
    }
  }

  @ViewBuilder
  private func overlay(
    policy: DesktopUpdatePolicyResponse,
    onDownload: @escaping () -> Void
  ) -> some View {
    Color.black.opacity(0.62)
      .ignoresSafeArea()
      .zIndex(20)
    DesktopRequiredUpdatePrompt(policy: policy, onDownload: onDownload)
      .zIndex(21)
  }
}

private struct AccountCutoverBlockingOverlayHost: View {
  @ObservedObject private var manager = AccountCutoverControlManager.shared
  let onOpenDownload: (DesktopUpdatePolicyResponse) -> Void

  var body: some View {
    if let decision = manager.overlayDecision {
      AccountCutoverBlockingOverlay(
        decision: decision,
        strandedNewData: manager.control.strandedNewData,
        onOpenDownload: onOpenDownload
      )
    }
  }
}
