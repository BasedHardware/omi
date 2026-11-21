import Foundation
import OmiNetwork

/// The live transcript of one call. The server re-sends a segment with the same id as it refines it,
/// so segments upsert by id in arrival order; translations attach to the segment they belong to
/// (Flutter `PhoneCallProvider._handleTranscriptionMessage`).
public struct PhoneCallTranscript: Equatable, Sendable {
    public private(set) var segments: [LiveSegment] = []
    /// Segment id → translated texts (the live interpreter).
    public private(set) var translations: [String: [String]] = [:]

    public init() {}

    public var isEmpty: Bool {
        segments.isEmpty
    }

    public mutating func merge(_ incoming: [LiveSegment]) {
        for segment in incoming {
            if let index = segments.firstIndex(where: { $0.id == segment.id }) {
                segments[index] = segment
            } else {
                segments.append(segment)
            }
        }
    }

    /// Only for segments already shown, like Flutter (a translation never creates a line).
    public mutating func applyTranslations(_ incoming: [String: [String]]) {
        for (id, texts) in incoming where segments.contains(where: { $0.id == id }) {
            translations[id] = texts
        }
    }

    public mutating func removeAll() {
        segments = []
        translations = [:]
    }
}
