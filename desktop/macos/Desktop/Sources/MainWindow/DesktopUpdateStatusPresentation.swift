import OmiTheme
import SwiftUI

/// Pure status mapping for Sparkle update UI shared by the chat-first top bar,
/// Settings → About, and the legacy sidebar widget (#11108).
enum DesktopUpdateStatusPresentation {
  enum Kind: Equatable {
    case idle
    case checking
    case downloading(version: String)
    case updateAvailable(version: String)
    case restartImminent(version: String)
    case deferredForRecording(version: String)

    var isVisible: Bool {
      self != .idle
    }

    var showsProgress: Bool {
      switch self {
      case .checking, .downloading, .restartImminent, .deferredForRecording:
        return true
      case .idle, .updateAvailable:
        return false
      }
    }

    /// Full-width / Settings headline.
    var title: String {
      switch self {
      case .idle:
        return ""
      case .checking:
        return "Checking for updates…"
      case .downloading:
        return "Downloading Update…"
      case .updateAvailable:
        return "Update Available"
      case .restartImminent:
        return "Update ready — Omi will restart"
      case .deferredForRecording:
        return "Update ready — waiting for quiet moment"
      }
    }

    /// Optional secondary line (version) for expanded surfaces.
    var detail: String? {
      switch self {
      case .idle, .checking:
        return nil
      case .downloading(let version), .updateAvailable(let version), .restartImminent(let version),
        .deferredForRecording(let version):
        return version.isEmpty ? nil : "v\(version)"
      }
    }

    /// Top-bar chip label (keeps version when known).
    var compactTitle: String {
      switch self {
      case .idle:
        return ""
      case .checking:
        return "Checking…"
      case .downloading(let version):
        return version.isEmpty ? "Downloading…" : "Downloading v\(version)…"
      case .updateAvailable(let version):
        return version.isEmpty ? "Update Available" : "Update v\(version)"
      case .restartImminent:
        return "Restarting…"
      case .deferredForRecording:
        return "Update waiting…"
      }
    }

    var accessibilityLabel: String {
      if let detail {
        return "\(title) \(detail)"
      }
      return title
    }
    /// Compact Settings / control label while a session is active.
    var checkActionTitle: String {
      switch self {
      case .idle, .updateAvailable:
        return "Check Now"
      case .checking:
        return "Checking…"
      case .downloading:
        return "Downloading…"
      case .restartImminent:
        return "Restarting…"
      case .deferredForRecording:
        return "Waiting…"
      }
    }
  }

  static func kind(
    sessionInProgress: Bool,
    updateAvailable: Bool,
    availableVersion: String,
    restartImminent: Bool = false,
    deferredForRecording: Bool = false,
    userInitiatedCheck: Bool = false
  ) -> Kind {
    if deferredForRecording {
      return .deferredForRecording(version: availableVersion)
    }
    if restartImminent {
      return .restartImminent(version: availableVersion)
    }
    if sessionInProgress && updateAvailable {
      return .downloading(version: availableVersion)
    }
    // Only surface "Checking…" for user-initiated checks. Automatic Sparkle
    // polls (every 2–10 min) also set sessionInProgress and would otherwise
    // flash a non-actionable chip in the chat-first top bar (#11108 / cubic).
    if sessionInProgress && userInitiatedCheck {
      return .checking
    }
    if updateAvailable {
      return .updateAvailable(version: availableVersion)
    }
    return .idle
  }
}

/// Compact spinner for update chrome. macOS `ProgressView()` defaults to a
/// linear bar (~100pt+), which left a blank gap beside "Downloading…" in the
/// top-bar chip; pin circular style and a caption-sized frame.
struct DesktopUpdateStatusProgressIndicator: View {
  var diameter: CGFloat = 16

  var body: some View {
    ProgressView()
      .progressViewStyle(.circular)
      .controlSize(.small)
      .tint(Ink.surface)
      .frame(width: diameter, height: diameter)
  }
}

/// Production label for `DesktopUpdateStatusChip`, extracted so layout tests
/// can measure the hugging width without Sparkle session state.
struct DesktopUpdateStatusChipLabel: View {
  let kind: DesktopUpdateStatusPresentation.Kind
  var glowAnimating: Bool = false

  var body: some View {
    HStack(spacing: OmiSpacing.xs) {
      if kind.showsProgress {
        DesktopUpdateStatusProgressIndicator()
      } else {
        Image(systemName: "arrow.down.circle.fill")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(Ink.surface)
      }

      Text(kind.compactTitle)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(Ink.surface)
        .lineLimit(1)
    }
    .padding(.horizontal, OmiSpacing.sm)
    .frame(height: 30)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(Ink.primary)
    )
    .shadow(color: Ink.primary.opacity(glowAnimating ? 0.55 : 0.25), radius: 6)
  }
}

/// Compact chip shown in `DesktopTopBar` so chat-first shell users see Sparkle
/// progress (the legacy sidebar widget it used to share this job with is gone).
struct DesktopUpdateStatusChip: View {
  @ObservedObject private var updaterViewModel = UpdaterViewModel.shared
  @State private var glowAnimating = false

  private var kind: DesktopUpdateStatusPresentation.Kind {
    DesktopUpdateStatusPresentation.kind(
      sessionInProgress: updaterViewModel.updateSessionInProgress,
      updateAvailable: updaterViewModel.updateAvailable,
      availableVersion: updaterViewModel.availableVersion,
      restartImminent: updaterViewModel.updateRestartImminent,
      deferredForRecording: updaterViewModel.updateDeferredForActiveRecording,
      userInitiatedCheck: updaterViewModel.userInitiatedCheckInProgress
    )
  }

  var body: some View {
    if kind.isVisible {
      Button(action: {
        if updaterViewModel.canManuallyCheckForUpdates {
          updaterViewModel.checkForUpdates()
        }
      }) {
        DesktopUpdateStatusChipLabel(kind: kind, glowAnimating: glowAnimating)
      }
      .buttonStyle(.plain)
      .help(kind.accessibilityLabel)
      .accessibilityIdentifier("desktop-update-status-chip")
      .accessibilityLabel(kind.accessibilityLabel)
      .onAppear {
        OmiMotion.withGated(.easeInOut(duration: 1.2).repeatForever(autoreverses: true)) {
          glowAnimating = true
        }
      }
      .transition(.opacity)
    }
  }
}

/// Expanded accent card used by the legacy sidebar (and any future full-width surface).
struct DesktopUpdateStatusBanner: View {
  @ObservedObject private var updaterViewModel = UpdaterViewModel.shared
  var isCollapsed: Bool = false
  var iconWidth: CGFloat = 20
  @State private var glowAnimating = false

  private var kind: DesktopUpdateStatusPresentation.Kind {
    DesktopUpdateStatusPresentation.kind(
      sessionInProgress: updaterViewModel.updateSessionInProgress,
      updateAvailable: updaterViewModel.updateAvailable,
      availableVersion: updaterViewModel.availableVersion,
      restartImminent: updaterViewModel.updateRestartImminent,
      deferredForRecording: updaterViewModel.updateDeferredForActiveRecording,
      userInitiatedCheck: updaterViewModel.userInitiatedCheckInProgress
    )
  }

  var body: some View {
    if kind.isVisible {
      Button(action: {
        if updaterViewModel.canManuallyCheckForUpdates {
          updaterViewModel.checkForUpdates()
        }
      }) {
        HStack(spacing: OmiSpacing.md) {
          if kind.showsProgress {
            DesktopUpdateStatusProgressIndicator(diameter: iconWidth)
          } else {
            Image(systemName: "arrow.down.circle.fill")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.surface)
              .frame(width: iconWidth)
          }

          if !isCollapsed {
            VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
              Text(kind.title)
                .scaledFont(size: OmiType.body, weight: .semibold)
                .foregroundColor(Ink.surface)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

              if let detail = kind.detail {
                Text(detail)
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(Ink.surface.opacity(0.8))
              }
            }

            Spacer()

            if !kind.showsProgress {
              Image(systemName: "chevron.right")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.surface.opacity(0.7))
            }
          }
        }
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .fill(Ink.primary)
        )
        .shadow(color: Ink.primary.opacity(glowAnimating ? 0.7 : 0.3), radius: 8)
      }
      .buttonStyle(.plain)
      .help(isCollapsed ? kind.accessibilityLabel : "")
      .accessibilityIdentifier("desktop-update-status-banner")
      .accessibilityLabel(kind.accessibilityLabel)
      .onAppear {
        OmiMotion.withGated(.easeInOut(duration: 1.2).repeatForever(autoreverses: true)) {
          glowAnimating = true
        }
      }
    }
  }
}
