//
//  ContentView.swift
//  OmiSimulator
//
//  Created by Eric Bariaux on 23/05/2024.
//

import SwiftUI
import AVFoundation

struct ContentView: View {

    @State var audioEngine = AVAudioEngine()
    @ObservedObject var bleManager = BLEManager()

    @State var recording = false
    @State private var batterySlider: Double = 87

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Omi simulator")
                .font(.title2)
            Text("Advertising as Omi Devkit")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Divider()

            HStack {
                Text("Battery \(Int(batterySlider))%")
                Slider(value: $batterySlider, in: 0...100, step: 1)
                    .onChange(of: batterySlider) { _, newValue in
                        bleManager.setBatteryLevel(UInt8(newValue))
                    }
            }

            Toggle("Charging", isOn: Binding(
                get: { bleManager.charging },
                set: { bleManager.setCharging($0) }
            ))

            Text("LED \(bleManager.ledBrightness) · Mic gain \(bleManager.microphoneGain)")
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack(spacing: 12) {
                Button {
                    bleManager.fireDoublePress()
                } label: {
                    Label("Double press", systemImage: "hand.tap")
                }

                Button {
                    if recording {
                        stopRecording()
                    } else {
                        startRecording()
                    }
                } label: {
                    Label(recording ? "Stop" : "Record", systemImage: recording ? "stop.circle" : "record.circle")
                }
            }
        }
        .padding()
        .frame(minWidth: 360)
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

                    while !dataLeft.isEmpty {
                        let block = dataLeft.prefix(160)
                        bleManager.writeAudio(block)
                        usleep(7_000)
                        dataLeft = dataLeft.dropFirst(160)
                    }
                }
            }
        }

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
        let channelCount = 1
        let channels = UnsafeBufferPointer(start: self.int16ChannelData, count: channelCount)
        let ch0Data = NSData(bytes: channels[0], length:Int(self.frameCapacity * self.format.streamDescription.pointee.mBytesPerFrame))
        return ch0Data as Data
    }
}

#Preview {
    ContentView()
}
