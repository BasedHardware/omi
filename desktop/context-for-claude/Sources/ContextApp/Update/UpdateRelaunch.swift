import Foundation

/// The note the outgoing build leaves for the incoming one, so the app that comes back after an
/// update knows it *is* the app that came back after an update.
///
/// This exists for one failure, and it is the failure this app is least able to survive. macOS
/// attaches Screen Recording, Microphone and System Audio consent to a code signature; installing an
/// update replaces the signed bundle. When the two signatures do not match — a changed certificate,
/// a changed Team ID, a changed designated requirement — every grant is silently revoked and the app
/// comes back looking healthy: the menu bar item appears, audio still records, and screen capture
/// quietly returns nothing, forever. That is not hypothetical. It happened on the machine this was
/// written on: the bundle was re-signed at 14:33, and the last screen frame it ever captured was
/// stamped 14:20 — thirteen minutes earlier — with a day of launches after it and no complaint from
/// anywhere.
///
/// A permission check on every launch would not answer the question, because "no Screen Recording"
/// on a first run is onboarding and "no Screen Recording" one launch after an update is a broken
/// update. Only the previous process knows which of those just happened, and it only knows it for
/// the moment between Sparkle deciding to install and Sparkle terminating it. So it writes it down.
///
/// **Written synchronously.** ``note(installOf:from:at:defaults:)`` is called from Sparkle's
/// `willInstallUpdate:`, the last delegate callback before the process is terminated to make way for
/// the installer. Anything queued rather than flushed is lost, and losing it means losing the one
/// signal that distinguishes a broken update from a fresh install.
enum UpdateRelaunch {

    /// The version being installed. Read back to tell "the update landed" from "the update was
    /// announced and then something went wrong", which are different bug reports.
    static let toVersionKey = "context.update.relaunchToVersion"
    /// The version that was running when the install started.
    static let fromVersionKey = "context.update.relaunchFromVersion"
    /// When the outgoing process handed over, as seconds since the reference date.
    static let notedAtKey = "context.update.relaunchNotedAt"

    struct Record: Equatable, Sendable {
        /// The version that was running before the update.
        let fromVersion: String
        /// The version the appcast said was being installed.
        let toVersion: String
        let notedAt: Date
    }

    /// Records that an update is about to be installed over this running copy.
    static func note(
        installOf toVersion: String,
        from fromVersion: String,
        at date: Date = Date(),
        defaults: UserDefaults = .standard
    ) {
        defaults.set(toVersion, forKey: toVersionKey)
        defaults.set(fromVersion, forKey: fromVersionKey)
        defaults.set(date.timeIntervalSinceReferenceDate, forKey: notedAtKey)
        // Sparkle terminates this process moments from now. `synchronize()` is normally unnecessary
        // and mildly discouraged; here it is the difference between the next launch knowing what
        // happened and not.
        defaults.synchronize()
    }

    /// Reads the note left by the previous process, clearing it so a single update is reported once.
    ///
    /// Returns `nil` when there is no note, and also when there is one but the running version still
    /// matches the version that wrote it — that is an install that was announced and then did not
    /// happen (a failed download, a cancelled install, a user who quit first), and treating it as a
    /// completed update would blame the updater for permissions that were never touched.
    ///
    /// Clearing on *every* call, including that one, is deliberate: a stale note that survives is a
    /// note that eventually fires against an unrelated launch.
    @discardableResult
    static func consume(
        currentVersion: String,
        defaults: UserDefaults = .standard
    ) -> Record? {
        defer {
            defaults.removeObject(forKey: toVersionKey)
            defaults.removeObject(forKey: fromVersionKey)
            defaults.removeObject(forKey: notedAtKey)
        }
        guard let fromVersion = defaults.string(forKey: fromVersionKey),
            let toVersion = defaults.string(forKey: toVersionKey)
        else { return nil }
        guard currentVersion != fromVersion else { return nil }
        return Record(
            fromVersion: fromVersion,
            toVersion: toVersion,
            notedAt: Date(timeIntervalSinceReferenceDate: defaults.double(forKey: notedAtKey)))
    }

    /// What to tell a user whose capture stopped working across an update.
    ///
    /// Kept here rather than at the place that shows it because the sentence is the whole point of
    /// the record: it has to name the update as the cause, or the user reads a permission prompt they
    /// already answered months ago as the app being broken.
    static func permissionsLostMessage(_ record: Record) -> String {
        "Context for Claude updated to \(record.toVersion) and macOS reset its screen and "
            + "microphone permissions. Nothing has been captured since. Re-grant them in "
            + "System Settings › Privacy & Security to start again."
    }
}
