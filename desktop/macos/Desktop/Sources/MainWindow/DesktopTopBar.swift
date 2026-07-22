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
  @ObservedObject var tasksStore: TasksStore
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
    tasksStore.tasks.filter { $0.createdAt > sinceDate && $0.deleted != true }.count
  }

  var body: some View {
    HStack(spacing: OmiSpacing.md) {
      navPills
      Spacer(minLength: OmiSpacing.md)
      CaptureListeningControls(appState: appState, onRewind: onRewind)
        .anchorPreference(key: SidebarCoachAnchorKey.self, value: .bounds) {
          [SidebarCoachAnchorKey.captureAnchorID: $0]
        }
    }
    .frame(height: 44)
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm)
  }

  private var navPills: some View {
    // Flat, containerless nav so the bar blends with the chat page: unselected
    // items are muted text; the selected item gets a subtle highlight only.
    HStack(spacing: OmiSpacing.xs) {
      ForEach(navItems) { item in
        Button {
          OmiMotion.withGated(.easeOut(duration: 0.08)) { selectedIndex = item.index }
        } label: {
          HStack(spacing: 6) {
            Image(systemName: item.icon)
              .scaledFont(size: OmiType.caption, weight: .semibold)
            Text(item.title)
              .scaledFont(size: OmiType.caption, weight: .semibold)
            // New-item badge lives on the button it belongs to (Memory =
            // memories + conversations, Tasks = tasks) since Omi was last front.
            if newCount(for: item) > 0 {
              Text("+\(newCount(for: item))")
                .scaledFont(size: OmiType.micro, weight: .bold)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 5)
                .padding(.vertical, 1)
                .background(Capsule(style: .continuous).fill(OmiColors.textPrimary.opacity(0.16)))
            }
          }
          .foregroundColor(selectedIndex == item.index ? OmiColors.textPrimary : OmiColors.textTertiary)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, 6)
          .background(
            Capsule(style: .continuous)
              .fill(selectedIndex == item.index ? OmiColors.textPrimary.opacity(0.08) : Color.clear)
          )
          .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .help(item.title)
        // Publish each pill's frame so the post-onboarding walkthrough can
        // spotlight it (the coach-marks used to anchor to the old nav rail).
        .anchorPreference(key: SidebarCoachAnchorKey.self, value: .bounds) { [item.index: $0] }
      }
    }
  }

  /// New-item count to badge on a nav button (since Omi was last in front).
  /// The Memory hub holds both memories and conversations, so its badge sums
  /// them; Tasks badges new tasks. Home/Apps have no counter.
  private func newCount(for item: NavItem) -> Int {
    switch item.index {
    case SidebarNavItem.conversations.rawValue: return newMemories + newConversations
    case SidebarNavItem.tasks.rawValue: return newTasks
    default: return 0
    }
  }
}
