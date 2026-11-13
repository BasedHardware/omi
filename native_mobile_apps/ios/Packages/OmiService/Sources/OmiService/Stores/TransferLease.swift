import Foundation

/// The finite grant of background runtime the app holds while a transfer runs.
///
/// iOS lets an app that has left the foreground keep running for a while longer when it asks
/// (`beginBackgroundTask`). A transfer that is still going asks, so a recording is not cut in half
/// when the screen goes off: reading a day of audio off the Omi, or uploading the files that came
/// out of it. The grant is finite and the system takes it back when the time is up, which is what
/// `begin`'s expiry closure reports.
///
/// The app owns the two platform calls (`App/System/BackgroundTransferLease.swift`); this type owns
/// the refcount, so a read and an upload running at the same time hold one grant, and the grant
/// ends when the last of them does.
@MainActor
public final class TransferLease {
    /// Asks for a grant and says whether it was given one; the system calls the closure when the
    /// grant is used up. Both sides of it run on the main actor, where the app's own calls live.
    public typealias Begin = @MainActor (@escaping @MainActor () -> Void) -> Bool
    /// Hands the grant back.
    public typealias End = @MainActor () -> Void

    private let begin: Begin
    private let end: End
    private let log: DebugLog?
    private var refs = 0

    /// Whether a grant is held right now.
    public private(set) var isHeld = false

    public init(begin: @escaping Begin, end: @escaping End, log: DebugLog? = nil) {
        self.begin = begin
        self.end = end
        self.log = log
    }

    /// A transfer is about to run. The first caller takes the grant; without one the transfer still
    /// runs, it is just the first thing iOS stops.
    public func acquire() {
        refs += 1
        guard refs == 1 else { return }
        guard begin({ [weak self] in self?.expire() }) else {
            refs = 0
            log?.add(.warning, "sync", "no background time left: the transfer stops if the app leaves")
            return
        }
        isHeld = true
    }

    /// One transfer finished; the last one hands the grant back.
    public func release() {
        guard refs > 0 else { return }
        refs -= 1
        guard refs == 0, isHeld else { return }
        endGrant()
    }

    /// The grant ran out. Whatever is running stops where it is; nothing is half-written, because
    /// every batch of records is closed before the next one is asked for, and an upload that was
    /// cut is still in the queue and goes again at the next launch.
    private func expire() {
        refs = 0
        guard isHeld else { return }
        endGrant()
        log?.add(.warning, "sync", "background time ran out: the transfer stops here, and resumes at the next launch")
    }

    private func endGrant() {
        isHeld = false
        end()
    }
}
