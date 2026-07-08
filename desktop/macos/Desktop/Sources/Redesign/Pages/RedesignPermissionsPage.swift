import AppKit
import SwiftUI

/// The redesigned "what I can reach — and why" permissions page — mockup
/// `permissions.html`, light-wired. Reads real granted flags off `AppState`
/// and each "Turn on" button calls the real request/open method.
struct RedesignPermissionsPage: View {
  @ObservedObject var appState: AppState

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        Text("PERMISSIONS").inkEyebrow()

        VStack(alignment: .leading, spacing: 8) {
          Text("What I can reach — and why.").inkH1()
          Text(
            "Each one unlocks something for you. Turn any of them off whenever you like; I'll just do less."
          )
          .inkSmall()
          .frame(maxWidth: 520, alignment: .leading)
          .fixedSize(horizontal: false, vertical: true)
        }

        VStack(spacing: 14) {
          PermissionCard(
            icon: "display",
            name: "Screen",
            benefit:
              "So I can see what you see and act on it — draft that reply, catch that promise.",
            granted: appState.hasScreenRecordingPermission
          ) {
            // Open Settings first so it's visible before the system dialog steals focus.
            appState.openScreenRecordingPreferences()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
              appState.triggerScreenRecordingPermission()
            }
          }

          PermissionCard(
            icon: "mic",
            name: "Microphone",
            benefit: "So I never miss what's said in a meeting or a call.",
            granted: appState.hasMicrophonePermission
          ) {
            NSApp.activate()
            appState.requestMicrophonePermission()
          }

          PermissionCard(
            icon: "externaldrive",
            name: "Full Disk",
            benefit: "So I can read the docs you point me at, right on your Mac.",
            granted: appState.hasFullDiskAccess
          ) {
            if let url = URL(
              string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
            {
              NSWorkspace.shared.open(url)
            }
          }

          PermissionCard(
            icon: "bolt",
            name: "Accessibility",
            benefit: "So I can act for you — click send, open the right app — when you ask.",
            granted: appState.hasAccessibilityPermission
          ) {
            appState.triggerAccessibilityPermission()
          }
        }

        HStack(spacing: 8) {
          Image(systemName: "lock").font(.system(size: 12)).foregroundColor(Ink.faint)
          Text(
            "Everything these unlock stays on your Mac. Read the source code to see exactly what I do with it."
          )
          .inkCaption()
          .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 8)
      }
      .frame(maxWidth: 760, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .onAppear { appState.checkAllPermissions() }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) {
      _ in
      // Re-check when returning from System Settings so a fresh grant flips the card.
      appState.checkAllPermissions()
    }
  }
}

// MARK: - Permission card

private struct PermissionCard: View {
  let icon: String
  let name: String
  let benefit: String
  let granted: Bool
  let turnOn: () -> Void

  var body: some View {
    HStack(alignment: .top, spacing: 16) {
      // Icon tile
      ZStack {
        RoundedRectangle(cornerRadius: 11, style: .continuous)
          .fill(granted ? Ink.surface2 : Ink.warn.opacity(0.10))
          .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
              .strokeBorder(granted ? Ink.hair : .clear, lineWidth: 1)
          )
          .frame(width: 42, height: 42)
        Image(systemName: icon)
          .font(.system(size: 17, weight: .medium))
          .foregroundColor(granted ? Ink.body : Ink.warn)
      }

      VStack(alignment: .leading, spacing: 4) {
        Text(name).font(InkFont.sans(15, .medium)).foregroundColor(Ink.ink)
        Text(benefit)
          .font(InkFont.sans(13)).foregroundColor(Ink.muted)
          .frame(maxWidth: 460, alignment: .leading)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer(minLength: 12)

      if granted {
        HStack(spacing: 6) {
          Image(systemName: "checkmark").font(.system(size: 11, weight: .semibold))
          Text("On").font(InkFont.sans(13, .medium))
        }
        .foregroundColor(Ink.live)
        .padding(.top, 2)
      } else {
        InkButton(title: "Turn on", kind: .accent, size: .sm) { turnOn() }
      }
    }
    .padding(22)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .strokeBorder(granted ? Ink.hair : Ink.warn, lineWidth: 1)
        )
    )
  }
}
