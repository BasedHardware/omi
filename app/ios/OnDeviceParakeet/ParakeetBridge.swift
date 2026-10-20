import Foundation
import FluidAudio

/// Loaded by name only on iOS 17+. Runner deliberately has no compile-time
/// dependency on this iOS-17 module, preserving its iOS-15 deployment target.
@objc(OMIParakeetEngine)
final class ParakeetBridge: NSObject {
    private var work: Task<Void, Never>?
    private var fraction = 0.0
    @objc func run(_ arguments: NSDictionary, completion: @escaping (NSDictionary?, NSError?) -> Void) {
        let method = arguments["method"] as? String ?? ""
        if method == "progress" { completion(["progress": fraction], nil); return }
        if method == "cancel" { work?.cancel(); completion([:], nil); return }
        guard work == nil else { completion(nil, NSError(domain: "OMIParakeet", code: 1)); return }
        let directory = URL(fileURLWithPath: arguments["directory"] as? String ?? "")
        let marker = directory.appendingPathComponent("installed")
        let modelsDirectory = directory.appendingPathComponent("parakeet-tdt-0.6b-v2-coreml")
        work = Task { @MainActor in
            defer { work = nil }
            do {
                if method == "download" {
                    fraction = 0
                    _ = try await AsrModels.downloadAndLoad(to: modelsDirectory, version: .v2, progressHandler: { [weak self] value in
                        Task { @MainActor in if let self { self.fraction = max(self.fraction, value.fractionCompleted) } }
                    })
                    try Task.checkCancellation()
                    try Data().write(to: marker, options: .atomic)
                    fraction = 1
                    completion([:], nil)
                } else if method == "transcribe" {
                    guard FileManager.default.fileExists(atPath: marker.path),
                          let path = arguments["filePath"] as? String else { throw BridgeError.modelMissing }
                    ModelHub.offlineMode = true
                    defer { ModelHub.offlineMode = false }
                    let models = try await AsrModels.load(from: modelsDirectory, version: .v2)
                    let manager = AsrManager(); try await manager.loadModels(models)
                    var state = try TdtDecoderState()
                    let result = try await manager.transcribe(URL(fileURLWithPath: path), decoderState: &state)
                    try Task.checkCancellation()
                    completion(["engine": "parakeet_v2", "text": result.text,
                                "words": buildWordTimings(from: result.tokenTimings ?? []).map {
                                    ["text": $0.word, "start": $0.startTime, "end": $0.endTime] as [String: Any]
                                }], nil)
                } else { throw BridgeError.invalidArguments }
            } catch { completion(nil, error as NSError) }
        }
    }
    private enum BridgeError: Error { case modelMissing, invalidArguments }
}
