import AppKit
import ApplicationServices
import OmiTheme
import SwiftUI

/// The one switch that lets anything drive this Mac, at the top of the MCP page
/// because that is what it turns on: an MCP server, Omi's own, serving the
/// computer-use tools on the loopback interface.
///
/// The card exists to make three things impossible to miss — that it is off, what
/// it needs to work, and how to stop it. A permission the user has not granted is
/// named here rather than discovered as a tool that silently does nothing.
struct ComputerControlSection: View {
  @ObservedObject private var gate = CuaControlGate.shared

  @State private var isEnabled = CuaControlGate.shared.isEnabled
  /// Every grant, checked with the API that actually answers for it. Input and
  /// UI reading are two TCC services behind one System Settings pane, so they
  /// are listed separately: a Mac can hold either without the other.
  @State private var granted: [CuaPermission: Bool] = [:]
  @State private var failure: String?

  /// Two of these live in the same System Settings pane and are still two
  /// separate grants, so each is named by what it lets Omi do rather than by the
  /// pane it is found in.
  private static let listed: [(permission: CuaPermission, title: String, detail: String)] = [
    (.postEvents, "Input", "Move the pointer, click, and type. Accessibility pane."),
    (
      .accessibility, "Reading controls",
      "List another app's controls and press them by name. Accessibility pane."
    ),
    (.screenRecording, "Screen", "Take screenshots. Screen Recording pane."),
  ]

  private let permissionPoll = Timer.publish(every: 2, on: .main, in: .common).autoconnect()

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      header

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        Toggle(isOn: $isEnabled) {
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Allow Omi to control this Mac")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.primary)
            Text(
              "Serves screenshots, the accessibility tree, and mouse and keyboard control to Omi and any MCP client you point at \(CuaMcpRegistration.endpointURL)."
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
          }
        }
        .toggleStyle(.switch)

        if isEnabled {
          ForEach(Self.listed, id: \.permission) { entry in
            permissionRow(
              title: entry.title,
              detail: entry.detail,
              granted: granted[entry.permission] ?? false,
              grant: {
                // Ask macOS first: the system prompt is the only path that grants
                // anything, and Settings is the fallback for a prompt already
                // answered once and never shown again.
                entry.permission.request()
                entry.permission.openSettings()
              })
          }
          Text(
            "A grant given now applies from Omi's next launch — macOS caches the answer per process."
          )
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          statusRow
        }

        if let failure {
          Text(failure)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
      }
      .padding(OmiSpacing.md)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(Ink.rowFill)
      .cornerRadius(OmiChrome.smallControlRadius)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .stroke(Ink.separator, lineWidth: 1))
    }
    .onReceive(permissionPoll) { _ in
      Task {
        // The live probe is IPC and runs off the main actor; the ticked box in
        // System Settings is what this is watching for.
        await CuaPermission.refreshLiveGrants([.accessibility, .postEvents])
        refreshPermissions()
      }
    }
    .onAppear { refreshPermissions() }
    // The toggle drives the switch through state rather than a `Binding(get:set:)`:
    // that shape crashes swift-frontend 6.3.3 in IRGen ("While emitting IR SIL
    // function @$sSbScA_pSgIeAghyg_SbIeAghn_TR"), the thunk for its isolated
    // Bool getter. `setEnabled` can also refuse (no account signed in) and correct
    // the state back, which re-enters here once with the corrected value and settles.
    .onChange(of: isEnabled) { _, enabled in setEnabled(enabled) }
  }

  private var header: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
      Text("Computer Control")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(Ink.primary)
      Text("Let Omi see the screen and use the keyboard and mouse, the way you would")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
    }
  }

  /// Live state, and the stop button. Present whenever control is on, because a
  /// kill switch you have to go looking for is not one.
  private var statusRow: some View {
    HStack(spacing: OmiSpacing.md) {
      Circle()
        .fill(gate.suspension == nil ? Ink.primary : Ink.secondary)
        .frame(width: 8, height: 8)
      Text(statusText)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
      Spacer()
      Button(gate.suspension == nil ? "Stop now" : "Re-arm") {
        if gate.suspension == nil {
          gate.suspend(reason: "stopped from Settings")
        } else {
          gate.rearm()
        }
      }
      .buttonStyle(.plain)
      .scaledFont(size: OmiType.caption, weight: .medium)
      .foregroundColor(Ink.primary)
    }
  }

  private var statusText: String {
    if let suspension = gate.suspension { return "Stopped — \(suspension)" }
    guard let last = gate.lastActivity else { return "Ready. Nothing has used it yet." }
    let seconds = Int(Date().timeIntervalSince(last))
    return seconds < 5 ? "Active now" : "Ready. Last action \(seconds)s ago."
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

  /// Turning control on also starts the loopback server and writes the entry
  /// Omi's own agent reads, so one switch is the whole setup rather than three
  /// steps a user can complete two of.
  private func setEnabled(_ enabled: Bool) {
    failure = nil
    guard enabled else {
      gate.setEnabled(false)
      CuaMcpRegistration.unregister()
      isEnabled = false
      return
    }
    do {
      let token = try LocalAgentAPISettings.enable()
      try CuaMcpRegistration.register(token: token)
      gate.setEnabled(true)
      isEnabled = gate.isEnabled
      if !isEnabled {
        failure = "Sign in to Omi first — computer control is granted per account."
      }
    } catch {
      failure = error.localizedDescription
      isEnabled = false
    }
  }

  private func refreshPermissions() {
    granted = Dictionary(
      uniqueKeysWithValues: Self.listed.map { ($0.permission, $0.permission.isGranted()) })
    isEnabled = gate.isEnabled
  }
}
