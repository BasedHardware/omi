import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

extension SettingsContentView {
  var gmailReaderSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Email account selection
      settingsCard(settingId: "advanced.gmail.account") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "person.crop.circle.badge.checkmark")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Email account")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(gmailAccountSummary)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          Button(action: {
            Task { await probeGmailAccounts() }
          }) {
            if isProbingGmailAccounts {
              ProgressView()
                .scaleEffect(0.7)
                .frame(width: 70, height: 22)
            } else {
              Text("Choose…")
                .scaledFont(size: OmiType.body, weight: .medium)
            }
          }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          .disabled(isProbingGmailAccounts)
        }
      }

      // Read Gmail button
      settingsCard(settingId: "advanced.gmail.read") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "envelope.badge")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(Ink.secondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Read Gmail")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)

            if let lastFetched = gmailLastFetched {
              Text("Last read \(lastFetched, formatter: relativeDateFormatter)")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
            } else {
              Text("Reads recent emails using browser cookies — no OAuth needed")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
            }
          }

          Spacer()

          Button(action: {
            Task { await readGmail() }
          }) {
            if isReadingGmail {
              ProgressView()
                .scaleEffect(0.7)
                .frame(width: 60, height: 22)
            } else {
              Text("Read Gmail")
                .scaledFont(size: OmiType.body, weight: .medium)
            }
          }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          .disabled(isReadingGmail)
        }
      }

      // Error card
      if let error = gmailReadError {
        settingsCard(settingId: "advanced.gmail.error") {
          HStack(spacing: OmiSpacing.md) {
            Image(systemName: "exclamationmark.triangle.fill")
              .foregroundColor(SettingsInk.notice)
            Text(error)
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
              .lineLimit(3)
            Spacer()
          }
        }
      }

      // Memory save status
      if gmailMemoriesSaved > 0 {
        settingsCard(settingId: "advanced.gmail.saved") {
          HStack(spacing: OmiSpacing.md) {
            Image(systemName: "checkmark.circle.fill")
              .foregroundColor(Ink.listeningGreen)
            Text("\(gmailMemoriesSaved) emails saved as memories")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
            Spacer()
          }
        }
      }

      // Email list
      if !gmailEmails.isEmpty {
        VStack(spacing: OmiSpacing.sm) {
          ForEach(gmailEmails.prefix(20)) { email in
            settingsCard(settingId: "advanced.gmail.email.\(email.id)") {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text(email.subject)
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(Ink.primary)
                  .lineLimit(1)

                Text(email.from)
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(Ink.secondary)
                  .lineLimit(1)

                if !email.snippet.isEmpty {
                  Text(email.snippet)
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(Ink.secondary)
                    .lineLimit(2)
                }
              }
            }
          }
        }
      }
    }
    .sheet(isPresented: $showingGmailAccountPicker) {
      GmailAccountPickerView(
        accounts: gmailAccounts,
        selectedCookiePath: GmailSelectionStore.selectedCookiePath,
        onSelect: { cookiePath, label in
          selectGmailAccount(cookiePath, label: label)
        },
        onCancel: { showingGmailAccountPicker = false }
      )
    }
  }

  var gmailAccountSummary: String {
    let label = GmailSelectionStore.selectedAccountLabel
    return label.isEmpty ? "Automatic — first readable browser account" : label
  }

  func probeGmailAccounts() async {
    guard !isProbingGmailAccounts else { return }
    isProbingGmailAccounts = true
    defer { isProbingGmailAccounts = false }
    guard let accounts = try? await GmailAccountProbe.availableAccounts(), !accounts.isEmpty else {
      return
    }
    gmailAccounts = accounts
    showingGmailAccountPicker = true
  }

  func selectGmailAccount(_ cookiePath: String?, label: String) {
    GmailSelectionStore.persist(cookiePath: cookiePath, label: label)
    showingGmailAccountPicker = false
  }

  func readGmail() async {
    isReadingGmail = true
    gmailReadError = nil
    gmailMemoriesSaved = 0

    do {
      let emails = try await GmailReaderService.shared.readRecentEmails(
        maxResults: 50,
        userInitiated: true
      )
      gmailEmails = emails
      gmailLastFetched = Date()
      viewModel.markIntegrationSynced()

      if !emails.isEmpty {
        isSavingGmailMemories = true
        let result = await GmailReaderService.shared.saveAsMemories(emails: emails)
        gmailMemoriesSaved = result.saved
        isSavingGmailMemories = false
      }
    } catch {
      gmailReadError = UserFacingErrorPresentation.message(for: error, while: .integration("Gmail"))
    }

    isReadingGmail = false
  }

  // MARK: - Calendar Sync Subsection

  var calendarSyncSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "advanced.calendar.sync") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "calendar.badge.clock")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(Ink.secondary)
            .frame(width: 24, height: 24)
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Sync Calendar")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)
            if let lastSynced = calendarLastSynced {
              Text("Last synced \(lastSynced, formatter: relativeDateFormatter)")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
            } else {
              Text("Reads Google Calendar using browser cookies — no OAuth needed")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
            }
          }
          Spacer()
          Button(action: { Task { await syncCalendar() } }) {
            if isReadingCalendar {
              ProgressView().scaleEffect(0.7).frame(width: 80, height: 22)
            } else {
              Text("Sync Calendar")
                .scaledFont(size: OmiType.body, weight: .medium)
            }
          }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          .disabled(isReadingCalendar)
          .accessibilityIdentifier("syncCalendarButton")
        }
      }
      if let error = calendarSyncError {
        settingsCard(settingId: "advanced.calendar.error") {
          HStack(spacing: OmiSpacing.md) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundColor(SettingsInk.notice)
            Text(error).scaledFont(size: OmiType.body).foregroundColor(Ink.secondary).lineLimit(3)
            Spacer()
          }
        }
      }
      if calendarMemoriesCreated > 0 || calendarTasksCreated > 0 {
        settingsCard(settingId: "advanced.calendar.saved") {
          HStack(spacing: OmiSpacing.md) {
            Image(systemName: "checkmark.circle.fill").foregroundColor(Ink.listeningGreen)
            Text(
              "\(calendarMemoriesCreated) memories and \(calendarTasksCreated) tasks created from \(calendarEvents.count) events"
            )
            .scaledFont(size: OmiType.body).foregroundColor(Ink.secondary)
            Spacer()
          }
        }
      }
      if !calendarEvents.isEmpty {
        VStack(spacing: OmiSpacing.sm) {
          ForEach(calendarEvents.prefix(15)) { event in
            settingsCard(settingId: "advanced.calendar.event.\(event.id)") {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text(event.summary).scaledFont(size: OmiType.body, weight: .medium).foregroundColor(
                  Ink.primary
                ).lineLimit(1)
                Text(event.startTime).scaledFont(size: OmiType.caption).foregroundColor(Ink.secondary)
                  .lineLimit(1)
                if !event.attendees.isEmpty {
                  Text("With: \(event.attendees.prefix(3).joined(separator: ", "))").scaledFont(
                    size: 12
                  ).foregroundColor(Ink.secondary).lineLimit(1)
                }
              }
            }
          }
        }
      }
    }
  }

  func syncCalendar() async {
    isReadingCalendar = true
    calendarSyncError = nil
    calendarMemoriesCreated = 0
    calendarTasksCreated = 0
    do {
      let events = try await CalendarReaderService.shared.readEvents(
        daysBack: 30,
        daysForward: 14,
        userInitiated: true
      )
      calendarEvents = events
      calendarLastSynced = Date()
      viewModel.markIntegrationSynced()
      if !events.isEmpty {
        let result = await CalendarReaderService.shared.synthesizeFromEvents(events: events)
        calendarMemoriesCreated = result.memories
        calendarTasksCreated = result.tasks
      }
    } catch {
      calendarSyncError = UserFacingErrorPresentation.message(for: error, while: .integration("Google Calendar"))
    }
    isReadingCalendar = false
  }

  var relativeDateFormatter: DateFormatter {
    let formatter = DateFormatter()
    formatter.doesRelativeDateFormatting = true
    formatter.dateStyle = .short
    formatter.timeStyle = .short
    return formatter
  }

  // MARK: - Developer API Keys Subsection

}
