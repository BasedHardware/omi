import Foundation

/// What the app does when iOS wakes it in the background (`BGTaskScheduler`, scheduled by
/// `App/System/BackgroundTasks.swift`). The Flutter iOS app declares `fetch` and `processing` but
/// leaves them to its plugins; here they do the work that otherwise waits for the next launch.
///
/// - `refresh` (a few seconds, often): recordings still on the phone upload, finished sync jobs
///   are collected, and conversations and tasks refresh, so widgets and Home are current.
/// - `processing` (minutes, on network, often while charging): the same, for a long queue of
///   recordings (an Omi that was away all day).
@MainActor
public struct BackgroundWork {
    public enum Kind: Sendable, CaseIterable {
        case refresh
        case processing
    }

    private let isSignedIn: () -> Bool
    private let uploadRecordings: () async -> Void
    private let refreshLists: () async -> Void
    private let log: DebugLog?

    public init(
        isSignedIn: @escaping () -> Bool,
        uploadRecordings: @escaping () async -> Void,
        refreshLists: @escaping () async -> Void,
        log: DebugLog? = nil
    ) {
        self.isSignedIn = isSignedIn
        self.uploadRecordings = uploadRecordings
        self.refreshLists = refreshLists
        self.log = log
    }

    /// Runs one wake-up; false when there was nothing it could do (signed out) or it was cancelled.
    public func run(_ kind: Kind) async -> Bool {
        guard isSignedIn() else { return false }
        log?.add(.info, "sync", "background \(kind == .refresh ? "refresh" : "processing") started")
        await uploadRecordings()
        guard !Task.isCancelled else { return false }
        await refreshLists()
        return !Task.isCancelled
    }
}
