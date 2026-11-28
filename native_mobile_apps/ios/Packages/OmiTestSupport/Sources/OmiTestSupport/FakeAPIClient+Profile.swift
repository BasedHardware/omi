import Foundation
import OmiCore
import OmiNetwork

/// Backend state for export, usage, fair use, subscription, referral, Wrapped, imports and
/// app data access.
public final class FakeAccountData: @unchecked Sendable {
    /// One entry per call, e.g. `usage:monthly`, `cancel:too_expensive`, `import:export.zip`.
    public internal(set) var log: [String] = []
    /// Fails just these calls (by log prefix).
    public var failing: Set<String> = []
    public var usage: [UsageStats.Period: UsageStats] = [
        .monthly: UsageStats(
            totals: .init(transcriptionSeconds: 1500, words: 2400, insights: 12, memories: 5),
            history: [("2026-10-06", .init(transcriptionSeconds: 600, words: 900, insights: 4, memories: 2))]
        ),
    ]
    public var fairUse = FairUseStatus(
        stage: "none", caseReference: nil, today: .init(used: 0.5, limit: 2), threeDays: .init(used: 1, limit: 8),
        week: .init(used: 2, limit: 10), message: "Your usage is within normal limits."
    )
    public var referral = URL(string: "https://omi.me/r/ref-test")
    public var profile = UserProfile(name: nil, email: nil)
    /// Wrapped by year; a year missing here answers 400, like the backend for anything but 2025.
    public var wrapped: [Int: Wrapped] = [2025: Wrapped(year: 2025, status: .notGenerated)]
    public var apps: [AppDataAccess] = [
        AppDataAccess(id: "zap", name: "Zapier", imageURL: nil, readsConversations: true, readsMemories: false, trigger: "memory_creation"),
    ]
    public var importJobs: [ImportJob] = []
    public var exportBody = Data(#"{"profile":{},"memories":[]}"#.utf8)

    public init() {}
}

public extension FakeAPIClient {
    private func recordAccount(_ kind: String, _ entry: String = "") throws {
        try lock.withLock {
            if let _error { throw _error }
            accountData.log.append(entry.isEmpty ? kind : "\(kind):\(entry)")
            if accountData.failing.contains(kind) { throw APIError.http(status: 500, body: kind) }
        }
    }

    func exportAllData() async throws -> URL {
        try recordAccount("export")
        let folder = FileManager.default.temporaryDirectory.appending(path: "omi-export-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let file = folder.appending(path: "omi-export.json")
        try accountData.exportBody.write(to: file)
        return file
    }

    func usage(period: UsageStats.Period, timeZone _: String) async throws -> UsageStats {
        try recordAccount("usage", period.rawValue)
        let none = UsageStats.Totals(transcriptionSeconds: 0, words: 0, insights: 0, memories: 0)
        return accountData.usage[period] ?? UsageStats(totals: none, history: [])
    }

    func fairUseStatus() async throws -> FairUseStatus {
        try recordAccount("fair-use")
        return accountData.fairUse
    }

    func cancelSubscription(reason: String?, details _: String?) async throws {
        try recordAccount("cancel", reason ?? "-")
    }

    func userProfile() async throws -> UserProfile {
        try recordAccount("profile")
        return accountData.profile
    }

    func referralURL() async throws -> URL? {
        try recordAccount("referral")
        return accountData.referral
    }

    func wrapped(year: Int) async throws -> Wrapped {
        try recordAccount("wrapped", String(year))
        guard let wrapped = accountData.wrapped[year] else {
            throw APIError.http(status: 400, body: "Only year 2025 is currently supported")
        }
        return wrapped
    }

    func generateWrapped(year: Int) async throws {
        try recordAccount("generate-wrapped", String(year))
        accountData.wrapped[year] = Wrapped(year: year, status: .processing, progress: "Reading your conversations")
    }

    func appsWithDataAccess() async throws -> [AppDataAccess] {
        try recordAccount("apps")
        return accountData.apps
    }

    func importLimitless(zip: Data, filename: String, language _: String) async throws -> ImportJob {
        try recordAccount("import", filename)
        let id = "job-\(accountData.importJobs.count + 1)"
        let job = ImportJob(id: id, status: .pending, totalFiles: zip.isEmpty ? 0 : 10, processedFiles: 0)
        accountData.importJobs.insert(job, at: 0)
        return job
    }

    func importJobs() async throws -> [ImportJob] {
        try recordAccount("jobs")
        return accountData.importJobs
    }

    func cancelImportJob(id: String) async throws {
        try recordAccount("cancel-import", id)
        if let index = accountData.importJobs.firstIndex(where: { $0.id == id }) {
            accountData.importJobs[index] = ImportJob(id: id, status: .cancelled, error: "Cancelled by user")
        }
    }

    func deleteImportJob(id: String) async throws {
        try recordAccount("delete-import", id)
        accountData.importJobs.removeAll { $0.id == id }
    }
}
