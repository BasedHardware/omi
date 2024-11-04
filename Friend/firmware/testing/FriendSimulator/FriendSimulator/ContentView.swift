//
//  ContentView.swift
//  FriendSimulator
//
//  Created by Eric Bariaux on 23/05/2024.
//

import SwiftUI
import AVFoundation

struct ContentView: View {
    
    @State var audioEngine = AVAudioEngine()
    @State var audioPlayerNode = AVAudioPlayerNode()
    @ObservedObject var bleManager = BLEManager()
   
    @State var recording = false
    @State var chatting = false;
    var body: some View {
        // TODO: switches to choose between possible audio formats
        // and publish those on the proper characteristic
        
        VStack {
            Text("Friend simulator")
            
            Button() {
                if recording {
                    stopRecording()
                    stopChatting()
                } else {
                    startRecording()
                }
            } label: {
                Label(recording ? "stop" : "record", systemImage: recording ? "stop.circle" : "record.circle")
            }

            Button() {
                if chatting {
                    stopChatting()
                    stopRecording()
                } else {
                    startChatting()
                    startRecording()
                }
            } label: {
                Label(chatting ? "stop" : "chat", systemImage: recording ? "stop.circle" : "record.circle")
            }
        }
        .padding()
        .onAppear() {
            bleManager.start()
            setupAudio()
            bleManager.onAudioDataReceived = handleReceivedAudio
        }
    }
    
    func setupAudio() {
        let friendFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 8000.0, channels: 1, interleaved: true)

        // Add playback node for received audio
        audioEngine.attach(audioPlayerNode)
        
        // Check the main mixer's output format and connect audioPlayerNode with matching format
        let mixerOutputFormat = audioEngine.mainMixerNode.outputFormat(forBus: 0)
        audioEngine.connect(audioPlayerNode, to: audioEngine.mainMixerNode, format: mixerOutputFormat)
        
        let input = audioEngine.inputNode
        let bus = 0
        let inputFormat = input.inputFormat(forBus: bus)
        
        let formatConverter = AVAudioConverter(from: inputFormat, to: friendFormat!)
        
        // Tap to send audio data over Bluetooth
        input.installTap(onBus: bus, bufferSize: 160, format: inputFormat) { (buffer, time) in
            if !recording {
                return
            }
            
            if let formatConverter {
                let ratio = friendFormat!.sampleRate / buffer.format.sampleRate
                let pcmBuffer = AVAudioPCMBuffer(pcmFormat: friendFormat!, frameCapacity: AVAudioFrameCount(Double(buffer.frameLength) * ratio))
                var error: NSError? = nil
                
                let inputBlock: AVAudioConverterInputBlock = { inNumPackets, outStatus in
                    outStatus.pointee = AVAudioConverterInputStatus.haveData
                    return buffer
                }
                
                formatConverter.convert(to: pcmBuffer!, error: &error, withInputFrom: inputBlock)
                
                if error != nil {
                    print(error!.localizedDescription)
                } else {
                    var dataLeft = pcmBuffer!.dataInt()
                    while !dataLeft.isEmpty {
                        let block = dataLeft.prefix(160)
                        bleManager.writeAudio(block)
                        usleep(7_000)
                        dataLeft = dataLeft.dropFirst(160)
                    }
                }
            }
        }
        
        // Run the audio engine
        audioEngine.prepare()
        try! audioEngine.start()
    }
    
    func startRecording() {
        recording = true
    }
    
    func stopRecording() {
        recording = false
    }
    
    func startChatting() {
        chatting = true
    }
    
    func stopChatting() {
        chatting = false
    }
    
    func handleReceivedAudio(_ data: Data) {
        guard let friendFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 8000.0, channels: 1, interleaved: true) else { return }
        
        let frameCount = AVAudioFrameCount(data.count) / friendFormat.streamDescription.pointee.mBytesPerFrame
        let buffer = AVAudioPCMBuffer(pcmFormat: friendFormat, frameCapacity: frameCount)!
        buffer.frameLength = frameCount

        data.withUnsafeBytes { (audioBytes: UnsafePointer<Int16>) in
            buffer.int16ChannelData!.pointee.assign(from: audioBytes, count: Int(frameCount))
        }
        
        audioPlayerNode.scheduleBuffer(buffer, at: nil, options: .interrupts, completionHandler: nil)
        if !audioPlayerNode.isPlaying {
            audioPlayerNode.play()
        }
    }
}

extension AVAudioPCMBuffer {
    func dataInt() -> Data {
        let channelCount = 1  // given PCMBuffer channel count is 1
        let channels = UnsafeBufferPointer(start: self.int16ChannelData, count: channelCount)
        let ch0Data = NSData(bytes: channels[0], length:Int(self.frameCapacity * self.format.streamDescription.pointee.mBytesPerFrame))
        return ch0Data as Data
    }
}

#Preview {
    ContentView()
}
