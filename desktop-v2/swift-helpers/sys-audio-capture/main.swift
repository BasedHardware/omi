// sys-audio-capture — captures macOS system audio via ScreenCaptureKit
// and pipes 16 kHz mono Int16 PCM over stdout.
//
// Why ScreenCaptureKit instead of Core Audio Process Taps: on some
// macOS 14.4+/26 systems the kernel silently refuses to route audio
// into CATapDescription taps even with permissions granted (the IOProc
// fires at the right rate with zero-filled buffers). ScreenCaptureKit
// uses a different kernel path and the same TCC "Screen Recording"
// grant the user already approved.
//
// Spawned as a subprocess by the Rust audio-capture plugin.
// Exits on SIGTERM/SIGINT or when stdout pipe breaks.

import AVFoundation
import CoreAudio
import CoreGraphics
import CoreMedia
import Darwin
import Foundation
import ScreenCaptureKit

// MARK: - Logging

func log(_ msg: String) {
    FileHandle.standardError.write("[sys-audio-helper] \(msg)\n".data(using: .utf8)!)
}

// MARK: - Shutdown flag shared with signal handlers

final class ShutdownFlag {
    private let lock = NSLock()
    private var _flag = false
    var value: Bool {
        lock.lock(); defer { lock.unlock() }
        return _flag
    }
    func set() {
        lock.lock(); defer { lock.unlock() }
        _flag = true
    }
}

let shutdown = ShutdownFlag()

// MARK: - Capture stream output

@available(macOS 13.0, *)
final class AudioOutput: NSObject, SCStreamOutput, SCStreamDelegate {
    private let stdout = FileHandle.standardOutput
    private let targetRate: Double = 16_000
    private var converter: AVAudioConverter?
    private var inputFormat: AVAudioFormat?
    private var targetFormat: AVAudioFormat?

    var callbackCount: Int = 0
    var totalFrames: Int = 0
    var maxAbsInput: Float = 0
    var bytesWritten: Int = 0

    func stream(
        _ stream: SCStream,
        didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
        of outputType: SCStreamOutputType
    ) {
        guard outputType == .audio else { return }
        guard CMSampleBufferIsValid(sampleBuffer),
              CMSampleBufferDataIsReady(sampleBuffer) else { return }

        callbackCount += 1

        // Extract the audio description — ScreenCaptureKit delivers
        // non-interleaved Float32 at 48 kHz by default.
        guard let desc = CMSampleBufferGetFormatDescription(sampleBuffer),
              let asbdPtr = CMAudioFormatDescriptionGetStreamBasicDescription(desc)
        else { return }
        let asbd = asbdPtr.pointee

        let numFrames = Int(CMSampleBufferGetNumSamples(sampleBuffer))
        if numFrames == 0 { return }
        totalFrames += numFrames

        // Pull samples into an AudioBufferList.
        var ablPtr: UnsafeMutablePointer<AudioBufferList>?
        var blockBuffer: CMBlockBuffer?
        let ablSize = MemoryLayout<AudioBufferList>.size +
            MemoryLayout<AudioBuffer>.size * Int(asbd.mChannelsPerFrame - 1)
        let ablRaw = UnsafeMutableRawPointer.allocate(
            byteCount: ablSize, alignment: MemoryLayout<AudioBufferList>.alignment
        )
        defer { ablRaw.deallocate() }
        ablPtr = ablRaw.assumingMemoryBound(to: AudioBufferList.self)

        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: nil,
            bufferListOut: ablPtr!,
            bufferListSize: ablSize,
            blockBufferAllocator: kCFAllocatorDefault,
            blockBufferMemoryAllocator: kCFAllocatorDefault,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
            blockBufferOut: &blockBuffer
        )
        guard status == noErr, let abl = ablPtr else { return }

        let ablWrap = UnsafeMutableAudioBufferListPointer(abl)

        // Scan the raw Float32 input for peak (diagnostic).
        for bufIdx in 0..<ablWrap.count {
            if let ptr = ablWrap[bufIdx].mData?
                .assumingMemoryBound(to: Float32.self)
            {
                let samples = Int(ablWrap[bufIdx].mDataByteSize) / 4
                for i in 0..<samples {
                    let a = abs(ptr[i])
                    if a > maxAbsInput { maxAbsInput = a }
                }
            }
        }

        // Lazily build the converter on the first buffer.
        if converter == nil {
            let inFmt = AVAudioFormat(
                commonFormat: .pcmFormatFloat32,
                sampleRate: asbd.mSampleRate,
                channels: AVAudioChannelCount(asbd.mChannelsPerFrame),
                interleaved: (asbd.mFormatFlags & kAudioFormatFlagIsNonInterleaved) == 0
            )
            let outFmt = AVAudioFormat(
                standardFormatWithSampleRate: targetRate,
                channels: 1
            )
            if let inFmt = inFmt, let outFmt = outFmt,
               let c = AVAudioConverter(from: inFmt, to: outFmt)
            {
                inputFormat = inFmt
                targetFormat = outFmt
                converter = c
                log("converter: in=\(asbd.mSampleRate)Hz/\(asbd.mChannelsPerFrame)ch/\(inFmt.isInterleaved ? "interleaved" : "planar") → out=\(targetRate)Hz/1ch")
            } else {
                log("WARN: failed to build AVAudioConverter")
                return
            }
        }

        guard let inputFmt = inputFormat,
              let targetFmt = targetFormat,
              let converter = converter
        else { return }

        // Build an AVAudioPCMBuffer from the AudioBufferList.
        guard let inputBuffer = AVAudioPCMBuffer(
            pcmFormat: inputFmt,
            bufferListNoCopy: abl
        ) else { return }
        inputBuffer.frameLength = AVAudioFrameCount(numFrames)

        let outCapacity = AVAudioFrameCount(
            Double(numFrames) * targetRate / inputFmt.sampleRate + 2
        )
        guard let outputBuffer = AVAudioPCMBuffer(
            pcmFormat: targetFmt,
            frameCapacity: outCapacity
        ) else { return }

        var error: NSError?
        var inputProvided = false
        let convStatus = converter.convert(to: outputBuffer, error: &error) {
            _, outStatus in
            if inputProvided {
                // `.noDataNow` pauses this conversion call without
                // closing the converter — the NEXT `convert()` call can
                // feed a fresh input buffer. `.endOfStream` by contrast
                // locks the converter so it never produces output again.
                outStatus.pointee = .noDataNow
                return nil
            }
            inputProvided = true
            outStatus.pointee = .haveData
            return inputBuffer
        }
        if convStatus == .error {
            if let error = error {
                log("converter error: \(error.localizedDescription)")
            }
            return
        }

        let framesOut = Int(outputBuffer.frameLength)
        if framesOut == 0 { return }
        guard let floatPtr = outputBuffer.floatChannelData?[0] else { return }

        var pcm = Data(count: framesOut * 2)
        pcm.withUnsafeMutableBytes { raw in
            let int16Ptr = raw.bindMemory(to: Int16.self)
            for i in 0..<framesOut {
                let f = max(-1.0, min(1.0, floatPtr[i]))
                int16Ptr[i] = Int16(f * 32767.0)
            }
        }

        do {
            try stdout.write(contentsOf: pcm)
            bytesWritten += pcm.count
        } catch {
            shutdown.set()
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        log("stream stopped with error: \(error.localizedDescription)")
        shutdown.set()
    }

    func reportStats() {
        log("stats: callbacks=\(callbackCount) totalInputFrames=\(totalFrames) maxAbsInput=\(maxAbsInput) bytesWritten=\(bytesWritten)")
    }
}

// MARK: - Entry point

guard #available(macOS 13.0, *) else {
    log("ERROR: ScreenCaptureKit audio requires macOS 13.0+")
    exit(2)
}

// Report identity so we can see what TCC expects to match.
let bundleID = Bundle.main.bundleIdentifier ?? "(none)"
let execPath = Bundle.main.executablePath ?? "(unknown)"
let screenPermission = CGPreflightScreenCaptureAccess()
log("bundleID=\(bundleID)")
log("executable=\(execPath)")
log("screenCaptureAccess=\(screenPermission) (required for SCStream audio)")

if !screenPermission {
    log("requesting screen capture access (TCC prompt)…")
    let granted = CGRequestScreenCaptureAccess()
    log("CGRequestScreenCaptureAccess → \(granted)")
    if !granted {
        log("ERROR: screen capture access was not granted")
        exit(3)
    }
}

signal(SIGTERM) { _ in shutdown.set() }
signal(SIGINT) { _ in shutdown.set() }
signal(SIGPIPE, SIG_IGN)

let output = AudioOutput()
var stream: SCStream?

let setup = DispatchSemaphore(value: 0)
var setupError: Error?

Task {
    do {
        // Need at least one display in the filter even if we only care
        // about audio — SCStream rejects empty content filters.
        let content = try await SCShareableContent.excludingDesktopWindows(
            false, onScreenWindowsOnly: false
        )
        guard let display = content.displays.first else {
            setupError = NSError(
                domain: "sys-audio-helper", code: 10,
                userInfo: [NSLocalizedDescriptionKey: "no displays available"]
            )
            setup.signal()
            return
        }
        log("using display: \(display.displayID) (\(display.width)x\(display.height))")

        let filter = SCContentFilter(display: display, excludingWindows: [])
        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = 48_000
        config.channelCount = 2
        // Minimal video config — we still have to set something.
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)

        let s = SCStream(filter: filter, configuration: config, delegate: output)
        try s.addStreamOutput(output, type: .audio, sampleHandlerQueue: .global(qos: .userInitiated))
        try await s.startCapture()
        stream = s
        log("SCStream started (audio-only)")
        setup.signal()
    } catch {
        setupError = error
        setup.signal()
    }
}

// Wait for async setup to complete.
setup.wait()
if let err = setupError {
    log("ERROR: \(err.localizedDescription)")
    exit(4)
}

// Main loop — wait for shutdown signal.
while !shutdown.value {
    Thread.sleep(forTimeInterval: 0.1)
}

if let s = stream {
    let stopWait = DispatchSemaphore(value: 0)
    Task {
        do {
            try await s.stopCapture()
        } catch {
            log("stopCapture error: \(error.localizedDescription)")
        }
        stopWait.signal()
    }
    stopWait.wait()
}

output.reportStats()
log("exiting cleanly")
