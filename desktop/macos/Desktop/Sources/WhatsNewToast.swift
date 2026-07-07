import AppKit
import SwiftUI
import OmiTheme

/// Drives the in-app "what's new" card that appears in the bottom-right corner of
/// the main window the first time the app launches on a newer build (i.e. right
/// after a Sparkle update). Tapping it opens the release notes for the running
/// version; the (x) button or the auto-dismiss timer hides it.
@MainActor
final class WhatsNewToast: ObservableObject {
  static let shared = WhatsNewToast()

  /// Version string to show, e.g. "0.11.476". `nil` means the card is hidden.
  @Published var version: String?

  /// Highest build number we've already announced. 0 / unset means "no baseline yet".
  private let lastShownBuildKey = "whatsNewLastShownBuild"

  private init() {}

  /// Show the card once when the running build is newer than the last one we
  /// announced. Records a baseline silently on the first tracked launch so we
  /// never show it on a fresh install — only after a real update.
  func presentIfUpdated() {
    guard AuthState.shared.isSignedIn else { return }  // re-evaluate on a later launch
    guard let current = Self.currentBuild else { return }

    let defaults = UserDefaults.standard
    let last = defaults.integer(forKey: lastShownBuildKey)
    if last == 0 {
      defaults.set(current, forKey: lastShownBuildKey)
      return
    }
    guard current > last else { return }
    defaults.set(current, forKey: lastShownBuildKey)
    present(version: Self.currentVersion)
  }

  func present(version: String) {
    self.version = version
  }

  func dismiss() {
    version = nil
  }

  private static var currentBuild: Int? {
    (Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String).flatMap(Int.init)
  }

  private static var currentVersion: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
  }
}

/// Bottom-right corner overlay for the main window. Attach with
/// `.overlay(alignment: .bottomTrailing) { WhatsNewToastOverlay() }`.
struct WhatsNewToastOverlay: View {
  @ObservedObject private var model = WhatsNewToast.shared
  private let autoDismissSeconds: UInt64 = 12

  var body: some View {
    ZStack(alignment: .bottomTrailing) {
      if let version = model.version {
        WhatsNewToastCard(
          version: version,
          onOpen: {
            if let url = URL(string: AppBuild.changelogURLString) {
              NSWorkspace.shared.open(url)
            }
            model.dismiss()
          },
          onClose: { model.dismiss() }
        )
        .padding(20)
        .transition(.move(edge: .trailing).combined(with: .opacity))
        .task(id: version) {
          try? await Task.sleep(nanoseconds: autoDismissSeconds * 1_000_000_000)
          if !Task.isCancelled { model.dismiss() }
        }
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
    .allowsHitTesting(model.version != nil)
    .animation(.spring(response: 0.4, dampingFraction: 0.85), value: model.version)
  }
}

private struct WhatsNewToastCard: View {
  let version: String
  let onOpen: () -> Void
  let onClose: () -> Void

  var body: some View {
    HStack(alignment: .top, spacing: 12) {
      logo

      VStack(alignment: .leading, spacing: 2) {
        HStack(alignment: .top, spacing: 8) {
          Text("omi updated")
            .scaledFont(size: 14, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Spacer(minLength: 0)
          closeButton
        }

        Text(version.isEmpty ? "A new version is installed" : "Now on version \(version)")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)

        HStack(spacing: 4) {
          Text("See what's new")
            .scaledFont(size: 12, weight: .medium)
            .foregroundColor(OmiColors.purpleSecondary)
          Image(systemName: "arrow.up.right")
            .scaledFont(size: 10, weight: .semibold)
            .foregroundColor(OmiColors.purpleSecondary)
        }
        .padding(.top, 3)
      }
    }
    .padding(14)
    .frame(width: 304, alignment: .topLeading)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(OmiColors.backgroundRaised)
    )
    .overlay(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .stroke(OmiColors.border, lineWidth: 1)
    )
    .shadow(color: .black.opacity(0.35), radius: 16, y: 6)
    .contentShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    .onTapGesture { onOpen() }
  }

  private var logo: some View {
    Group {
      if let url = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
        let image = NSImage(contentsOf: url)
      {
        Image(nsImage: image).resizable().aspectRatio(contentMode: .fit)
      } else {
        Image(systemName: "sparkles").resizable().aspectRatio(contentMode: .fit)
          .foregroundColor(OmiColors.purplePrimary)
      }
    }
    .frame(width: 34, height: 34)
  }

  private var closeButton: some View {
    Button(action: onClose) {
      Image(systemName: "xmark")
        .scaledFont(size: 10, weight: .bold)
        .foregroundColor(OmiColors.textTertiary)
        .padding(4)
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .help("Dismiss")
  }
}
