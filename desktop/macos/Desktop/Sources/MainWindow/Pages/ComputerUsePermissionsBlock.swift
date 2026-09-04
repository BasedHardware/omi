import OmiTheme
import SwiftUI

/// The built-in server's permissions block in its detail sheet: the switch, the
/// three grants it needs, and the stop control — the whole gate UI, on the
/// server's own surface, so control is managed where the server is listed.
///
/// The grid card for this server renders through the same `AgentExtensionCard`
/// as every other server; this block is the one surface that is unique to it.
struct ComputerUsePermissionsBlock: View {
  @ObservedObject private var store = CuaControlStatusStore.shared
  // The status line reads the gate directly: `lastActivity` changes on every
  // tool call, and "Active now" that never appears is worse than no indicator.
  @ObservedObject private var gate = CuaControlGate.shared

  private let permissionPoll = Timer.publish(every: 2, on: .main, in: .common).autoconnect()

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Toggle(isOn: $store.isEnabled) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Allow Omi to control this Mac")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)
          Text(
            "Serves the screen, the accessibility tree, and mouse and keyboard control to Omi and any MCP client you point at this server"
          )
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
        }
      }
      .toggleStyle(.switch)

      if store.isEnabled {
        ForEach(CuaControlStatusStore.listed, id: \.permission) { entry in
          permissionRow(
            title: entry.title,
            detail: entry.detail,
            granted: store.granted[entry.permission] ?? false,
            grant: {
              // Ask macOS first: the system prompt is the only path that grants
              // anything, and Settings is the fallback for a prompt already
              // answered once and never shown again.
              entry.permission.request()
              entry.permission.openSettings()
            })
        }
        Text("New grants take effect the next time Omi starts.")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)

        statusRow
      }

      if let failure = store.failure {
        Text(failure)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .padding(OmiSpacing.md)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Ink.rowFill)
    .cornerRadius(OmiChrome.smallControlRadius)
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .stroke(Ink.separator, lineWidth: 1)
    )
    .onReceive(permissionPoll) { _ in
      Task { await store.poll() }
    }
    .onAppear { store.refreshPermissions() }
  }

  /// Live state, and the stop button. Present whenever control is on, because a
  /// kill switch you have to go looking for is not one.
  private var statusRow: some View {
    HStack(spacing: OmiSpacing.md) {
      Circle()
        .fill(gate.suspension == nil ? Ink.primary : Ink.secondary)
        .frame(width: 8, height: 8)
      Text(store.statusText())
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
      Spacer()
      Button(gate.suspension == nil ? "Stop now" : "Re-arm") {
        if gate.suspension == nil {
          store.stopNow()
        } else {
          store.rearm()
        }
      }
      .buttonStyle(.plain)
      .scaledFont(size: OmiType.caption, weight: .medium)
      .foregroundColor(Ink.primary)
    }
  }

  private func permissionRow(
    title: String, detail: String, granted: Bool, grant: @escaping () -> Void
  ) -> some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: granted ? "checkmark.circle.fill" : "exclamationmark.circle")
        .foregroundColor(granted ? Ink.primary : Ink.secondary)
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(title)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.primary)
        Text(detail)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
      }
      Spacer()
      if !granted {
        Button("Grant", action: grant)
          .buttonStyle(.plain)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.primary)
      }
    }
  }
}
