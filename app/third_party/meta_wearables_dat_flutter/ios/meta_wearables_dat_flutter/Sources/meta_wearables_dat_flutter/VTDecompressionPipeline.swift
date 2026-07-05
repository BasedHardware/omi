// HEVC (`hvc1`) → BGRA decoding pipeline.
//
// When `videoCodec: .hvc1` is selected on iOS, the MWDATCamera SDK emits
// compressed `CMSampleBuffer`s carrying HEVC NAL units. This pipeline:
//
//   - Lazily builds a `VTDecompressionSession` keyed on the
//     `CMVideoFormatDescription` of the first incoming sample buffer,
//     output pixel format `kCVPixelFormatType_32BGRA`.
//   - Decodes each sample synchronously so the resulting `CVPixelBuffer`
//     can be handed to Flutter's texture path on the same frame.
//   - Optionally surfaces the compressed NAL bytes (with VPS/SPS/PPS
//     prepended on every keyframe, in Annex-B form) so host apps can
//     forward them to an `mp4` muxer or to disk through
//     `videoFramesStream`.
//
// Software-only fallback is requested at build time via
// `kVTVideoDecoderSpecification_EnableHardwareAcceleratedVideoDecoder = false`
// when the caller flags `softwareOnly` — that path is used in slice H
// when background streaming is active (hardware decoders are killed by
// the OS as soon as the app backgrounds).

import Foundation
import VideoToolbox
import CoreMedia
import CoreVideo

@MainActor
final class VTDecompressionPipeline {
  /// Output pixel format. Matches the format the regular `.raw` capture
  /// path produces so downstream texture code doesn't need to special-case.
  private let outputPixelFormat: OSType = kCVPixelFormatType_32BGRA

  /// When true, build the `VTDecompressionSession` with hardware
  /// acceleration disabled. Costs a bit of CPU but is required while the
  /// app is backgrounded.
  var softwareOnly: Bool = false {
    didSet { if oldValue != softwareOnly { invalidate() } }
  }

  /// Session is rebuilt whenever the format description changes (e.g.
  /// resolution change mid-stream). We compare by identity since
  /// CoreMedia recycles `CMFormatDescriptionRef`s for identical descs.
  private var session: VTDecompressionSession?
  private var formatDescription: CMFormatDescription?

  init() {}

  deinit {
    if let session = session {
      VTDecompressionSessionInvalidate(session)
    }
  }

  /// Releases the underlying `VTDecompressionSession`. The next
  /// `decode(...)` call will rebuild it.
  func invalidate() {
    if let session = session {
      VTDecompressionSessionInvalidate(session)
      self.session = nil
    }
    formatDescription = nil
  }

  /// Synchronously decodes one HEVC `CMSampleBuffer` to a BGRA
  /// `CVPixelBuffer`. Returns `nil` when the session could not be
  /// built or the decode itself failed; the caller should log and
  /// continue rather than crash.
  func decode(_ sampleBuffer: CMSampleBuffer) -> CVPixelBuffer? {
    guard let desc = CMSampleBufferGetFormatDescription(sampleBuffer) else {
      return nil
    }
    if !ensureSession(for: desc) {
      return nil
    }
    guard let session = session else { return nil }

    var decoded: CVPixelBuffer?
    // Bit 0 of VTDecodeFrameFlags is "enable async decompression"; the
    // Swift bridging name has changed across SDKs so we use the raw
    // bitmask directly.
    let flags = VTDecodeFrameFlags(rawValue: 1)
    var infoFlags = VTDecodeInfoFlags()
    let status = VTDecompressionSessionDecodeFrame(
      session,
      sampleBuffer: sampleBuffer,
      flags: flags,
      infoFlagsOut: &infoFlags,
      outputHandler: { _, _, buffer, _, _ in
        decoded = buffer
      },
    )
    if status != noErr {
      print("[meta_wearables_dat_flutter] VTDecompressionSessionDecodeFrame " +
        "failed status=\(status)")
      return nil
    }
    // Wait briefly for the async output handler. In practice the
    // decoder runs on a dedicated thread and completes in a few hundred
    // microseconds for HEVC at 720p.
    VTDecompressionSessionWaitForAsynchronousFrames(session)
    return decoded
  }

  /// (Re-)builds the `VTDecompressionSession` when the format
  /// description changes. Returns `true` if a session is ready for
  /// decoding.
  private func ensureSession(for desc: CMFormatDescription) -> Bool {
    if let existing = formatDescription,
       CFEqual(existing, desc),
       session != nil {
      return true
    }
    if let stale = session {
      VTDecompressionSessionInvalidate(stale)
      session = nil
    }
    formatDescription = desc

    let dims = CMVideoFormatDescriptionGetDimensions(desc)
    var imageBufferAttrs: [String: Any] = [
      kCVPixelBufferPixelFormatTypeKey as String: outputPixelFormat,
      kCVPixelBufferWidthKey as String: Int(dims.width),
      kCVPixelBufferHeightKey as String: Int(dims.height),
      kCVPixelBufferIOSurfacePropertiesKey as String: [:] as [String: Any],
    ]
    if softwareOnly {
      imageBufferAttrs[
        kCVPixelBufferOpenGLCompatibilityKey as String] = false
    }

    var spec: [String: Any] = [:]
    if softwareOnly {
      spec[
        kVTVideoDecoderSpecification_EnableHardwareAcceleratedVideoDecoder
          as String] = false
    } else {
      spec[
        kVTVideoDecoderSpecification_EnableHardwareAcceleratedVideoDecoder
          as String] = true
    }

    var newSession: VTDecompressionSession?
    let status = VTDecompressionSessionCreate(
      allocator: kCFAllocatorDefault,
      formatDescription: desc,
      decoderSpecification: spec as CFDictionary,
      imageBufferAttributes: imageBufferAttrs as CFDictionary,
      outputCallback: nil,
      decompressionSessionOut: &newSession,
    )
    if status != noErr {
      print("[meta_wearables_dat_flutter] VTDecompressionSessionCreate " +
        "failed status=\(status) software=\(softwareOnly)")
      session = nil
      return false
    }
    session = newSession
    return true
  }

  /// Extracts the HEVC `VPS`, `SPS`, and `PPS` parameter sets from a
  /// `CMVideoFormatDescription` and returns them as Annex-B encoded
  /// NAL units (i.e. each prefixed with the `00 00 00 01` start code).
  /// Returns `nil` when the format description does not carry HEVC
  /// parameter sets (e.g. for `kCMVideoCodecType_H264`).
  static func annexBParameterSets(
    from desc: CMFormatDescription,
  ) -> Data? {
    var count = 0
    let probe = CMVideoFormatDescriptionGetHEVCParameterSetAtIndex(
      desc,
      parameterSetIndex: 0,
      parameterSetPointerOut: nil,
      parameterSetSizeOut: nil,
      parameterSetCountOut: &count,
      nalUnitHeaderLengthOut: nil,
    )
    if probe != noErr || count == 0 { return nil }

    var out = Data()
    for i in 0..<count {
      var pointer: UnsafePointer<UInt8>?
      var size = 0
      let status = CMVideoFormatDescriptionGetHEVCParameterSetAtIndex(
        desc,
        parameterSetIndex: i,
        parameterSetPointerOut: &pointer,
        parameterSetSizeOut: &size,
        parameterSetCountOut: nil,
        nalUnitHeaderLengthOut: nil,
      )
      if status == noErr, let pointer = pointer, size > 0 {
        out.append(contentsOf: [0x00, 0x00, 0x00, 0x01])
        out.append(pointer, count: size)
      }
    }
    return out.isEmpty ? nil : out
  }

  /// Reads the (length-prefixed AVCC-style) NAL bytes from a sample
  /// buffer's underlying `CMBlockBuffer` and returns them as an
  /// Annex-B encoded `Data` (start codes between NAL units instead of
  /// 4-byte length prefixes).
  static func annexBNalBytes(
    from sampleBuffer: CMSampleBuffer,
  ) -> Data? {
    guard let block = CMSampleBufferGetDataBuffer(sampleBuffer) else {
      return nil
    }
    var totalLength = 0
    var rawPointer: UnsafeMutablePointer<Int8>?
    let status = CMBlockBufferGetDataPointer(
      block,
      atOffset: 0,
      lengthAtOffsetOut: nil,
      totalLengthOut: &totalLength,
      dataPointerOut: &rawPointer,
    )
    if status != noErr || rawPointer == nil { return nil }

    let bytes = UnsafeMutableRawPointer(rawPointer!).assumingMemoryBound(
      to: UInt8.self,
    )
    var out = Data()
    out.reserveCapacity(totalLength + 16)
    var offset = 0
    while offset + 4 <= totalLength {
      // AVCC NAL units are prefixed with a 4-byte big-endian length.
      let length = (UInt32(bytes[offset]) << 24) |
        (UInt32(bytes[offset + 1]) << 16) |
        (UInt32(bytes[offset + 2]) << 8) |
        UInt32(bytes[offset + 3])
      offset += 4
      if length == 0 || offset + Int(length) > totalLength { break }
      out.append(contentsOf: [0x00, 0x00, 0x00, 0x01])
      out.append(bytes + offset, count: Int(length))
      offset += Int(length)
    }
    return out.isEmpty ? nil : out
  }

  /// Reports whether a sample buffer's primary attachment marks it as a
  /// keyframe (i.e. independent of any other frame).
  static func isKeyframe(_ sampleBuffer: CMSampleBuffer) -> Bool {
    guard
      let attachments = CMSampleBufferGetSampleAttachmentsArray(
        sampleBuffer,
        createIfNecessary: false,
      ) as? [[CFString: Any]],
      let first = attachments.first
    else {
      // No attachments → assume keyframe (matches Apple's behaviour for
      // single-NAL CMSampleBuffers).
      return true
    }
    if let dependsOnOthers = first[kCMSampleAttachmentKey_DependsOnOthers]
      as? Bool {
      return !dependsOnOthers
    }
    if let notSync = first[kCMSampleAttachmentKey_NotSync] as? Bool {
      return !notSync
    }
    return true
  }
}
