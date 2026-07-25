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
  let onRewind: () -> Void
  @AppStorage(MemoryHubDestination.storageKey) private var memoryDestinationRawValue =
    MemoryHubDestination.memories.rawValue
  @State private var memoryMenuHoverIntent = MemoryMenuHoverIntent()
  @State private var memoryMenuHoverTask: Task<Void, Never>?

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
      settingsButton
    }
    .frame(height: 44)
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm)
  }

  /// Gear that opens Settings. The old left rail held the settings/profile entry;
  /// with the rail gone this is the only visible way in (⌘, still works too).
  private var settingsButton: some View {
    let isActive = selectedIndex == SidebarNavItem.settings.rawValue
    return Button {
      OmiMotion.withGated(.easeOut(duration: 0.08)) {
        selectedIndex = SidebarNavItem.settings.rawValue
      }
    } label: {
      Image(systemName: "gearshape")
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(isActive ? OmiColors.textPrimary : OmiColors.textTertiary)
        .frame(width: 32, height: 32)
        .background(Circle().fill(isActive ? OmiColors.textPrimary.opacity(0.08) : Color.clear))
        .contentShape(Circle())
    }
    .buttonStyle(.plain)
    .help("Settings")
  }

  private var navPills: some View {
    // Flat, containerless nav so the bar blends with the chat page: unselected
    // items are muted text; the selected item gets a subtle highlight only.
    HStack(spacing: OmiSpacing.xs) {
      ForEach(navItems) { item in
        if item.index == SidebarNavItem.conversations.rawValue {
          Button {
            memoryMenuHoverTask?.cancel()
            memoryMenuHoverIntent.openImmediately()
          } label: {
            navLabel(for: item, showsDisclosure: true)
          }
          .buttonStyle(.plain)
          .fixedSize()
          .background {
            NativeMemoryNavigationMenuPresenter(
              presentationRequest: memoryMenuHoverIntent.presentationRequest,
              selectedDestination: memoryDestination,
              onSelect: selectMemoryDestination
            )
            .allowsHitTesting(false)
          }
          .onHover(perform: memoryMenuHoverChanged)
          .help("Choose a Memory view — opens on hover")
        } else {
          Button {
            OmiMotion.withGated(.easeOut(duration: 0.08)) { selectedIndex = item.index }
          } label: {
            navLabel(for: item)
          }
          .buttonStyle(.plain)
          .help(item.title)
        }
      }
    }
  }

  private var memoryDestination: MemoryHubDestination {
    MemoryHubDestination(rawValue: memoryDestinationRawValue) ?? .memories
  }

  private func selectMemoryDestination(_ destination: MemoryHubDestination) {
    memoryDestinationRawValue = destination.rawValue
    OmiMotion.withGated(.easeOut(duration: 0.08)) {
      selectedIndex = SidebarNavItem.conversations.rawValue
    }
  }

  private func memoryMenuHoverChanged(_ isHovering: Bool) {
    memoryMenuHoverTask?.cancel()
    guard let generation = memoryMenuHoverIntent.hoverChanged(isHovering) else {
      memoryMenuHoverTask = nil
      return
    }

    memoryMenuHoverTask = Task { @MainActor in
      try? await Task.sleep(for: .milliseconds(140))
      guard !Task.isCancelled else { return }
      memoryMenuHoverIntent.openAfterHoverDelay(generation: generation)
    }
  }

  private func navLabel(for item: NavItem, showsDisclosure: Bool = false) -> some View {
    HStack(spacing: 6) {
      Image(systemName: item.icon)
        .scaledFont(size: OmiType.caption, weight: .semibold)
      Text(item.title)
        .scaledFont(size: OmiType.caption, weight: .semibold)
      if showsDisclosure {
        Image(systemName: "chevron.down")
          .scaledFont(size: 8, weight: .bold)
          .foregroundStyle(OmiColors.textQuaternary)
      }
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

/// A deliberately tiny AppKit bridge: SwiftUI owns selection and hover intent;
/// AppKit owns only native menu construction and tracking.
private struct NativeMemoryNavigationMenuPresenter: NSViewRepresentable {
  let presentationRequest: Int
  let selectedDestination: MemoryHubDestination
  let onSelect: @MainActor (MemoryHubDestination) -> Void

  func makeCoordinator() -> Coordinator {
    Coordinator(onSelect: onSelect)
  }

  func makeNSView(context: Context) -> NSView {
    let view = NSView()
    view.setAccessibilityElement(false)
    return view
  }

  func updateNSView(_ nsView: NSView, context: Context) {
    context.coordinator.onSelect = onSelect
    guard presentationRequest != context.coordinator.lastPresentationRequest else { return }
    context.coordinator.lastPresentationRequest = presentationRequest
    context.coordinator.presentMenu(
      selectedDestination: selectedDestination,
      relativeTo: nsView
    )
  }

  @MainActor
  final class Coordinator: NSObject {
    var onSelect: @MainActor (MemoryHubDestination) -> Void
    var lastPresentationRequest = 0

    init(onSelect: @escaping @MainActor (MemoryHubDestination) -> Void) {
      self.onSelect = onSelect
    }

    func presentMenu(
      selectedDestination: MemoryHubDestination,
      relativeTo anchorView: NSView
    ) {
      let menu = NSMenu(title: "Memory")
      menu.autoenablesItems = false
      menu.minimumWidth = 190

      for destination in MemoryHubDestination.allCases {
        let item = NSMenuItem(
          title: destination.title,
          action: #selector(selectDestination(_:)),
          keyEquivalent: ""
        )
        item.target = self
        item.tag = destination.rawValue
        item.state = destination == selectedDestination ? .on : .off
        item.image = NSImage(
          systemSymbolName: destination.icon,
          accessibilityDescription: destination.title
        )
        menu.addItem(item)
      }

      menu.popUp(
        positioning: menu.items.first(where: { $0.state == .on }),
        at: NSPoint(x: 0, y: -4),
        in: anchorView
      )
    }

    @objc private func selectDestination(_ sender: NSMenuItem) {
      guard let destination = MemoryHubDestination(rawValue: sender.tag) else { return }
      onSelect(destination)
    }
  }
}
