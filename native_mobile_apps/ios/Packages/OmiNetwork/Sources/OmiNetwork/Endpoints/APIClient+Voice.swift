import Foundation

public extension APIClient {
    /// `GET v3/speech-profile`.
    func hasSpeechProfile() async throws -> Bool {
        let data = try await data(.get, "v3/speech-profile")
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return object?["has_profile"] as? Bool ?? false
    }

    /// `POST v3/upload-audio` (multipart `file`). The server keeps 5 to 180 s of speech.
    func uploadSpeechProfile(wav: Data) async throws {
        _ = try await data(.post, "v3/upload-audio", body: .file(field: "file", filename: "voice.wav", mimeType: "audio/wav", data: wav))
    }
}
