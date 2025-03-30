//
//  Codecs.swift
//  PALApp
//
//  Created by Eric Bariaux on 24/06/2024.
//

import AVFoundation
@_implementationOnly import Opus

// TODO: Can we have some automated tests ?

enum CodecError: Error {
    case invalidAudioFormat
    case audioBufferCreationError
}

protocol Codec {
    var sampleRate: Double { get }
    
    init(sampleRate: Double) throws
    
    func pcmBuffer(decodedData: Data) throws -> AVAudioPCMBuffer
    
    func decode(data: Data) throws -> Data
}

extension Codec {
    func pcmBuffer(decodedData: Data) throws -> AVAudioPCMBuffer {
        guard let audioFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: sampleRate, channels: 1, interleaved: false) else {
            throw CodecError.invalidAudioFormat
        }
        
        guard let pcmBuffer = AVAudioPCMBuffer(pcmFormat: audioFormat, frameCapacity: UInt32(decodedData.count / MemoryLayout<Int16>.size)) else {
            throw CodecError.audioBufferCreationError
        }
        pcmBuffer.frameLength = pcmBuffer.frameCapacity

        let channels = UnsafeBufferPointer(start: pcmBuffer.int16ChannelData, count: Int(pcmBuffer.format.channelCount))
        UnsafeMutableRawPointer(channels[0]).withMemoryRebound(to: UInt8.self, capacity: decodedData.count) {
            (bytes: UnsafeMutablePointer<UInt8>) in
            decodedData.copyBytes(to: bytes, count: decodedData.count)
        }
        return pcmBuffer
    }

    func decode(data: Data) -> Data {
        return data
    }
}

struct PcmCodec: Codec {
    let sampleRate: Double
    
    init(sampleRate: Double) {
        self.sampleRate = sampleRate
    }
}

struct µLawCodec: Codec {
    // From https://web.archive.org/web/20110719132013/http://hazelware.luggle.com/tutorials/mulawcompression.html
    static let muLawToLinearTable: [Int16] = [
         -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
         -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
         -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
         -11900, -11388, -10876, -10364,  -9852,  -9340,  -8828,  -8316,
          -7932,  -7676,  -7420,  -7164,  -6908,  -6652,  -6396,  -6140,
          -5884,  -5628,  -5372,  -5116,  -4860,  -4604,  -4348,  -4092,
          -3900,  -3772,  -3644,  -3516,  -3388,  -3260,  -3132,  -3004,
          -2876,  -2748,  -2620,  -2492,  -2364,  -2236,  -2108,  -1980,
          -1884,  -1820,  -1756,  -1692,  -1628,  -1564,  -1500,  -1436,
          -1372,  -1308,  -1244,  -1180,  -1116,  -1052,   -988,   -924,
           -876,   -844,   -812,   -780,   -748,   -716,   -684,   -652,
           -620,   -588,   -556,   -524,   -492,   -460,   -428,   -396,
           -372,   -356,   -340,   -324,   -308,   -292,   -276,   -260,
           -244,   -228,   -212,   -196,   -180,   -164,   -148,   -132,
           -120,   -112,   -104,    -96,    -88,    -80,    -72,    -64,
            -56,    -48,    -40,    -32,    -24,    -16,     -8,     -1,
          32124,  31100,  30076,  29052,  28028,  27004,  25980,  24956,
          23932,  22908,  21884,  20860,  19836,  18812,  17788,  16764,
          15996,  15484,  14972,  14460,  13948,  13436,  12924,  12412,
          11900,  11388,  10876,  10364,   9852,   9340,   8828,   8316,
           7932,   7676,   7420,   7164,   6908,   6652,   6396,   6140,
           5884,   5628,   5372,   5116,   4860,   4604,   4348,   4092,
           3900,   3772,   3644,   3516,   3388,   3260,   3132,   3004,
           2876,   2748,   2620,   2492,   2364,   2236,   2108,   1980,
           1884,   1820,   1756,   1692,   1628,   1564,   1500,   1436,
           1372,   1308,   1244,   1180,   1116,   1052,    988,    924,
            876,    844,    812,    780,    748,    716,    684,    652,
            620,    588,    556,    524,    492,    460,    428,    396,
            372,    356,    340,    324,    308,    292,    276,    260,
            244,    228,    212,    196,    180,    164,    148,    132,
            120,    112,    104,     96,     88,     80,     72,     64,
             56,     48,     40,     32,     24,     16,      8,      0]
    
    let sampleRate: Double
    
    init(sampleRate: Double) {
        self.sampleRate = sampleRate
    }

    func decode(data: Data) -> Data {
        let i16Array = data.map( { Self.muLawToLinearTable[Int($0)] })
        return i16Array.withUnsafeBufferPointer( { Data(buffer: $0 )})
    }
}

struct OpusCodec: Codec {
    let sampleRate: Double
    let opusDecoder: Opus.Decoder
    
    init(sampleRate: Double) throws {
        self.sampleRate = sampleRate
        guard let opusFormat = AVAudioFormat(opusPCMFormat: .int16, sampleRate: .opus16khz, channels: 1) else {
            throw CodecError.invalidAudioFormat
        }
        opusDecoder = try Opus.Decoder(format: opusFormat)
    }
    
    func decode(data: Data) throws -> Data {
        do {
            return try opusDecoder.decodeToData(data)
        } catch {
            print(error.localizedDescription)
            throw CodecError.audioBufferCreationError
        }
    }
}

