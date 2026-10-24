import Foundation
import OmiCore

/// Joins a conversation's audio parts into one local file, as Flutter's `AudioDownloadService`:
/// MP3 parts are concatenated byte for byte, WAV parts get one header over all their samples, and
/// mixed formats fall back to the first part.
enum AudioJoiner {
    /// Downloads the cached parts in order and writes `<name>.mp3|wav` to the temporary folder.
    static func join(_ parts: [AudioPart], name: String, session: URLSession = .shared) async -> URL? {
        let urls = parts.compactMap(\.url)
        guard !urls.isEmpty else { return nil }
        var files: [Data] = []
        for url in urls {
            guard let (data, response) = try? await session.data(from: url),
                  (response as? HTTPURLResponse).map({ (200 ..< 300).contains($0.statusCode) }) ?? true else { return nil }
            files.append(data)
        }
        let wav = files.map(isWAV)
        let (joined, ext): (Data?, String) = if wav.allSatisfy(\.self) {
            (combineWAV(files), "wav")
        } else if wav.allSatisfy({ !$0 }) {
            (files.reduce(Data(), +), "mp3")
        } else {
            (files.first, wav.first == true ? "wav" : "mp3")
        }
        guard let joined else { return nil }
        let target = FileManager.default.temporaryDirectory.appending(path: "\(name).\(ext)")
        try? FileManager.default.removeItem(at: target)
        do {
            try joined.write(to: target)
            return target
        } catch {
            return nil
        }
    }

    static func isWAV(_ data: Data) -> Bool {
        data.count >= 12 && data.prefix(4) == Data("RIFF".utf8) && data[data.startIndex + 8 ..< data.startIndex + 12] == Data("WAVE".utf8)
    }

    /// One RIFF/WAVE file with the first part's format and every part's samples, in order.
    static func combineWAV(_ files: [Data]) -> Data? {
        var format: Data?
        var samples = Data()
        for file in files {
            guard let chunks = chunks(file), let fmt = chunks.fmt else { return nil }
            if format == nil { format = fmt }
            samples.append(chunks.data)
        }
        guard let format else { return nil }
        var out = Data("RIFF".utf8)
        out.append(le32(UInt32(4 + 8 + format.count + 8 + samples.count)))
        out.append(Data("WAVE".utf8))
        out.append(Data("fmt ".utf8))
        out.append(le32(UInt32(format.count)))
        out.append(format)
        out.append(Data("data".utf8))
        out.append(le32(UInt32(samples.count)))
        out.append(samples)
        return out
    }

    /// The `fmt ` body and the `data` body of a WAV file.
    private static func chunks(_ file: Data) -> (fmt: Data?, data: Data)? {
        let bytes = [UInt8](file)
        guard isWAV(file) else { return nil }
        var offset = 12
        var fmt: Data?
        while offset + 8 <= bytes.count {
            let id = String(bytes: bytes[offset ..< offset + 4], encoding: .ascii)
            let size = Int(bytes[offset + 4]) | Int(bytes[offset + 5]) << 8 | Int(bytes[offset + 6]) << 16 | Int(bytes[offset + 7]) << 24
            let body = offset + 8
            let end = min(bytes.count, body + size)
            if id == "fmt " { fmt = Data(bytes[body ..< end]) }
            if id == "data" { return (fmt, Data(bytes[body ..< end])) }
            offset = body + size + (size & 1)
        }
        return nil
    }

    private static func le32(_ value: UInt32) -> Data {
        withUnsafeBytes(of: value.littleEndian) { Data($0) }
    }
}
