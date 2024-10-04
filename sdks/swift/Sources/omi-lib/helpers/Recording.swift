//
//  Recording.swift
//  PALApp
//
//  Created by Eric Bariaux on 29/04/2024.
//

import Foundation
import AVFoundation
import CoreTransferable
import SwiftData


class Recording: Identifiable {

    var id = UUID()
    var filename: String
    var name: String
    var comment = ""
    var timestamp: Date
    var duration_: Double?
    
    var duration: Duration? {
        get {
            if let seconds = duration_ {
                return Duration.seconds(seconds)
            } else {
                return nil
            }
        }
        set {
            if let d = newValue {
                duration_ = d.inSeconds
            } else {
                duration_ = nil
            }
        }
    }

    @Transient var fileURL: URL {
        self.getDocumentsDirectory().appendingPathComponent(filename)
    }

    @Transient private var audioFormat: AVAudioFormat?
    @Transient private var codec: Codec?
    @Transient private var recordingFile: AVAudioFile?
    
    init(filename: String) {
        self.filename = filename
        self.name = filename
        self.timestamp = Self.extractStartDate(filename: filename)
    }
    
    private static func extractStartDate(filename: String) -> Date {
        let timestampString = filename.deletingPrefix("Recording_").deletingSuffix(".wav")
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyyMMdd_HHmmss"
        return dateFormatter.date(from: timestampString) ?? Date()
    }
    
    func readInfo() {
        if let file = try? AVAudioFile(forReading: fileURL) {
            duration = Duration.seconds(Double(file.length) / file.fileFormat.sampleRate)
        }
    }
    
    func startRecording(usingCodec codec: Codec) -> Bool {
        self.codec = codec
        audioFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: codec.sampleRate, channels: 1, interleaved: false)
        
        let recordingFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: codec.sampleRate, channels: 1, interleaved: false)
        guard let recordingFormat else { return false }
        recordingFile = try? AVAudioFile(forWriting: fileURL, settings: recordingFormat.settings, commonFormat: .pcmFormatInt16, interleaved: false)
        return recordingFile != nil
    }
    
    func append(packets: [AudioPacket]) {
        if let recordingFile, let codec {
            do {
                var decodedDataBlock = Data()
                for packet in packets {
                    try decodedDataBlock.append(codec.decode(data: packet.packetData))
                }
                let pcmBuffer = try codec.pcmBuffer(decodedData: decodedDataBlock)
                try recordingFile.write(from: pcmBuffer)
            } catch {
                print(error.localizedDescription)
            }
        }
    }
    
    func getDocumentsDirectory() -> URL {
        let paths = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)
        let documentsDirectory = paths[0]
        return documentsDirectory
    }

    func updateFileURL() {
        // Generate a new filename (e.g., with a new timestamp or unique identifier)
        let newFilename = "Recording_\(UUID().uuidString).wav"
        
        // Create a new file URL with the new filename
        let newFileURL = self.getDocumentsDirectory().appendingPathComponent(newFilename)
        
        do {
            // Copy the contents from the current file URL to the new file URL
            try FileManager.default.copyItem(at: fileURL, to: newFileURL)
            
            // Update the filename property to the new filename
            self.filename = newFilename
            
            // Update the recordingFile with the new file
            if let audioFormat = audioFormat {
                recordingFile = try AVAudioFile(forWriting: newFileURL, settings: audioFormat.settings, commonFormat: .pcmFormatInt16, interleaved: false)
            }
            
        } catch {
            print("Failed to update file URL: \(error.localizedDescription)")
        }
    }
    
    func closeRecording() {
        recordingFile = nil
        codec = nil
    }
}


extension Recording: Hashable {
    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
}

extension Recording: Equatable {
    static func == (lhs: Recording, rhs: Recording) -> Bool {
        lhs.id == rhs.id
    }
}

extension Recording: Transferable {
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .wav) { recording in
            SentTransferredFile(recording.fileURL)
        } importing: { data in
            // TODO: write data to doc folder
            Recording(filename: "")
        }
    }
    
}

extension String {
    func deletingPrefix(_ prefix: String) -> String {
        guard self.hasPrefix(prefix) else { return self }
        return String(self.dropFirst(prefix.count))
    }
    
    func deletingSuffix(_ suffix: String) -> String {
        guard self.hasSuffix(suffix) else { return self }
        return String(self.dropLast(suffix.count))
    }
}

extension Duration {
    var inSeconds: Double {
        let v = components
        return Double(v.seconds) + Double(v.attoseconds) * 1e-18
    }
}

struct RecordingDTO: Codable {
    var id: String
    var filename: String
    var name: String
    var comment: String
    var timestamp: Date
}

extension Recording {
    func toDTO() -> RecordingDTO {
        return RecordingDTO(id: self.id.uuidString, filename: self.filename, name: self.name, comment: self.comment, timestamp: self.timestamp)
    }
}
