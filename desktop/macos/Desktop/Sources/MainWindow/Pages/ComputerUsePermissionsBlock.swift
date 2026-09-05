import OmiTheme
import SwiftUI

/// The built-in server's detail sheet below its header: what computer control
/// is, the switch, whatever grants are still missing, and the tool list.
///
/// The grid card for this server renders through the same `AgentExtensionCard`
/// as every other server; this block is the one surface that is unique to it.
///
/// Sized by its content. Nothing is shown for a state the user is not in: the
/// grants appear when the switch is on and something is genuinely missing, and
/// disappear for good once macOS has given them.
struct ComputerUsePermissionsBlock: View {
  var appState: AppState?

  @ObservedObject private var store = CuaControlStatusStore.shared
  @ObservedObject private var gate = CuaControlGate.shared

  @State private var showTools = false

  /// Every grant is listed at all times, so the row says which of three things
  /// is true rather than appearing only to complain. `needsRelaunch` is the
  /// state a checkbox cannot express: macOS has given the grant and this
  /// process still cannot use it.
  private enum GrantState {
    case granted
    case needsRelaunch
    case missing

    var isSettled: Bool { self == .granted }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text(CuaControlCopy.description)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)

      Toggle(isOn: $store.isEnabled) {
        Text("Allow Omi to control this Mac")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
      }
      .toggleStyle(.switch)

      // Always listed. Which grants this asks for is the substance of the
      // consent, so it is answered before the switch is touched and stays
      // answerable afterwards — a settled grant reads as settled rather than
      // vanishing and leaving the list looking incomplete.
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        Text("Permissions")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.secondary)
        ForEach(CuaControlStatusStore.listed, id: \.permission) { entry in
          permissionRow(entry: entry, state: state(of: entry.permission))
        }
      }

      if let failure = store.failure {
        Text(failure)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.errorRed)
          .fixedSize(horizontal: false, vertical: true)
      }

      // The switch turns control off for good; this stops work already running
      // without giving up the setup, so it is only worth showing while there is
      // something to stop.
      if store.isEnabled {
        Button(gate.suspension == nil ? "Stop now" : "Re-arm") {
          if gate.suspension == nil { store.stopNow() } else { store.rearm() }
        }
        .buttonStyle(.plain)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(gate.suspension == nil ? Ink.errorRed : Ink.primary)
      }

      toolsSection
    }
    .onAppear { store.beginPolling() }
    .onDisappear { store.endPolling() }
  }

  // MARK: - Permissions

  private func state(of permission: CuaPermission) -> GrantState {
    guard store.granted[permission] ?? false else { return .missing }
    // Only Screen Recording has a grant macOS withholds from a running process.
    return permission == .screenRecording && store.screenNeedsRelaunch ? .needsRelaunch : .granted
  }

  @ViewBuilder
  private func permissionRow(entry: CuaControlStatusStore.Listed, state: GrantState) -> some View {
    HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
      Image(systemName: icon(for: state))
        .foregroundColor(tint(for: state))
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(entry.title)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.primary)
        Text(detail(entry: entry, state: state))
          .scaledFont(size: OmiType.caption)
          .foregroundColor(state.isSettled ? Ink.listeningGreen : Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      Spacer(minLength: OmiSpacing.sm)
      action(for: state, permission: entry.permission)
    }
  }

  private func icon(for state: GrantState) -> String {
    switch state {
    case .granted: return "checkmark.circle.fill"
    case .needsRelaunch: return "arrow.clockwise.circle.fill"
    case .missing: return "exclamationmark.circle.fill"
    }
  }

  private func tint(for state: GrantState) -> Color {
    state.isSettled ? Ink.listeningGreen : Ink.errorRed
  }

  private func detail(entry: CuaControlStatusStore.Listed, state: GrantState) -> String {
    switch state {
    case .granted: return "Granted"
    case .needsRelaunch: return "granted, but macOS only hands it to a fresh launch"
    case .missing: return entry.detail
    }
  }

  /// The grant is worth offering whether or not the switch is on: someone who
  /// wants the permissions in place before turning control on should not have
  /// to turn it on to be asked.
  @ViewBuilder
  private func action(for state: GrantState, permission: CuaPermission) -> some View {
    if state == .needsRelaunch, let appState {
      actionButton("Reopen Omi") { appState.restartApp() }
    } else if state == .missing {
      actionButton("Grant") {
        // macOS shows its dialog once per service per app. Opening System
        // Settings as well puts the pane on top of the dialog we just raised,
        // so it is the fallback for a prompt already spent, not a companion.
        if CuaPermission.hasBeenRequested(permission) {
          permission.openSettings()
        } else {
          permission.request()
        }
      }
    }
  }

  private func actionButton(_ title: String, action: @escaping () -> Void) -> some View {
    Button(title, action: action)
      .buttonStyle(.plain)
      .scaledFont(size: OmiType.caption, weight: .medium)
      .foregroundColor(Ink.errorRed)
      .padding(.horizontal, OmiSpacing.sm)
      .frame(height: 22)
      .background(Ink.errorRed.opacity(0.1))
      .cornerRadius(OmiChrome.chipRadius)
      .fixedSize()
  }

  // MARK: - Tools

  private var toolsSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Button {
        showTools.toggle()
      } label: {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: showTools ? "chevron.down" : "chevron.right")
            .scaledFont(size: OmiType.caption)
          Text("What Omi can do")
            .scaledFont(size: OmiType.caption, weight: .medium)
          Text("\(CuaToolCatalog.tools.count) tools")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
          Spacer(minLength: 0)
        }
        .foregroundColor(Ink.primary)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)

      // Capped and scrollable: the catalog grows, and a sheet that grows with
      // it stops fitting on a laptop screen.
      if showTools {
        ScrollView {
          VStack(spacing: 0) {
            ForEach(Array(CuaToolCatalog.tools.enumerated()), id: \.element.name) { index, tool in
              if index > 0 { Divider().overlay(Ink.separator) }
              toolRow(tool)
            }
          }
        }
        .frame(maxHeight: 200)
        .background(Ink.rowFill)
        .cornerRadius(OmiChrome.smallControlRadius)
      }
    }
  }

  /// Name over summary rather than two columns: a name column wide enough for
  /// `update_agent_artifact_lifecycle` at large type is most of the sheet, and
  /// one narrow enough to look tidy clips it.
  private func toolRow(_ tool: CuaTool) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
      Text(tool.name)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.primary)
      Text(tool.summary)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xs)
  }

}
