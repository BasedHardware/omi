import AppKit
import OmiTheme
import SwiftUI

/// Edit the same owner/account-scoped selection used by mobile, imports and chat.
/// Keep drafts local until Save, preserving unavailable choices for explicit removal.
struct GoogleCalendarSelectionEditor: View {
  @State private var data: GoogleCalendarSelection?
  @State private var selectedIDs: Set<String> = []
  @State private var authorization: RuntimeOwnerAuthorizationSnapshot?
  @State private var busy = false
  @State private var failed = false
  @State private var saved = false
  @State private var needsConnection = false
  @State private var awaitingConsent = false

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      if busy { ProgressView().controlSize(.small) }
      if needsConnection || failed {
        Text("Connect Google Calendar to choose which calendars Omi reads.")
          .scaledFont(size: OmiType.body).foregroundColor(Ink.secondary)
        Button("Connect Google Calendar") { Task { await connect() } }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact)).disabled(busy)
          .accessibilityIdentifier("google-calendar-connect")
      }
      if awaitingConsent {
        Text("Finish Google sign-in, then Reload Calendars.")
          .scaledFont(size: OmiType.body).foregroundColor(Ink.secondary)
      }
      if let data {
        let primary = data.calendars.first(where: { $0.primary })?.name ?? data.accountID
        Text("Read selected calendars. New events use \(primary).")
          .scaledFont(size: OmiType.body).foregroundColor(Ink.secondary)
        ForEach(data.calendars) { calendar in
          Toggle(
            isOn: Binding(
              get: { selectedIDs.contains(calendar.id) },
              set: {
                saved = false
                if $0 { selectedIDs.insert(calendar.id) } else { selectedIDs.remove(calendar.id) }
              }
            )
          ) {
            Text(calendar.name.isEmpty ? "\(calendar.id) — No longer available" : calendar.name)
              .scaledFont(size: OmiType.body)
          }
          .toggleStyle(.checkbox)
          .disabled(busy || (!calendar.available && !selectedIDs.contains(calendar.id)))
          .accessibilityIdentifier("google-calendar-choice-\(calendar.id)")
        }
        HStack {
          Button("Cancel") { selectedIDs = data.selectedIDs }
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact)).disabled(busy)
          Button("Save") { Task { await save(data) } }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))
            .disabled(busy || selectedIDs.isEmpty)
            .accessibilityIdentifier("google-calendar-save")
        }
      }
      if failed {
        Text("Couldn't save or load calendars. Reload the list and try again.")
          .scaledFont(size: OmiType.body).foregroundColor(Ink.secondary)
      }
      if saved {
        Text("Calendar selection saved")
          .scaledFont(size: OmiType.body).foregroundColor(Ink.secondary)
      }
      Button("Reload Calendars") { Task { await load() } }
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact)).disabled(busy)
    }
    .task(id: RuntimeOwnerIdentity.currentOwnerId()) { await load() }
  }

  private func load() async {
    guard let owner = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      data = nil
      return
    }
    busy = true
    failed = false
    saved = false
    awaitingConsent = false
    data = nil
    defer { busy = false }
    do {
      let status = try await APIClient.shared.googleCalendarGrantStatus(authorizationSnapshot: owner)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(owner) else { return }
      needsConnection = !status.connected
      guard status.connected else { return }
      let result = try await APIClient.shared.googleCalendarSelection(authorizationSnapshot: owner)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(owner) else { return }
      authorization = owner
      data = result
      selectedIDs = result.selectedIDs
    } catch { failed = true }
  }

  private func connect() async {
    guard !busy, let owner = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return }
    busy = true
    failed = false
    awaitingConsent = false
    defer { busy = false }
    do {
      let url = try await APIClient.shared.googleCalendarOAuthURL(authorizationSnapshot: owner)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(owner) else { return }
      guard NSWorkspace.shared.open(url) else { throw APIError.invalidResponse }
      awaitingConsent = true
    } catch { failed = true }
  }

  private func save(_ selection: GoogleCalendarSelection) async {
    guard !busy, !selectedIDs.isEmpty else { return }
    guard let owner = authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(owner) else {
      data = nil
      return
    }
    busy = true
    failed = false
    saved = false
    defer { busy = false }
    do {
      let result = try await APIClient.shared.saveGoogleCalendarSelection(
        accountID: selection.accountID, selectedIDs: selectedIDs, authorizationSnapshot: owner)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(owner) else {
        data = nil
        return
      }
      data = result
      selectedIDs = result.selectedIDs
      saved = true
    } catch { failed = true }
  }
}
