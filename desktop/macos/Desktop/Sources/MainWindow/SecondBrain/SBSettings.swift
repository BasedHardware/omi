import OmiTheme
import SwiftUI

/// Second Brain settings landing: the design's five groups (YOU · CAPTURE ·
/// ASSISTANT · CONNECT · SYSTEM). Each row routes to the real, working control —
/// either a legacy settings section (full functionality preserved) or an overflow
/// page — so nothing is a dead end. Copy is verbatim from the design.
struct SBSettingsLanding: View {
  @Environment(\.sbTheme) private var sb
  @ObservedObject var appState: AppState

  /// Open a legacy settings section (real controls).
  var onOpenSection: (SettingsContentView.SettingsSection) -> Void
  /// Navigate to an overflow page by SidebarNavItem raw value.
  var onNavigate: (Int) -> Void
  /// Open the native Account & Billing page.
  var onOpenAccount: () -> Void
  var onReplayOnboarding: () -> Void

  private struct Row: Identifiable {
    let id = UUID()
    let name: String
    let sub: String
    let value: String
    let go: () -> Void
  }
  private struct Group: Identifiable {
    let id = UUID()
    let header: String
    let rows: [Row]
  }

  private var grantedCount: Int {
    [
      appState.hasMicrophonePermission, appState.hasSystemAudioPermission,
      appState.hasScreenRecordingPermission, appState.hasFullDiskAccess,
      appState.hasAccessibilityPermission, appState.hasAutomationPermission,
    ].filter { $0 }.count
  }

  private var groups: [Group] {
    [
      Group(header: "YOU", rows: [
        Row(name: "Account & Billing", sub: "signed in · Unlimited", value: "Pro") { onOpenAccount() },
        Row(name: "Memory", sub: "everything I know — each fact links to its source", value: "›") {
          onNavigate(SidebarNavItem.memories.rawValue)
        },
        Row(name: "Permissions", sub: "mic · screen · automation — health at a glance", value: "\(grantedCount) of 6") {
          onNavigate(SidebarNavItem.permissions.rawValue)
        },
      ]),
      Group(header: "CAPTURE", rows: [
        Row(name: "Transcription", sub: "on-device (Parakeet) · bring your own key", value: "on-device") {
          onOpenSection(.transcription)
        },
        Row(name: "Screen history", sub: "Rewind storage · retention", value: "›") {
          onNavigate(SidebarNavItem.rewind.rawValue)
        },
        Row(name: "Privacy rules", sub: "per-app capture rules · notch-only notifications", value: "quiet") {
          onOpenSection(.privacy)
        },
      ]),
      Group(header: "ASSISTANT", rows: [
        Row(name: "Notch bar & voice", sub: "⌘⇧O to summon · hold fn to talk · snooze 2h", value: "⌘⇧O") {
          onOpenSection(.floatingBar)
        },
        Row(name: "Proactive nudges", sub: "promises, focus, screen context", value: "›") {
          onOpenSection(.advanced)
        },
      ]),
      Group(header: "CONNECT", rows: [
        Row(name: "Sources", sub: "Gmail · Google Calendar · Apple Notes · local files", value: "›") {
          onOpenSection(.advanced)
        },
        Row(name: "Task export", sub: "Apple Reminders · Todoist · Google Tasks · ClickUp · Asana", value: "›") {
          onOpenSection(.advanced)
        },
        Row(name: "AI agents", sub: "ChatGPT · Claude Code · Gemini · OpenClaw · Hermes", value: "›") {
          onOpenSection(.advanced)
        },
        Row(name: "Memory export", sub: "Notion · Obsidian — your memories, your vault", value: "›") {
          onOpenSection(.advanced)
        },
        Row(name: "Apps", sub: "summarizers, personas, 250+ community apps", value: "›") {
          onNavigate(SidebarNavItem.apps.rawValue)
        },
      ]),
      Group(header: "SYSTEM", rows: [
        Row(name: "General", sub: "login · language · updates · shortcuts · advanced", value: "›") {
          onOpenSection(.general)
        },
      ]),
    ]
  }

  private let columns = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
          ForEach(groups) { group in
            groupCard(group)
          }
        }
        Button(action: onReplayOnboarding) {
          Text("Replay onboarding")
            .geist(size: 13).foregroundStyle(sb.ink(.w35)).underline()
        }
        .buttonStyle(.plain)
        .padding(.top, 16)
      }
      .padding(.horizontal, 30).padding(.top, 4).padding(.bottom, 24)
    }
  }

  private func groupCard(_ group: Group) -> some View {
    VStack(alignment: .leading, spacing: 0) {
      Text(group.header)
        .geistMono(size: 11.5, weight: .medium, tracking: 11.5 * 0.1)
        .foregroundStyle(sb.ink(.w35))
        .padding(.bottom, 6)
      ForEach(Array(group.rows.enumerated()), id: \.element.id) { idx, row in
        Button(action: row.go) {
          HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 1) {
              Text(row.name).geist(size: 14).foregroundStyle(sb.ink(.w9))
              Text(row.sub).geist(size: 12).foregroundStyle(sb.ink(.w38)).lineLimit(1)
            }
            Spacer(minLength: 6)
            Text(row.value).geistMono(size: 12).foregroundStyle(sb.ink(.w45))
          }
          .padding(.vertical, 9)
          .contentShape(Rectangle())
          .overlay(alignment: .top) {
            if idx > 0 { Rectangle().fill(sb.ink(.w06)).frame(height: 1) }
          }
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, 16).padding(.vertical, 14)
    .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(sb.ink(.w04)))
    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(sb.ink(.w09), lineWidth: 1))
  }
}
