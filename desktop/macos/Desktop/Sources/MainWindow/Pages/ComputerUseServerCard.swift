import OmiTheme
import SwiftUI

// MARK: - Server card

/// The built-in computer-use server as a card in the MCP grid: the same shape
/// as every other server, plus the two things only it has — the switch that
/// turns control on, and the warning that it is on but macOS has not let it
/// work yet.
///
/// The switch sits beside the card rather than inside it, so flipping it does
/// not also open the sheet; everything else on the card opens the sheet.
struct ComputerUseServerCard: View {
  @ObservedObject private var store = CuaControlStatusStore.shared
  let status: McpServerProbe.Status
  let onOpen: () -> Void

  @State private var isHovering = false

  private let permissionPoll = Timer.publish(every: 2, on: .main, in: .common).autoconnect()

  var body: some View {
    HStack(alignment: .center, spacing: OmiSpacing.md) {
      Button(action: onOpen) {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          HStack(spacing: OmiSpacing.md) {
            ExtensionLogo(imageUrl: "", fallbackSymbol: "macbook")

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text(CuaMcpRegistration.serverName)
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(Ink.primary)
                .lineLimit(1)
              Text("Built-in")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
            }

            Spacer(minLength: 0)
          }

          Text("Let Omi see the screen and use the keyboard and mouse, the way you would")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .lineLimit(2)
            .multilineTextAlignment(.leading)
            .frame(maxWidth: .infinity, minHeight: 28, alignment: .topLeading)

          HStack(spacing: OmiSpacing.sm) {
            Circle()
              .fill(statusColor)
              .frame(width: 8, height: 8)
            Text(statusText)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(statusColor)
              .lineLimit(1)

            if store.isEnabled, store.missingGrantCount > 0 {
              Text("Needs \(store.missingGrantCount) grant\(store.missingGrantCount == 1 ? "" : "s")")
                .scaledFont(size: OmiType.caption, weight: .medium)
                .foregroundColor(Ink.errorRed)
                .padding(.horizontal, OmiSpacing.sm)
                .frame(height: 20)
                .background(Ink.errorRed.opacity(0.1))
                .cornerRadius(OmiChrome.chipRadius)
            }

            Spacer(minLength: 0)

            ImportConnectorActionButton(title: "Manage", isConnected: true)
          }
        }
        .padding(OmiSpacing.md)
        .background(isHovering ? Ink.rowFillHover : Ink.rowFill)
        .cornerRadius(OmiChrome.smallControlRadius)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .stroke(Ink.separator, lineWidth: 1)
        )
      }
      .buttonStyle(.plain)
      .onHover { isHovering = $0 }

      Toggle("Allow Omi to control this Mac", isOn: $store.isEnabled)
        .toggleStyle(.switch)
        .labelsHidden()
        .accessibilityLabel("Allow Omi to control this Mac")
        .fixedSize()
    }
    .onReceive(permissionPoll) { _ in
      // The chip tracks TCC boxes ticked while Omi runs; the live probe behind
      // the accessibility rows is IPC and runs off the main actor.
      Task { await store.poll() }
    }
    .onAppear { store.refreshPermissions() }
  }

  private var statusText: String {
    if !store.isEnabled { return "Off" }
    if store.isSuspended { return "Stopped" }
    return status.label
  }

  private var statusColor: Color {
    store.isEnabled && !store.isSuspended && status.isHealthy ? Ink.primary : Ink.secondary
  }
}

// MARK: - Permissions block (detail sheet)

/// The built-in server's permissions block: the switch, the three grants it
/// needs, and the stop control — moved from the page-level section the server
/// list replaced, so control is managed where the server itself is.
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
