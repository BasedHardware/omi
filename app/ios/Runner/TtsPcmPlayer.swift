import AudioToolbox
import Flutter

/// Small app-owned PCM sink used by progressive TTS.
///
/// Audio Queue accepts the decoder's native interleaved Int16 output directly,
/// avoiding a second codec and keeping each HTTP increment independently
/// cancellable. Method-channel calls arrive on the main thread; Audio Queue
/// completions are marshalled back there before touching bookkeeping.
final class TtsPcmPlayer {
  private var queue: AudioQueueRef?
  private var queueStarted = false
  private var pendingBuffers = 0
  private var drainResults: [FlutterResult] = []

  func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "start":
      guard let args = call.arguments as? [String: Any],
            let channels = args["channels"] as? Int,
            let sampleRate = args["sample_rate"] as? Int,
            channels > 0,
            sampleRate > 0 else {
        result(FlutterError(code: "invalid_pcm", message: "Invalid PCM geometry", details: nil))
        return
      }
      stopNow()
      var format = AudioStreamBasicDescription(
        mSampleRate: Double(sampleRate),
        mFormatID: kAudioFormatLinearPCM,
        mFormatFlags: kLinearPCMFormatFlagIsSignedInteger | kLinearPCMFormatFlagIsPacked,
        mBytesPerPacket: UInt32(MemoryLayout<Int16>.size * channels),
        mFramesPerPacket: 1,
        mBytesPerFrame: UInt32(MemoryLayout<Int16>.size * channels),
        mChannelsPerFrame: UInt32(channels),
        mBitsPerChannel: UInt32(MemoryLayout<Int16>.size * 8),
        mReserved: 0
      )
      var createdQueue: AudioQueueRef?
      let status = AudioQueueNewOutput(
        &format,
        { userData, finishedQueue, buffer in
          guard let userData else { return }
          let player = Unmanaged<TtsPcmPlayer>.fromOpaque(userData).takeUnretainedValue()
          DispatchQueue.main.async {
            player.bufferDidFinish(queue: finishedQueue, buffer: buffer)
          }
        },
        Unmanaged.passUnretained(self).toOpaque(),
        nil,
        nil,
        0,
        &createdQueue
      )
      guard status == noErr, let createdQueue else {
        result(audioError("pcm_start_failed", status))
        return
      }
      queue = createdQueue
      queueStarted = false
      result(nil)

    case "feed":
      guard let args = call.arguments as? [String: Any],
            let typedData = args["pcm"] as? FlutterStandardTypedData,
            !typedData.data.isEmpty,
            let queue else {
        result(FlutterError(code: "invalid_pcm", message: "PCM player is not started", details: nil))
        return
      }
      var buffer: AudioQueueBufferRef?
      var status = AudioQueueAllocateBuffer(queue, UInt32(typedData.data.count), &buffer)
      guard status == noErr, let buffer else {
        result(audioError("pcm_buffer_failed", status))
        return
      }
      typedData.data.copyBytes(
        to: buffer.pointee.mAudioData.assumingMemoryBound(to: UInt8.self),
        count: typedData.data.count
      )
      buffer.pointee.mAudioDataByteSize = UInt32(typedData.data.count)
      status = AudioQueueEnqueueBuffer(queue, buffer, 0, nil)
      guard status == noErr else {
        AudioQueueFreeBuffer(queue, buffer)
        result(audioError("pcm_enqueue_failed", status))
        return
      }
      pendingBuffers += 1
      if !queueStarted {
        status = AudioQueueStart(queue, nil)
        guard status == noErr else {
          stopNow()
          result(audioError("pcm_start_failed", status))
          return
        }
        queueStarted = true
      }
      result(nil)

    case "drain":
      if pendingBuffers == 0 {
        result(nil)
      } else {
        drainResults.append(result)
      }

    case "pause":
      guard let queue, queueStarted else {
        result(nil)
        return
      }
      let status = AudioQueuePause(queue)
      result(status == noErr ? nil : audioError("pcm_pause_failed", status))

    case "resume":
      guard let queue else {
        result(nil)
        return
      }
      let status = AudioQueueStart(queue, nil)
      if status == noErr { queueStarted = true }
      result(status == noErr ? nil : audioError("pcm_resume_failed", status))

    case "stop":
      stopNow()
      result(nil)

    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func bufferDidFinish(queue finishedQueue: AudioQueueRef, buffer: AudioQueueBufferRef) {
    guard queue == finishedQueue else { return }
    AudioQueueFreeBuffer(finishedQueue, buffer)
    pendingBuffers = max(0, pendingBuffers - 1)
    finishDrainsIfReady()
  }

  private func stopNow() {
    if let queue {
      AudioQueueStop(queue, true)
      AudioQueueDispose(queue, true)
    }
    queue = nil
    queueStarted = false
    pendingBuffers = 0
    finishDrainsIfReady()
  }

  private func finishDrainsIfReady() {
    guard pendingBuffers == 0 else { return }
    let results = drainResults
    drainResults.removeAll()
    results.forEach { $0(nil) }
  }

  private func audioError(_ code: String, _ status: OSStatus) -> FlutterError {
    FlutterError(code: code, message: "Audio Queue failed with status \(status)", details: nil)
  }
}
