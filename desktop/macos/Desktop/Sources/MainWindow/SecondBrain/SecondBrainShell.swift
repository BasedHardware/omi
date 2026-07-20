import OmiTheme
import SwiftUI

/// The Second Brain main-window shell: ridgeline wallpaper, a centered glass
/// column, three text tabs (Today · Conversations · Follow-ups) with a `···`
/// overflow menu + ⌘K + Settings, and a persistent bottom ask bar.
///
/// This replaces the legacy sidebar + PageChromeBar chrome. It owns NO business
/// logic — navigation drives the same `selectedIndex` (mapped to `SidebarNavItem`
/// raw values) so automation, notifications, and tier gating keep working. The
/// page body itself is supplied by the caller via `content`.
struct SecondBrainShell<Content: View>: View {
  @Environment(\.sbTheme) private var sb

  @Binding var selectedIndex: Int
  /// Logo spins only while Omi is actively working (listening / thinking).
  var isWorking: Bool

  // Ask bar wiring (supplied by the host).
  @Binding var askText: String
  var onSubmitAsk: () -> Void
  var onOpenChats: () -> Void
  var onVoice: () -> Void
  var onOpenPalette: () -> Void
  var onOpenSettings: () -> Void

  @ViewBuilder var content: () -> Content

  // Primary tabs → SidebarNavItem raw values.
  private var tabs: [(title: String, index: Int)] {
    [
      ("Today", SidebarNavItem.dashboard.rawValue),
      ("Conversations", SidebarNavItem.conversations.rawValue),
      ("Follow-ups", SidebarNavItem.tasks.rawValue),
    ]
  }

  // Overflow destinations (verbatim order from the design).
  private var overflow: [(title: String, index: Int)] {
    [
      ("Memories", SidebarNavItem.memories.rawValue),
      ("Rewind", SidebarNavItem.rewind.rawValue),
      ("Focus", SidebarNavItem.focus.rawValue),
      ("Insights", SidebarNavItem.insight.rawValue),
      ("Apps", SidebarNavItem.apps.rawValue),
      ("Permissions", SidebarNavItem.permissions.rawValue),
    ]
  }

  private var isSettings: Bool { selectedIndex == SidebarNavItem.settings.rawValue }

  var body: some View {
    ZStack {
      SBWallpaper()

      VStack(spacing: 0) {
        topBar
        navBar
        // Centered readable column.
        content()
          .frame(maxWidth: 780, maxHeight: .infinity, alignment: .top)
          .frame(maxWidth: .infinity)
        askBar
      }
      .padding(.horizontal, 0)
    }
    .background(sb.background.ignoresSafeArea())
  }

  // MARK: Top bar — window dots + working logo

  private var topBar: some View {
    HStack(spacing: 6) {
      ForEach(0..<3, id: \.self) { _ in
        Circle().fill(sb.ink(.w14)).frame(width: 11, height: 11)
      }
      Spacer()
      Button { SBThemeManager.shared.toggle() } label: {
        Text("◐").font(.system(size: 14)).foregroundStyle(sb.ink(.w4))
      }
      .buttonStyle(.plain)
      .help("Light / dark")
      .padding(.trailing, 10)
      SBLogo(size: 15, spinning: isWorking, opacity: isWorking ? 1 : 0.85)
    }
    .padding(.horizontal, 22)
    .padding(.top, 16)
  }

  // MARK: Nav — tabs + ⌘K + settings + overflow

  private var navBar: some View {
    HStack(alignment: .firstTextBaseline, spacing: 18) {
      ForEach(tabs, id: \.index) { tab in
        Button {
          navigate(to: tab.index)
        } label: {
          Text(tab.title)
            .geist(size: 15, weight: selectedIndex == tab.index ? .semibold : .regular)
            .foregroundStyle(selectedIndex == tab.index ? sb.ink : sb.ink(.w38))
        }
        .buttonStyle(.plain)
      }

      Spacer()

      Button(action: onOpenPalette) {
        Text("⌘K")
          .geistMono(size: 12.5, weight: .medium)
          .foregroundStyle(sb.ink(.w35))
          .padding(.horizontal, 7).padding(.vertical, 2)
          .overlay(RoundedRectangle(cornerRadius: 6).stroke(sb.ink(.w12), lineWidth: 1))
      }
      .buttonStyle(.plain)

      overflowMenu

      Button {
        onOpenSettings()
      } label: {
        HStack(spacing: 6) {
          Image(systemName: "gearshape").font(.system(size: 13))
          Text("Settings").geist(size: 13.5)
        }
        .foregroundStyle(isSettings ? sb.ink : sb.ink(.w4))
        .padding(.horizontal, 12).padding(.vertical, 4)
        .overlay(Capsule().stroke(sb.ink(.w12), lineWidth: 1))
      }
      .buttonStyle(.plain)
    }
    .frame(maxWidth: 780)
    .frame(maxWidth: .infinity)
    .padding(.horizontal, 30)
    .padding(.top, 18)
    .padding(.bottom, 14)
  }

  private var overflowMenu: some View {
    Menu {
      ForEach(overflow, id: \.index) { item in
        Button(item.title) { navigate(to: item.index) }
      }
      Divider()
      Button("Settings") { onOpenSettings() }
    } label: {
      Text("···")
        .geist(size: 15, weight: .semibold)
        .foregroundStyle(sb.ink(.w4))
        .frame(width: 22)
    }
    .menuStyle(.borderlessButton)
    .menuIndicator(.hidden)
    .fixedSize()
  }

  // MARK: Ask bar (persistent)

  private var askBar: some View {
    HStack(spacing: 10) {
      TextField("Search your conversations…", text: $askText)
        .textFieldStyle(.plain)
        .geist(size: 14)
        .foregroundStyle(sb.ink)
        .onSubmit(onSubmitAsk)

      Button(action: onOpenChats) {
        Text("Chats").geistMono(size: 12, weight: .medium).foregroundStyle(sb.ink(.w45))
      }
      .buttonStyle(.plain)

      Button(action: onVoice) {
        HStack(spacing: 6) {
          Circle().fill(sb.ink(.w55)).frame(width: 6, height: 6)
          Text("fn · speak").geistMono(size: 12, weight: .medium)
        }
        .foregroundStyle(sb.ink(.w55))
        .padding(.horizontal, 10).padding(.vertical, 4)
        .overlay(RoundedRectangle(cornerRadius: 7).stroke(sb.ink(.w12), lineWidth: 1))
      }
      .buttonStyle(.plain)
      .help("Hold fn and just say it")

      Button(action: onSubmitAsk) {
        Text("↩").geistMono(size: 12.5).foregroundStyle(sb.ink(.w35))
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, 14).padding(.vertical, 11)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous).fill(sb.ink(.w06))
    )
    .overlay(
      RoundedRectangle(cornerRadius: 11, style: .continuous).stroke(sb.ink(.w09), lineWidth: 1)
    )
    .frame(maxWidth: 780)
    .frame(maxWidth: .infinity)
    .padding(.horizontal, 30)
    .padding(.top, 12)
    .padding(.bottom, 18)
  }

  private func navigate(to index: Int) {
    withAnimation(SBMotion.standard) { selectedIndex = index }
  }
}
