import Foundation
import OmiDevice

/// A recording from the Omi's storage, on disk until the backend has it.
public struct PendingRecording: Codable, Equatable, Sendable {
    public var filename: String
    /// Epoch seconds of the first frame.
    public var startedAt: Double
    public var frames: Int
    public var frameDuration: Double
    /// Set once uploaded (HTTP 202); the file stays until the job completes.
    public var jobID: String?
    public var failedJobs = 0
    /// Who was signed in when the Omi recorded it: it is only ever uploaded to that account.
    public var owner: String?
    /// Recorded with Transcribe later: waits for "Process now" instead of uploading by itself.
    public var manual: Bool?
    /// Store audio on phone: a copy of audio the backend already got live. It stays here (to play
    /// or share) and is never uploaded.
    public var kept: Bool?

    /// A copy kept by Store audio on phone (nothing to upload).
    public var isKept: Bool {
        kept == true
    }

    public var seconds: Double {
        Double(frames) * frameDuration
    }

    /// Recorded by the phone's microphone (offline or Transcribe later), not by the Omi.
    public var isPhone: Bool {
        filename.contains("_phonemic_") || filename.contains("_omibatchphone_")
    }

    /// The format of its frames: Opus from the Omi, PCM16 from the phone.
    public var isPCM: Bool {
        filename.contains("_pcm16_")
    }
}

/// What survives an app relaunch: recordings waiting for upload, the one being written, and how
/// far the Omi's storage has been saved here.
struct OfflineSyncState: Codable, Equatable {
    var recordings: [PendingRecording] = []
    var open: PendingRecording?
    /// Records below `durableSeq` of ring `ringID` are on disk here (custody firmware only).
    var ringID: UInt64?
    var durableSeq: UInt64?
    /// Unread records on the Omi when last seen.
    var devicePending: UInt64 = 0
    var secondsPerRecord: Double = 0.1
    /// An Omi with offline storage has been seen: the status row has something to say.
    var known = false
    /// The phone-mic file being written (`SyncStore+Phone.swift`).
    var phoneOpen: PendingRecording?
    /// The kept copy of live audio being written (Store audio on phone).
    var keptOpen: PendingRecording?
}

/// The files behind offline sync, in Flutter's WAL format: `[u32 LE length][frame]…`, named
/// `audio_<device>_<codec>_<rate>_1_fs<samples>_<epoch>.bin` (`wal.dart` `getFileNameByTimeStarts`)
/// so `v2/sync-local-files` can decode and date them.
@MainActor
final class OfflineRecordings {
    /// Longer stretches are cut so one upload stays small (~1.2 MB of Opus).
    static let maxSeconds: Double = 300
    /// A jump in the record clock this large starts a new recording: the Omi was off or asleep.
    static let gapSeconds: Double = 10

    let directory: URL
    private(set) var state: OfflineSyncState
    private var handle: FileHandle?

    init(directory: URL) {
        self.directory = directory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        state = (try? Data(contentsOf: directory.appending(path: "state.json")))
            .flatMap { try? JSONDecoder().decode(OfflineSyncState.self, from: $0) } ?? OfflineSyncState()
        // Killed mid-transfer: keep what reached the disk.
        if state.open != nil { closeOpen() }
        if let phone = state.phoneOpen { adopt(phone) }
        if let kept = state.keptOpen { adopt(kept) }
    }

    /// A finished file joins the queue with the frames it really holds (none: it is dropped).
    func adopt(_ recording: PendingRecording) {
        var recording = recording
        if state.phoneOpen?.filename == recording.filename { state.phoneOpen = nil }
        if state.keptOpen?.filename == recording.filename { state.keptOpen = nil }
        recording.frames = Self.validate(directory.appending(path: recording.filename))
        if recording.frames > 0 {
            state.recordings.append(recording)
        } else {
            try? FileManager.default.removeItem(at: directory.appending(path: recording.filename))
        }
        save()
    }

    func update(_ change: (inout OfflineSyncState) -> Void) {
        change(&state)
        save()
    }

    func save() {
        guard let data = try? JSONEncoder().encode(state) else { return }
        try? data.write(to: directory.appending(path: "state.json"), options: .atomic)
    }

    /// Appends one record's frames. Returns true when this closed a finished recording.
    @discardableResult
    func append(_ record: OmiStorage.Record, deviceID: String, codec: OmiGATT.Codec, owner: String?, now: Date) -> Bool {
        guard !record.frames.isEmpty else { return false }
        let duration = Self.frameDuration(codec)
        let expected = state.open.map { $0.startedAt + $0.seconds }
        let time = record.timestamp.map(Double.init) ?? expected ?? now.timeIntervalSince1970
        var closed = false
        if let open = state.open, let expected,
           time > expected + Self.gapSeconds || time + Self.gapSeconds < expected || open.seconds >= Self.maxSeconds {
            closeOpen()
            closed = true
        }
        if state.open == nil { openRecording(at: time, deviceID: deviceID, codec: codec, frameDuration: duration, owner: owner) }
        var bytes = Data()
        for frame in record.frames {
            bytes += UInt32(frame.count).littleEndianData + frame
        }
        handle?.write(bytes)
        state.open?.frames += record.frames.count
        state.secondsPerRecord = state.secondsPerRecord * 0.98 + Double(record.frames.count) * duration * 0.02
        return closed
    }

    /// Flushes the open file to storage (before the Omi is told it may free those records).
    func sync() {
        try? handle?.synchronize()
        save()
    }

    /// Finishes the open recording: it joins the upload queue (an empty one is dropped).
    func closeOpen() {
        try? handle?.synchronize()
        try? handle?.close()
        handle = nil
        guard var open = state.open else { return }
        state.open = nil
        open.frames = Self.validate(directory.appending(path: open.filename))
        if open.frames > 0 {
            state.recordings.append(open)
        } else {
            try? FileManager.default.removeItem(at: directory.appending(path: open.filename))
        }
        save()
    }

    func data(for recording: PendingRecording) -> Data? {
        try? Data(contentsOf: directory.appending(path: recording.filename))
    }

    func remove(_ filename: String) {
        try? FileManager.default.removeItem(at: directory.appending(path: filename))
        update { $0.recordings.removeAll { $0.filename == filename } }
    }

    func setJob(_ jobID: String?, for filename: String, failed: Bool = false) {
        update { state in
            guard let index = state.recordings.firstIndex(where: { $0.filename == filename }) else { return }
            state.recordings[index].jobID = jobID
            if failed { state.recordings[index].failedJobs += 1 }
        }
    }

    private func openRecording(at time: Double, deviceID: String, codec: OmiGATT.Codec, frameDuration: Double, owner: String?) {
        let device = deviceID.lowercased().filter { $0.isLetter || $0.isNumber }
        let samples = Int((frameDuration * Double(codec.sampleRate)).rounded())
        let prefix = "audio_\(device)_\(codec.listenValue)_\(codec.sampleRate)_1_fs\(samples)_"
        var filename = prefix + "\(Int(time)).bin"
        // Same second as an earlier file: milliseconds keep the name unique and still parse as a time.
        var millis = Int(time * 1000)
        while FileManager.default.fileExists(atPath: directory.appending(path: filename).path) {
            millis += 1
            filename = prefix + "\(millis).bin"
        }
        let url = directory.appending(path: filename)
        FileManager.default.createFile(atPath: url.path, contents: nil)
        handle = try? FileHandle(forWritingTo: url)
        state.open = PendingRecording(filename: filename, startedAt: time, frames: 0, frameDuration: frameDuration, owner: owner)
    }

    static func frameDuration(_ codec: OmiGATT.Codec) -> Double {
        codec == .opusFS320 ? 0.02 : 0.01
    }

    /// Counts whole frames and cuts off a frame the app was killed in the middle of writing.
    static func validate(_ url: URL) -> Int {
        guard let data = try? Data(contentsOf: url) else { return 0 }
        let bytes = [UInt8](data)
        var offset = 0
        var frames = 0
        while offset + 4 <= bytes.count {
            let length = Int(bytes[offset]) | Int(bytes[offset + 1]) << 8 | Int(bytes[offset + 2]) << 16 | Int(bytes[offset + 3]) << 24
            guard length > 0, offset + 4 + length <= bytes.count else { break }
            offset += 4 + length
            frames += 1
        }
        if offset < bytes.count, let handle = try? FileHandle(forWritingTo: url) {
            try? handle.truncate(atOffset: UInt64(offset))
            try? handle.close()
        }
        return frames
    }
}

extension UInt32 {
    var littleEndianData: Data {
        withUnsafeBytes(of: littleEndian) { Data($0) }
    }
}
