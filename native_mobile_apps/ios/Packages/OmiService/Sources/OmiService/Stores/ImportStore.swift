import Foundation
import Observation
import OmiNetwork

/// Importing history from another device (Flutter `import_history_page`): a Limitless export zip
/// is uploaded, the backend turns it into conversations; the list refreshes every few seconds
/// while a job runs.
@MainActor
@Observable
public final class ImportStore {
    public enum Phase: Equatable, Sendable { case idle, loading, loaded, failed }

    public private(set) var phase: Phase = .idle
    public private(set) var jobs: [ImportJob] = []
    public private(set) var isUploading = false
    public private(set) var lastError: String?

    private let api: any APIClientProtocol
    private let pollInterval: Duration
    private var polling: Task<Void, Never>?
    /// The backend refuses anything larger.
    static let maxBytes = 100 * 1024 * 1024

    public init(api: any APIClientProtocol, pollInterval: Duration = .seconds(3)) {
        self.api = api
        self.pollInterval = pollInterval
    }

    public var hasRunningJob: Bool {
        jobs.contains(where: \.isRunning)
    }

    public func load() async {
        if jobs.isEmpty { phase = .loading }
        do {
            jobs = try await api.importJobs()
            phase = .loaded
        } catch {
            phase = jobs.isEmpty ? .failed : .loaded
        }
        if hasRunningJob { startPolling() }
    }

    /// Uploads a picked zip. Returns whether the import started.
    @discardableResult
    public func importZip(at url: URL, language: String) async -> Bool {
        lastError = nil
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        guard url.pathExtension.lowercased() == "zip", let data = try? Data(contentsOf: url, options: .mappedIfSafe) else {
            lastError = "unreadable"
            return false
        }
        guard data.count <= Self.maxBytes else {
            lastError = "tooLarge"
            return false
        }
        isUploading = true
        defer { isUploading = false }
        do {
            let job = try await api.importLimitless(zip: data, filename: url.lastPathComponent, language: language)
            jobs.removeAll { $0.id == job.id }
            jobs.insert(job, at: 0)
            startPolling()
            return true
        } catch {
            lastError = String(describing: error)
            return false
        }
    }

    public func cancel(_ id: String) async {
        do {
            try await api.cancelImportJob(id: id)
        } catch {
            lastError = String(describing: error)
        }
        await load()
    }

    /// Removes a finished job from the history (its conversations stay).
    public func delete(_ id: String) async {
        guard let index = jobs.firstIndex(where: { $0.id == id }) else { return }
        let removed = jobs.remove(at: index)
        do {
            try await api.deleteImportJob(id: id)
        } catch {
            lastError = String(describing: error)
            jobs.insert(removed, at: min(index, jobs.count))
        }
    }

    public func stopPolling() {
        polling?.cancel()
        polling = nil
    }

    private func startPolling() {
        guard polling == nil else { return }
        let interval = pollInterval
        polling = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: interval)
                guard let self, !Task.isCancelled else { return }
                if let fresh = try? await api.importJobs() { jobs = fresh }
                if !hasRunningJob { break }
            }
            self?.polling = nil
        }
    }
}
