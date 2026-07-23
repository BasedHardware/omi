import AppKit
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
  /// Leading inset that clears the window traffic lights when the bar rides in
  /// the hidden-titlebar band with no sidebar to its left.
  var leadingInset: CGFloat = 0
  /// When true the leading chip reads "Back to app" and closes settings; when
  /// false it reads "Settings" and opens them. Same control, it just morphs.
  var isInSettings: Bool = false
  let onRewind: () -> Void
  /// Toggles the settings sidebar open/closed. Owned by DesktopHomeView so the
  /// back-navigation target (previous tab) stays correct.
  var onToggleSettings: () -> Void = {}

  /// Drives the sliding selection inside the segmented nav control.
  @Namespace private var navSegmentNamespace

  private static let logoImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png") else {
      return nil
    }
    return NSImage(contentsOf: url)
  }()

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
    VStack(spacing: OmiSpacing.xs) {
      // Row 1 — toolbar aligned with the traffic lights: the Settings chip sits
      // by them (only while closed — in settings "Back to app" lives on the
      // sidebar glass), the Omi identity is centered, capture on the right.
      ZStack {
        omiIdentity

        HStack(spacing: OmiSpacing.md) {
          if !isInSettings {
            settingsChip
              .padding(.leading, leadingInset)
              .transition(.opacity)
          }
          Spacer(minLength: OmiSpacing.md)
          CaptureListeningControls(appState: appState, onRewind: onRewind)
        }
      }
      .frame(height: 34)

      // Row 2 — the segmented primary nav, centered below the identity.
      navPills
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.top, 10)
    .padding(.bottom, OmiSpacing.sm)
    .background(WindowDragArea())
  }

  /// The app identity beside the window controls: mark + wordmark, centered.
  private var omiIdentity: some View {
    HStack(spacing: OmiSpacing.xs) {
      if let logo = Self.logoImage {
        Image(nsImage: logo)
          .resizable()
          .scaledToFit()
          .frame(width: 18, height: 18)
      }
      Text("Omi")
        .scaledFont(size: OmiType.subheading, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
    }
    .allowsHitTesting(false)
  }

  /// Opens settings. It sits by the traffic lights; when settings is open the
  /// matching "Back to app" control lives on the sidebar glass instead.
  private var settingsChip: some View {
    Button(action: onToggleSettings) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "gearshape")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .frame(width: 18, height: 18)
        Text("Settings")
          .scaledFont(size: OmiType.caption, weight: .semibold)
      }
      .foregroundColor(OmiColors.textTertiary)
      .padding(.horizontal, OmiSpacing.md)
      .frame(height: 34)
      .background(
        Capsule(style: .continuous)
          .fill(Color.white.opacity(0.05))
          .overlay(Capsule(style: .continuous).stroke(Color.white.opacity(0.07), lineWidth: 1))
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .help("Settings")
  }

  private var navPills: some View {
    // Segmented control: one rounded track holds the four primary tabs and the
    // selected segment's fill slides between them via matchedGeometry, so it
    // reads as a single native control instead of loose pills.
    HStack(spacing: 2) {
      ForEach(navItems) { item in
        navSegment(item)
      }
    }
    .padding(3)
    .background(
      Capsule(style: .continuous)
        .fill(Color.white.opacity(0.05))
        .overlay(
          Capsule(style: .continuous)
            .stroke(Color.white.opacity(0.07), lineWidth: 1)
        )
    )
  }

  private func navSegment(_ item: NavItem) -> some View {
    let isSelected = selectedIndex == item.index
    return Button {
      OmiMotion.withGated(.spring(response: 0.32, dampingFraction: 0.82)) {
        selectedIndex = item.index
      }
    } label: {
      HStack(spacing: 6) {
        Image(systemName: item.icon)
          .scaledFont(size: OmiType.caption, weight: .semibold)
        Text(item.title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
        // New-item badge lives on the segment it belongs to (Memory =
        // memories + conversations, Tasks = tasks) since Omi was last front.
        if newCount(for: item) > 0 {
          Text("+\(newCount(for: item))")
            .scaledFont(size: OmiType.micro, weight: .bold)
            .foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
            .background(Capsule(style: .continuous).fill(OmiColors.textPrimary.opacity(0.18)))
        }
      }
      .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, 6)
      .background {
        if isSelected {
          Capsule(style: .continuous)
            .fill(Color.white.opacity(0.12))
            .matchedGeometryEffect(id: "navSegment", in: navSegmentNamespace)
        }
      }
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .help(item.title)
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

/// Lets the user drag the window by the top bar's empty areas, the way a native
/// toolbar behaves. Controls on top keep their own clicks; only the gaps drag.
private struct WindowDragArea: NSViewRepresentable {
  func makeNSView(context: Context) -> NSView { DragView() }
  func updateNSView(_ nsView: NSView, context: Context) {}

  private final class DragView: NSView {
    override var mouseDownCanMoveWindow: Bool { true }
  }
}
