import Foundation
import OmiCore

/// A history import (`ImportJobResponse`, backend `routers/imports.py`): a Limitless export zip
/// turned into conversations in the background.
public struct ImportJob: Identifiable, Sendable, Equatable {
    public enum Status: String, Sendable { case pending, processing, completed, failed, cancelled }

    public let id: String
    public let status: Status
    public let totalFiles: Int?
    public let processedFiles: Int?
    public let created: Int?
    public let skipped: Int?
    public let createdAt: Date?
    public let error: String?

    public init(
        id: String, status: Status, totalFiles: Int? = nil, processedFiles: Int? = nil, created: Int? = nil,
        skipped: Int? = nil, createdAt: Date? = nil, error: String? = nil
    ) {
        self.id = id
        self.status = status
        self.totalFiles = totalFiles
        self.processedFiles = processedFiles
        self.created = created
        self.skipped = skipped
        self.createdAt = createdAt
        self.error = error
    }

    public var isRunning: Bool {
        status == .pending || status == .processing
    }

    /// 0…1 while the files are processed.
    public var progress: Double? {
        guard let totalFiles, totalFiles > 0, let processedFiles else { return nil }
        return min(Double(processedFiles) / Double(totalFiles), 1)
    }
}

public extension APIClient {
    /// `POST v1/import/limitless?language=` with the zip as multipart field `file` (at most 100 MB).
    func importLimitless(zip: Data, filename: String, language: String) async throws -> ImportJob {
        var upload = try await request(
            .post, "v1/import/limitless", query: [URLQueryItem(name: "language", value: language)],
            body: .file(field: "file", filename: filename, mimeType: "application/zip", data: zip)
        )
        upload.timeoutInterval = 300
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: upload)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200 ..< 300).contains(status) else {
            throw APIError.http(status: status, body: String(bytes: data.prefix(500), encoding: .utf8) ?? "")
        }
        guard let job = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]).flatMap(ImportJobMapper.map) else {
            throw APIError.decoding("ImportJobResponse")
        }
        return job
    }

    /// `GET v1/import/jobs?limit=`, newest first.
    func importJobs() async throws -> [ImportJob] {
        let data = try await data(.get, "v1/import/jobs", query: [URLQueryItem(name: "limit", value: "50")])
        return (try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []).compactMap(ImportJobMapper.map)
    }

    /// `POST v1/import/jobs/{id}/cancel` (pending or processing only).
    func cancelImportJob(id: String) async throws {
        _ = try await data(.post, "v1/import/jobs/\(id)/cancel")
    }

    /// `DELETE v1/import/jobs/{id}`: the entry only, not its conversations (finished jobs only).
    func deleteImportJob(id: String) async throws {
        _ = try await data(.delete, "v1/import/jobs/\(id)")
    }
}

enum ImportJobMapper {
    static func map(_ json: [String: Any]) -> ImportJob? {
        guard let id = json["job_id"] as? String else { return nil }
        return ImportJob(
            id: id,
            status: (json["status"] as? String).flatMap(ImportJob.Status.init(rawValue:)) ?? .failed,
            totalFiles: json["total_files"] as? Int, processedFiles: json["processed_files"] as? Int,
            created: json["conversations_created"] as? Int, skipped: json["conversations_skipped"] as? Int,
            createdAt: (json["created_at"] as? String).flatMap(BackendDate.parse),
            error: json["error"] as? String
        )
    }
}
