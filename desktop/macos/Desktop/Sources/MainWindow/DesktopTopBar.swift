import OmiTheme
import SwiftUI

/// The constant floating top bar that replaces the left nav rail: primary
/// navigation (Home / Memory / Tasks / Apps), a "new since you were last here"
/// counter (conversations · memories · tasks created while Omi wasn't in front),
/// and the Capture/Listening controls on the right.
struct DesktopTopBar: View {
  @Binding var selectedIndex: Int
  @ObservedObject var appState: AppState
  @ObservedObject var memoriesViewModel: MemoriesViewModel
  @ObservedObject var tasksViewModel: TasksViewModel
  /// Items created after this instant count as "new" — updated whenever Omi
  /// last resigned front (see DesktopHomeView).
  let sinceDate: Date
  let onRewind: () -> Void

  private struct NavItem: Identifiable {
    let index: Int
    let title: String
    let icon: String
    var id: Int { index }
  }

  private var navItems: [NavItem] {
    [
      NavItem(index: SidebarNavItem.dashboard.rawValue, title: "Home", icon: "house.fill"),
      NavItem(index: SidebarNavItem.conversations.rawValue, title: "Memory", icon: "brain"),
      NavItem(index: SidebarNavItem.tasks.rawValue, title: "Tasks", icon: "checklist"),
      NavItem(index: SidebarNavItem.apps.rawValue, title: "Apps", icon: "puzzlepiece.fill"),
    ]
  }

  private var newConversations: Int {
    appState.conversations.filter { $0.createdAt > sinceDate && $0.deleted != true }.count
  }
  private var newMemories: Int {
    memoriesViewModel.memories.filter { $0.createdAt > sinceDate }.count
  }
  private var newTasks: Int {
    tasksViewModel.tasks.filter { $0.createdAt > sinceDate && $0.deleted != true }.count
  }

  var body: some View {
    HStack(spacing: OmiSpacing.md) {
      navPills
      countsPill
      Spacer(minLength: OmiSpacing.md)
      CaptureListeningControls(appState: appState, onRewind: onRewind)
    }
    .padding(.horizontal, OmiSpacing.xl)
    .padding(.top, OmiSpacing.lg)
    .padding(.bottom, OmiSpacing.xs)
  }

  private var navPills: some View {
    HStack(spacing: 2) {
      ForEach(navItems) { item in
        Button {
          OmiMotion.withGated(.easeOut(duration: 0.08)) { selectedIndex = item.index }
        } label: {
          HStack(spacing: 6) {
            Image(systemName: item.icon)
              .scaledFont(size: OmiType.caption, weight: .semibold)
            Text(item.title)
              .scaledFont(size: OmiType.caption, weight: .semibold)
          }
          .foregroundColor(selectedIndex == item.index ? OmiColors.textPrimary : OmiColors.textTertiary)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, 6)
          .background(
            Capsule(style: .continuous)
              .fill(selectedIndex == item.index ? OmiColors.backgroundTertiary : Color.clear)
          )
          .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .help(item.title)
      }
    }
    .padding(3)
    .background(Capsule(style: .continuous).fill(OmiColors.backgroundSecondary))
  }

  @ViewBuilder private var countsPill: some View {
    let parts: [(count: Int, label: String)] = [
      (newConversations, newConversations == 1 ? "conversation" : "conversations"),
      (newMemories, newMemories == 1 ? "memory" : "memories"),
      (newTasks, newTasks == 1 ? "task" : "tasks"),
    ].filter { $0.count > 0 }

    if !parts.isEmpty {
      HStack(spacing: OmiSpacing.sm) {
        ForEach(Array(parts.enumerated()), id: \.offset) { index, part in
          if index > 0 {
            Text("·")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary.opacity(0.6))
          }
          HStack(spacing: 4) {
            Text("+\(part.count)")
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text(part.label)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, 5)
      .background(Capsule(style: .continuous).fill(OmiColors.backgroundSecondary.opacity(0.6)))
      .help("New since Omi was last in front")
      .transition(.opacity)
    }
  }
}
