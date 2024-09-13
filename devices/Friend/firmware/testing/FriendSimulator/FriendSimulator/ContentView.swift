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
    @ObservedObject var bleManager = BLEManager()
   
    @State var recording = false
    var body: some View {
        // TODO: switches to choose between possible audio formats
        // and publish those on the proper characteristic
        
        VStack {
            Text("Friend simulator")
            
            Button() {
                if recording {
                    stopRecording()
                } else {
                    startRecording()
                }
            } label: {
                Label(recording ? "stop" : "record", systemImage: recording ? "stop.circle" : "record.circle")
            }
        }
        .padding()
        .onAppear() {
            bleManager.start()
            setupAudio()
        }
    }
    
    func setupAudio() {
        let friendFormat = AVAudioFormat.init(commonFormat: .pcmFormatInt16, sampleRate: 8000.0, channels: 1, interleaved: true)

        let input = audioEngine.inputNode
        let bus = 0
        let inputFormat = input.inputFormat(forBus: bus)
        
        let formatConverter =  AVAudioConverter(from:inputFormat, to: friendFormat!)
        
        input.installTap(onBus: bus, bufferSize: 160, format: inputFormat) { (buffer, time) in
            // Note: implementation may choose other size that requested (and in fact it does) -> need to split later before sending over BLE

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
                }
                else {
                    var dataLeft = pcmBuffer!.dataInt()
                    
                    // TODO: this is ugly, must implement proper background sending
                    while !dataLeft.isEmpty {
                        let block = dataLeft.prefix(160)
                        bleManager.writeAudio(block)
                        usleep(7_000)
                        dataLeft = dataLeft.dropFirst(160)
                    }
                }
            }
        }
        
        //run the engine
        audioEngine.prepare()
        try! audioEngine.start()
    }
    
    func startRecording() {
        recording = true
    }
    
    func stopRecording() {
        recording = false
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
