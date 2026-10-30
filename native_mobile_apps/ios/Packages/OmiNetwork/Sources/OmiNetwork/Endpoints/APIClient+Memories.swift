import Foundation
import OmiCore

public extension APIClient {
    /// `GET v3/memories` (offset paging, at most 500 per page).
    func memories(limit: Int, offset: Int) async throws -> [Memory] {
        let data = try await data(.get, "v3/memories", query: [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
        ])
        return try decode([OmiAPI.MemoryDB].self, from: data).map(MemoryMapper.map)
    }

    /// `POST v3/memories`: returns the stored `MemoryDB`. `manual` for what the user typed in,
    /// `system` for what they told Omi about themselves.
    func createMemory(content: String, category: String) async throws -> Memory {
        let body = try JSONSerialization.data(withJSONObject: ["content": content, "visibility": "private", "category": category])
        let data = try await data(.post, "v3/memories", body: .json(body))
        return try MemoryMapper.map(decode(OmiAPI.MemoryDB.self, from: data))
    }
}

enum MemoryMapper {
    static func map(_ dto: OmiAPI.MemoryDB) -> Memory {
        Memory(
            id: dto.id,
            content: dto.content,
            headline: dto.headline.flatMap { $0.isEmpty ? nil : $0 },
            category: dto.category?.rawValue ?? "other",
            createdAt: BackendDate.parse(dto.createdAt) ?? .distantPast,
            conversationID: dto.conversationId,
            visibility: dto.visibility.flatMap(Memory.Visibility.init(rawValue:)) ?? .private,
            isBaseline: dto.isBaseline ?? false,
            reviewed: dto.reviewed ?? false,
            userReview: dto.userReview,
            captureDevice: dto.primaryCaptureDevice.flatMap { $0.isEmpty ? nil : $0 },
            isLocked: dto.isLocked ?? false,
            veracity: dto.veracity,
            captureConfidence: dto.captureConfidence,
            uncertaintyReasons: dto.uncertaintyReasons ?? [],
            subjectAttribution: dto.subjectAttribution.flatMap { $0 == ._unknown ? nil : $0.rawValue },
            subjectName: subjectName(dto.arguments),
            evidence: (dto.evidence ?? []).map {
                Memory.Evidence(sourceType: $0.sourceType ?? "unknown", sourceID: $0.sourceId, capturedAt: BackendDate.parse($0.capturedAt))
            }
        )
    }

    /// The person a fact is about, when its arguments name one.
    static func subjectName(_ arguments: [String: OmiAnyCodable]?) -> String? {
        guard let arguments else { return nil }
        for key in ["subject_name", "subject", "person", "name", "who"] {
            if let value = arguments[key]?.value as? String {
                let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty, trimmed.count <= 40, trimmed.lowercased() != "user" { return trimmed }
            }
        }
        return nil
    }
}
