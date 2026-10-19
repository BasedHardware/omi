import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

extension SettingsContentView {
  func openURLInDefaultBrowser(_ url: URL) {
    if let appURL = NSWorkspace.shared.urlForApplication(toOpen: url) {
      let configuration = NSWorkspace.OpenConfiguration()
      configuration.activates = true
      NSWorkspace.shared.open([url], withApplicationAt: appURL, configuration: configuration) {
        _, error in
        if let error {
          NSLog(
            "OMI SETTINGS: Failed to open browser URL %@: %@", url.absoluteString,
            error.localizedDescription)
          NSWorkspace.shared.open(url)
        }
      }
      return
    }

    NSWorkspace.shared.open(url)
  }

  func updateDailySummarySettings(enabled: Bool? = nil, hour: Int? = nil) {
    Task {
      do {
        try await APIClient.shared.updateDailySummarySettings(enabled: enabled, hour: hour)
      } catch {
        logError("Failed to update daily summary settings", error: error)
      }
    }
  }

  func updateDailySummaryDepth(_ depth: DailySummaryDepth) {
    guard depth != savedDailySummaryDepth, !dailySummaryDepthSaving else { return }
    dailySummaryDepthSaving = true
    dailySummaryDepthRevision += 1
    dailySummaryDepthError = nil
    Task {
      do {
        try await APIClient.shared.updateDailySummarySettings(depth: depth)
        savedDailySummaryDepth = depth
      } catch {
        logError("Failed to update daily summary depth", error: error)
        dailySummaryDepth = savedDailySummaryDepth
        dailySummaryDepthError = "Couldn't save recap depth. Choose a depth again."
      }
      dailySummaryDepthSaving = false
    }
  }

  func updateNotificationSettings(enabled: Bool? = nil, frequency: Int? = nil) {
    if let enabled {
      // Mirror locally so NotificationService suppresses/resumes proactive notifications
      // immediately when the master toggle flips, even before the backend round-trip completes.
      UserDefaults.standard.set(enabled, forKey: NotificationService.masterEnabledDefaultsKey)
    }
    if let frequency {
      // Mirror locally so NotificationService picks up the new throttle level immediately,
      // even before the backend round-trip completes.
      UserDefaults.standard.set(frequency, forKey: NotificationService.frequencyDefaultsKey)
    }
    let syncRevision = NotificationService.beginNotificationSettingsSync()
    // Preserve request order and always send the complete locally desired state.
    // If an earlier partial mutation fails, a later successful mutation must also
    // repair that field before it is allowed to clear the pending-sync journal.
    NotificationSettingsSyncCoordinator.shared.enqueue(
      enabled: NotificationService.areNotificationsEnabled(),
      frequency: NotificationService.currentFrequencyLevel(),
      revision: syncRevision)
  }

  func updateLanguage(_ language: String) {
    Task {
      // Track language change
      AnalyticsManager.shared.languageChanged(language: language)
      do {
        let _ = try await APIClient.shared.updateUserLanguage(language)
      } catch {
        logError("Failed to update language", error: error)
      }
    }
  }

  func updateRecordingPermission(_ enabled: Bool) {
    Task {
      do {
        try await APIClient.shared.setRecordingPermission(enabled: enabled)
      } catch {
        logError("Failed to update recording permission", error: error)
      }
    }
  }

  func updatePrivateCloudSync(_ enabled: Bool) {
    Task {
      do {
        try await APIClient.shared.setPrivateCloudSync(enabled: enabled)
      } catch {
        logError("Failed to update private cloud sync", error: error)
      }
    }
  }

  func updateTranscriptionPreferences(
    singleLanguageMode: Bool? = nil, vocabulary: String? = nil
  ) {
    guard let vocabulary else {
      Task {
        do {
          let _ = try await APIClient.shared.updateTranscriptionPreferences(singleLanguageMode: singleLanguageMode)
        } catch {
          logError("Failed to update transcription preferences", error: error)
        }
      }
      return
    }

    let terms = vocabulary.split(separator: ",")
      .map { $0.trimmingCharacters(in: .whitespaces) }
      .filter { !$0.isEmpty }
    // `saveVocabulary()` has already put this list in the pane and the local copy. Any later write to
    // the local copy (another edit, a Settings load) moves the revision on.
    let vocabularyRevision = AssistantSettings.shared.transcriptionVocabularyRevision
    vocabularySaveError = nil
    Task {
      let outcome = await TranscriptionVocabularySaver.save(
        terms,
        lastConfirmed: { savedVocabularyList },
        isLatestEdit: { AssistantSettings.shared.transcriptionVocabularyRevision == vocabularyRevision },
        write: {
          try await APIClient.shared.updateTranscriptionPreferences(
            singleLanguageMode: singleLanguageMode, vocabulary: $0
          ).vocabulary
        }
      )
      switch outcome {
      case .saved(let stored):
        savedVocabularyList = stored
      case .failed(let restore):
        if let restore {
          vocabularyList = restore
          AssistantSettings.shared.transcriptionVocabulary = restore
        }
        vocabularySaveError = TranscriptionVocabularySaver.failureMessage
      case .superseded:
        break
      }
    }
  }

  func deleteAccountAndData() {
    guard !isDeletingAccount else { return }

    deleteAccountError = nil
    isDeletingAccount = true
    AnalyticsManager.shared.deleteAccountConfirmed()

    Task {
      do {
        guard let deletionOwner = RuntimeOwnerIdentity.currentOwnerId() else {
          throw AuthError.notSignedIn
        }
        try await APIClient.shared.deleteAccount()
        // The backend has durably admitted deletion. Persist the cleanup owner
        // before any local transition so a crash/relaunch cannot restore this
        // accepted account and migrate its local Rewind data into a new UID.
        UserDefaults.standard.set(deletionOwner, forKey: .acceptedAccountDeletionOwnerId)
        await MainActor.run {
          appState.stopTranscription()
          ProactiveAssistantsPlugin.shared.stopMonitoring(reason: .accountDeleted)
        }
        do {
          try await AuthService.shared.signOut(acceptedAccountDeletion: true)
          isDeletingAccount = false
        } catch {
          deleteAccountError = "Your account was deleted, but Omi couldn't sign you out. Quit and reopen Omi."
          isDeletingAccount = false
        }
      } catch {
        await MainActor.run {
          deleteAccountError = UserFacingErrorPresentation.message(for: error, while: .accountDeletion)
          isDeletingAccount = false
        }
      }
    }
  }

}

/// Custom-vocabulary saves, which the pane shows before the account has stored them.
///
/// `saveVocabulary()` puts an edit in the pane and in the local copy (`AssistantSettings`), then sends
/// the whole list to `PATCH /v1/users/transcription-preferences`. A failed PATCH (offline, a server
/// error, an expired session) used to be only logged, so the pane and the local copy kept a list the
/// account never stored: the word looked saved, live transcription (which reads the account's list)
/// never used it, and the next Settings load quietly dropped it.
///
/// So a failed save puts back the list the account last confirmed and says the change was not saved.
@MainActor
enum TranscriptionVocabularySaver {
  static let failureMessage = "Couldn't save your vocabulary change. Try again."

  enum Outcome: Equatable {
    /// The account stored the list; `stored` is the list it now holds.
    case saved(stored: [String])
    /// The account did not store the list. Show `restore`, the list it last confirmed, again (`nil`
    /// when Settings has not read the account's list yet), and say the change was not saved.
    case failed(restore: [String]?)
    /// The save failed, but a newer edit was made while it ran. That edit's save sends the whole list
    /// again, this change included, so its outcome decides what the pane shows.
    case superseded
  }

  /// Stores `terms` as the account's whole vocabulary through `write`, which returns the list the
  /// account then holds.
  ///
  /// `isLatestEdit` and `lastConfirmed` are read only once the save has failed, so they see an edit
  /// made, or a save confirmed, while it ran.
  static func save(
    _ terms: [String],
    lastConfirmed: () -> [String]?,
    isLatestEdit: () -> Bool,
    write: ([String]) async throws -> [String]
  ) async -> Outcome {
    do {
      let stored = try await write(terms)
      return .saved(stored: stored)
    } catch {
      logError("Settings: failed to save custom vocabulary", error: error)
      guard isLatestEdit() else { return .superseded }
      return .failed(restore: lastConfirmed())
    }
  }
}
