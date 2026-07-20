import AppKit
import OmiTheme
import SwiftUI

// MARK: - Permissions health

/// Plain-words permission health. Read-only status per the design; a "Fix" action
/// opens the relevant System Settings pane when a permission isn't granted.
struct SBPermissionsPage: View {
  @Environment(\.sbTheme) private var sb
  @ObservedObject var appState: AppState

  private struct Perm {
    let name: String
    let why: String
    let granted: Bool
    let fix: () -> Void
  }

  private var perms: [Perm] {
    [
      Perm(name: "Microphone", why: "hears your side of conversations",
        granted: appState.hasMicrophonePermission, fix: { appState.requestMicrophonePermission() }),
      Perm(name: "System audio", why: "hears the other side — Zoom, Meet, calls",
        granted: appState.hasSystemAudioPermission, fix: { appState.triggerSystemAudioPermission() }),
      Perm(name: "Screen Recording", why: "sees what you see · stays on this Mac",
        granted: appState.hasScreenRecordingPermission, fix: { appState.openScreenRecordingPreferences() }),
      Perm(name: "Full Disk Access", why: "answers can cite your files",
        granted: appState.hasFullDiskAccess, fix: { Self.openPane("Privacy_AllFiles") }),
      Perm(name: "Accessibility", why: "global shortcuts, dictation anywhere",
        granted: appState.hasAccessibilityPermission && !appState.isAccessibilityBroken,
        fix: { appState.triggerAccessibilityPermission() }),
      Perm(name: "Automation", why: "lets me act — calendar, reminders, mail",
        granted: appState.hasAutomationPermission, fix: { Self.openPane("Privacy_Automation") }),
    ]
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        SBSectionLabel(text: "Permission health").padding(.bottom, 2)
        ForEach(Array(perms.enumerated()), id: \.offset) { _, p in
          HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 1) {
              Text(p.name).geist(size: 15).foregroundStyle(sb.ink(.w9))
              Text(p.why).geist(size: 12.5).foregroundStyle(sb.ink(.w38))
            }
            Spacer(minLength: 8)
            if p.granted {
              Text("✓ granted").geistMono(size: 12.5).foregroundStyle(sb.ink(.w6))
            } else {
              Button(action: p.fix) {
                Text("Fix").geistMono(size: 12.5).foregroundStyle(sb.ink(.w6)).underline()
              }
              .buttonStyle(.plain)
            }
          }
          .padding(.vertical, 11)
          .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }
        }
        Text("If macOS revokes something, this page shows Fix / Reset — one click, plain words.")
          .geist(size: 12.5).foregroundStyle(sb.ink(.w32)).padding(.top, 12)
      }
      .padding(.horizontal, 30).padding(.bottom, 24)
    }
    .onAppear { appState.checkAllPermissions() }
  }

  private static func openPane(_ pane: String) {
    if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(pane)") {
      NSWorkspace.shared.open(url)
    }
  }
}

// MARK: - Memories

struct SBMemoriesContainer: View {
  @Environment(\.sbTheme) private var sb
  @ObservedObject var memoriesViewModel: MemoriesViewModel

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        SBSectionLabel(text: "What I know").padding(.bottom, 2)
        if memoriesViewModel.memories.isEmpty {
          Text("Nothing yet — I fill this in as I listen.")
            .geist(size: 14).foregroundStyle(sb.ink(.w35)).padding(.vertical, 14)
        }
        ForEach(memoriesViewModel.memories) { memory in
          HStack(spacing: 12) {
            Text(memory.content).geist(size: 15).foregroundStyle(sb.ink(.w85))
            Spacer(minLength: 8)
            Text(tagLabel(memory)).geistMono(size: 12.5).foregroundStyle(sb.ink(.w35))
          }
          .padding(.vertical, 11)
          .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }
          .contextMenu {
            Button("Delete", role: .destructive) {
              Task { await memoriesViewModel.deleteMemory(memory) }
            }
          }
        }
        Text("Every memory is editable and deletable — and each one links back to the conversation it came from.")
          .geist(size: 12.5).foregroundStyle(sb.ink(.w32)).padding(.top, 12)
      }
      .padding(.horizontal, 30).padding(.bottom, 24)
    }
    .task { await memoriesViewModel.loadMemoriesIfNeeded() }
  }

  private func tagLabel(_ memory: ServerMemory) -> String {
    if let first = memory.tags.first, !first.isEmpty { return first }
    return memory.category.rawValue
  }
}

// MARK: - Apps

struct SBAppsContainer: View {
  @Environment(\.sbTheme) private var sb
  @ObservedObject var appProvider: AppProvider

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        SBSectionLabel(text: "Installed").padding(.bottom, 2)
        let installed = appProvider.enabledApps.isEmpty ? Array(appProvider.apps.prefix(8)) : appProvider.enabledApps
        if installed.isEmpty {
          Text("No apps installed yet.").geist(size: 14).foregroundStyle(sb.ink(.w35)).padding(.vertical, 14)
        }
        ForEach(installed) { app in
          HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 1) {
              Text(app.name).geist(size: 15).foregroundStyle(sb.ink(.w9))
              Text(app.description).geist(size: 12.5).foregroundStyle(sb.ink(.w38)).lineLimit(1)
            }
            Spacer(minLength: 8)
            Text(app.enabled ? "on" : "off").geistMono(size: 12.5).foregroundStyle(sb.ink(.w45))
          }
          .padding(.vertical, 11)
          .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }
        }
        Text("Browse 250+ community apps and personas →")
          .geist(size: 12.5).foregroundStyle(sb.ink(.w32)).padding(.top, 12)
      }
      .padding(.horizontal, 30).padding(.bottom, 24)
    }
    .task { await appProvider.fetchEnabledApps() }
  }
}
