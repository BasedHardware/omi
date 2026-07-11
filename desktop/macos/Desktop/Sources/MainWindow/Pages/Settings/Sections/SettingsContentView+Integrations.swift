import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var gmailReaderSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Read Gmail button
      settingsCard(settingId: "advanced.gmail.read") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "envelope.badge")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Read Gmail")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            if let lastFetched = gmailLastFetched {
              Text("Last read \(lastFetched, formatter: relativeDateFormatter)")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
            } else {
              Text("Reads recent emails using browser cookies — no OAuth needed")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
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
              .foregroundColor(.orange)
            Text(error)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
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
              .foregroundColor(.green)
            Text("\(gmailMemoriesSaved) emails saved as memories")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
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
                  .foregroundColor(OmiColors.textPrimary)
                  .lineLimit(1)

                Text(email.from)
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textSecondary)
                  .lineLimit(1)

                if !email.snippet.isEmpty {
                  Text(email.snippet)
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                    .lineLimit(2)
                }
              }
            }
          }
        }
      }
    }
  }

  func readGmail() async {
    isReadingGmail = true
    gmailReadError = nil
    gmailMemoriesSaved = 0

    do {
      let emails = try await GmailReaderService.shared.readRecentEmails(maxResults: 50)
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
      gmailReadError = error.localizedDescription
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
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 24, height: 24)
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Sync Calendar")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            if let lastSynced = calendarLastSynced {
              Text("Last synced \(lastSynced, formatter: relativeDateFormatter)")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
            } else {
              Text("Reads Google Calendar using browser cookies — no OAuth needed")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
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
            Image(systemName: "exclamationmark.triangle.fill").foregroundColor(.orange)
            Text(error).scaledFont(size: OmiType.body).foregroundColor(OmiColors.textSecondary).lineLimit(3)
            Spacer()
          }
        }
      }
      if calendarMemoriesCreated > 0 || calendarTasksCreated > 0 {
        settingsCard(settingId: "advanced.calendar.saved") {
          HStack(spacing: OmiSpacing.md) {
            Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
            Text(
              "\(calendarMemoriesCreated) memories and \(calendarTasksCreated) tasks created from \(calendarEvents.count) events"
            )
            .scaledFont(size: OmiType.body).foregroundColor(OmiColors.textSecondary)
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
                  OmiColors.textPrimary
                ).lineLimit(1)
                Text(event.startTime).scaledFont(size: OmiType.caption).foregroundColor(OmiColors.textSecondary)
                  .lineLimit(1)
                if !event.attendees.isEmpty {
                  Text("With: \(event.attendees.prefix(3).joined(separator: ", "))").scaledFont(
                    size: 12
                  ).foregroundColor(OmiColors.textTertiary).lineLimit(1)
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
      let events = try await CalendarReaderService.shared.readEvents(daysBack: 30, daysForward: 14)
      calendarEvents = events
      calendarLastSynced = Date()
      viewModel.markIntegrationSynced()
      if !events.isEmpty {
        let result = await CalendarReaderService.shared.synthesizeFromEvents(events: events)
        calendarMemoriesCreated = result.memories
        calendarTasksCreated = result.tasks
      }
    } catch {
      calendarSyncError = error.localizedDescription
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
