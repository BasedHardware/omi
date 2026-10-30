import Foundation
import OmiAudio
import OmiDevice
import OmiNetwork

/// Live audio written to disk in the WAL format the backend decodes (`utils/sync/files.py`
/// `decode_pcm_file_to_wav`): `[u32 LE length][frame]…`.
///
/// Phone mic: 320 bytes of PCM16 per frame (10 ms), named `audio_phonemic_pcm16_16000_1_fs160_<epoch>.bin`
/// (dropped connection, or a kept copy: Flutter's phone-mic WAL) or `audio_omibatchphone_…`
/// (Transcribe later). Both mark the conversation as recorded by the phone. The Omi (kept copies
/// only): one opus packet per frame, named like the Omi's own offline recordings.
@MainActor
final class PhoneAudioFile {
    enum Kind: Equatable {
        /// Waits for upload; `manual` is Transcribe later (uploaded when asked).
        case phone(manual: Bool)
        /// Store audio on phone: a copy of phone audio that also streamed.
        case keptPhone
        /// Store audio on phone: a copy of the Omi's live audio (`device` is its id).
        case keptDevice(device: String, codec: OmiGATT.Codec)
    }

    static let frameBytes = 320
    static let frameSeconds = 0.01

    private(set) var recording: PendingRecording
    private let handle: FileHandle?
    /// Phone PCM is cut into fixed frames; the Omi's packets are frames already.
    private let fixedFrames: Bool
    private var remainder = Data()
    private var unsavedFrames = 0

    convenience init(directory: URL, manual: Bool, owner: String?, startedAt: Date) {
        self.init(directory: directory, kind: .phone(manual: manual), owner: owner, startedAt: startedAt)
    }

    init(directory: URL, kind: Kind, owner: String?, startedAt: Date) {
        let prefix: String
        var frameDuration = Self.frameSeconds
        switch kind {
        case let .phone(manual): prefix = "audio_\(manual ? "omibatchphone" : "phonemic")_pcm16_16000_1_fs160_"
        case .keptPhone: prefix = "audio_phonemic_pcm16_16000_1_fs160_"
        case let .keptDevice(device, codec):
            frameDuration = OfflineRecordings.frameDuration(codec)
            let samples = Int((frameDuration * Double(codec.sampleRate)).rounded())
            let name = device.lowercased().filter { $0.isLetter || $0.isNumber }
            prefix = "audio_\(name.isEmpty ? "omi" : name)_\(codec.listenValue)_\(codec.sampleRate)_1_fs\(samples)_"
        }
        fixedFrames = if case .keptDevice = kind { false } else { true }
        var filename = prefix + "\(Int(startedAt.timeIntervalSince1970)).bin"
        var millis = Int(startedAt.timeIntervalSince1970 * 1000)
        while FileManager.default.fileExists(atPath: directory.appending(path: filename).path) {
            millis += 1
            filename = prefix + "\(millis).bin"
        }
        let url = directory.appending(path: filename)
        FileManager.default.createFile(atPath: url.path, contents: nil)
        handle = try? FileHandle(forWritingTo: url)
        let kept: Bool? = if case .phone = kind { nil } else { true }
        recording = PendingRecording(
            filename: filename, startedAt: startedAt.timeIntervalSince1970, frames: 0, frameDuration: frameDuration,
            owner: owner, manual: kind == .phone(manual: true) ? true : nil, kept: kept
        )
    }

    /// Appends audio; returns true about every two seconds of it (time to save the queue state).
    @discardableResult
    func append(_ audio: Data) -> Bool {
        var bytes = Data()
        var frames = 0
        if fixedFrames {
            remainder.append(audio)
            while remainder.count >= Self.frameBytes {
                bytes += UInt32(Self.frameBytes).littleEndianData + remainder.prefix(Self.frameBytes)
                remainder.removeFirst(Self.frameBytes)
                frames += 1
            }
        } else if !audio.isEmpty {
            bytes = UInt32(audio.count).littleEndianData + audio
            frames = 1
        }
        guard frames > 0 else { return false }
        try? handle?.write(contentsOf: bytes)
        recording.frames += frames
        unsavedFrames += frames
        guard Double(unsavedFrames) * recording.frameDuration >= 2 else { return false }
        unsavedFrames = 0
        try? handle?.synchronize()
        return true
    }

    func close() {
        try? handle?.synchronize()
        try? handle?.close()
    }
}

/// Where a kept copy's audio comes from (Store audio on phone).
public enum KeptAudioSource: Equatable, Sendable {
    case phone
    /// The Omi's live stream; only opus is kept (what every current Omi sends).
    case device(codec: OmiGATT.Codec)
}

extension SyncStore: PhoneAudioBuffering {
    public func beginPhoneAudio(manual: Bool) {
        guard phoneFile == nil else { return }
        let file = PhoneAudioFile(directory: files.directory, manual: manual, owner: userID(), startedAt: .now)
        phoneFile = file
        files.update { $0.phoneOpen = file.recording }
    }

    public func appendPhoneAudio(_ pcm: Data) {
        guard let phoneFile, phoneFile.append(pcm) else { return }
        files.update { $0.phoneOpen = phoneFile.recording }
    }

    /// The file joins the queue; one recorded offline uploads right away (Transcribe later waits).
    public func endPhoneAudio() {
        guard let phoneFile else { return }
        phoneFile.close()
        self.phoneFile = nil
        files.adopt(phoneFile.recording)
        refresh()
        if phoneFile.recording.manual != true { uploadSoon() }
    }

    public func beginKeptCopy(_ source: KeptAudioSource) {
        guard keptFile == nil else { return }
        let kind: PhoneAudioFile.Kind
        switch source {
        case .phone: kind = .keptPhone
        case let .device(codec):
            guard codec == .opus || codec == .opusFS320 else { return }
            kind = .keptDevice(device: link?.storageDeviceID ?? "omi", codec: codec)
        }
        let file = PhoneAudioFile(directory: files.directory, kind: kind, owner: userID(), startedAt: .now)
        keptFile = file
        files.update { $0.keptOpen = file.recording }
    }

    public func appendKeptCopy(_ audio: Data) {
        guard let keptFile, keptFile.append(audio) else { return }
        files.update { $0.keptOpen = keptFile.recording }
    }

    /// The copy joins the recordings on the phone (nothing uploads).
    public func endKeptCopy() {
        guard let keptFile else { return }
        keptFile.close()
        self.keptFile = nil
        files.adopt(keptFile.recording)
        refresh()
    }
}

public extension SyncStore {
    /// Recordings made with the phone's microphone and still on the phone, oldest first.
    var phoneRecordings: [PendingRecording] {
        recordings.filter(\.isPhone)
    }

    /// Recordings the Omi kept and still on the phone.
    var deviceRecordings: [PendingRecording] {
        recordings.filter { !$0.isPhone }
    }

    /// "Process now": this recording uploads at once (a Transcribe later one stops waiting). A kept
    /// copy is already on the backend: uploading it again would duplicate the conversation.
    func process(_ filename: String) async {
        guard files.state.recordings.first(where: { $0.filename == filename })?.isKept != true else { return }
        files.update { state in
            guard let index = state.recordings.firstIndex(where: { $0.filename == filename }) else { return }
            state.recordings[index].manual = nil
            if state.recordings[index].jobID == nil { state.recordings[index].failedJobs = 0 }
        }
        refresh()
        await uploadPending()
    }

    /// The recording as a WAV file in the temporary folder (to play or share), decoded here:
    /// Opus frames from the Omi, PCM16 from the phone.
    func audioFile(for filename: String) -> URL? {
        guard let recording = files.state.recordings.first(where: { $0.filename == filename }),
              let data = files.data(for: recording) else { return nil }
        let frames = Self.frames(in: data)
        let pcm: Data
        if recording.isPCM {
            pcm = frames.reduce(into: Data()) { $0 += $1 }
        } else {
            guard let decoded = OpusFileDecoder.decode(frames) else { return nil }
            pcm = decoded
        }
        guard !pcm.isEmpty else { return nil }
        let url = URL.temporaryDirectory.appending(path: (filename as NSString).deletingPathExtension + ".wav")
        do {
            try PCMWave.wav(pcm16: pcm, sampleRate: 16000).write(to: url, options: .atomic)
        } catch {
            return nil
        }
        return url
    }

    /// Splits `[u32 LE length][frame]…`; stops at a frame cut short.
    nonisolated static func frames(in data: Data) -> [Data] {
        let bytes = [UInt8](data)
        var frames: [Data] = []
        var offset = 0
        while offset + 4 <= bytes.count {
            let length = Int(bytes[offset]) | Int(bytes[offset + 1]) << 8 | Int(bytes[offset + 2]) << 16 | Int(bytes[offset + 3]) << 24
            guard length > 0, offset + 4 + length <= bytes.count else { break }
            frames.append(Data(bytes[(offset + 4) ..< (offset + 4 + length)]))
            offset += 4 + length
        }
        return frames
    }
}
