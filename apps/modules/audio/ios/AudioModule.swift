import ExpoModulesCore
import AVFoundation

public class AudioModule: Module {
  public func definition() -> ModuleDefinition {
    Name("Audio")
      AsyncFunction("convert") { (source: Data, promise: Promise) in
          let fileManager = FileManager.default
          
          // Source and destinations
          let sourceURL = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("source.aac")
          let outputURL = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("output.m4a")
          if fileManager.fileExists(atPath: sourceURL.path) {
            do {
              try fileManager.removeItem(at: sourceURL)
            } catch {
              promise.reject(error)
              return
            }
          }
          if fileManager.fileExists(atPath: outputURL.path) {
            do {
              try fileManager.removeItem(at: outputURL)
            } catch {
              promise.reject(error)
              return
            }
          }
          
          // Init Converter
          try source.write(to: sourceURL)
          let audioAsset = AVAsset(url: sourceURL)
          let exportSession = AVAssetExportSession(asset: audioAsset, presetName: AVAssetExportPresetAppleM4A)!
          
          // Converter parameters
          exportSession.outputFileType = .m4a
          exportSession.outputURL = outputURL
          
          // Run
          exportSession.exportAsynchronously {
              if exportSession.status == .completed {
                do {
                  let outputData = try Data(contentsOf: outputURL)
                  promise.resolve(outputData)
                } catch {
                  promise.reject(error)
                }
              } else if exportSession.status == .failed {
                let error = exportSession.error ?? NSError(domain: "AudioModule", code: -1, userInfo: nil)
                promise.reject(error)
              }
          }
      }
  }
}
