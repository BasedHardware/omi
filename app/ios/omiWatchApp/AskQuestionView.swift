// Created by Barrett Jacobsen

import SwiftUI
import AVFoundation
import WatchConnectivity

struct AskQuestionView: View {
    @StateObject private var viewModel = AskQuestionViewModel()

    var body: some View {
        VStack(spacing: 12) {
            Spacer()

            Button(action: {
                if viewModel.isRecording {
                    viewModel.stopAndSend()
                } else {
                    viewModel.startRecording()
                }
            }) {
                ZStack {
                    Circle()
                        .fill(viewModel.isRecording ? Color.red : Color.white)
                        .frame(width: 70, height: 70)

                    Image(systemName: viewModel.isRecording ? "stop.fill" : "bubble.left.fill")
                        .font(.title2)
                        .foregroundColor(viewModel.isRecording ? .white : .black)
                }
            }
            .buttonStyle(PlainButtonStyle())

            Spacer()

            Group {
                switch viewModel.state {
                case .idle:
                    Text("Tap to ask a question")
                case .recording:
                    Text("Listening...")
                case .sending:
                    VStack(spacing: 4) {
                        ProgressView()
                        Text("Asking Omi...")
                    }
                case .answered:
                    Text("Answer sent as notification")
                case .error(let message):
                    Text(message)
                        .foregroundColor(.red)
                }
            }
            .font(.system(size: 14, weight: .medium))
            .foregroundColor(.white)
            .multilineTextAlignment(.center)
            .padding(.bottom, 16)
        }
        .background(Color.black.ignoresSafeArea())
    }
}

enum AskState: Equatable {
    case idle
    case recording
    case sending
    case answered
    case error(String)
}

@MainActor
class AskQuestionViewModel: NSObject, ObservableObject {
    @Published var state: AskState = .idle
    @Published var isRecording = false

    private var audioEngine: AVAudioEngine?
    private var audioConverter: AVAudioConverter?
    private var recordedData = Data()

    func startRecording() {
        guard state != .recording && state != .sending else { return }

        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.playAndRecord, mode: .default, options: [.mixWithOthers])
            try audioSession.setActive(true)

            audioEngine = AVAudioEngine()
            guard let inputNode = audioEngine?.inputNode else { return }
            let inputFormat = inputNode.inputFormat(forBus: 0)

            guard let targetFormat = AVAudioFormat(standardFormatWithSampleRate: 16000.0, channels: 1) else { return }
            audioConverter = AVAudioConverter(from: inputFormat, to: targetFormat)

            recordedData = Data()

            inputNode.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { [weak self] buffer, _ in
                self?.processBuffer(buffer)
            }

            try audioEngine?.start()
            isRecording = true
            state = .recording
        } catch {
            state = .error("Mic error")
        }
    }

    func stopAndSend() {
        audioEngine?.inputNode.removeTap(onBus: 0)
        audioEngine?.stop()
        audioEngine = nil
        audioConverter = nil
        isRecording = false

        guard !recordedData.isEmpty else {
            state = .error("No audio captured")
            return
        }

        state = .sending
        sendQuestionAudio()
    }

    private func processBuffer(_ buffer: AVAudioPCMBuffer) {
        guard let converter = audioConverter else { return }
        let frameCount = AVAudioFrameCount(ceil(Double(buffer.frameLength) * 16000.0 / buffer.format.sampleRate))
        guard let targetFormat = AVAudioFormat(standardFormatWithSampleRate: 16000.0, channels: 1),
              let outputBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: frameCount) else { return }

        var error: NSError?
        converter.convert(to: outputBuffer, error: &error) { _, outStatus in
            outStatus.pointee = .haveData
            return buffer
        }

        guard error == nil, let channelData = outputBuffer.floatChannelData?[0] else { return }

        var pcmData = [Int16]()
        for i in 0..<Int(outputBuffer.frameLength) {
            let sample = channelData[i]
            pcmData.append(Int16(max(-32768, min(32767, sample * 32767))))
        }

        let byteData = pcmData.withUnsafeBufferPointer { Data(buffer: $0) }
        DispatchQueue.main.async {
            self.recordedData.append(byteData)
        }
    }

    private func sendQuestionAudio() {
        let session = WCSession.default
        let message: [String: Any] = [
            "method": "askQuestion",
            "audioData": recordedData,
            "sampleRate": 16000.0
        ]

        if session.isReachable {
            session.sendMessage(message, replyHandler: { [weak self] _ in
                DispatchQueue.main.async {
                    self?.state = .answered
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                        self?.state = .idle
                    }
                }
            }, errorHandler: { [weak self] _ in
                DispatchQueue.main.async {
                    self?.state = .error("Send failed")
                }
            })
        } else {
            session.transferUserInfo(message)
            state = .answered
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
                self?.state = .idle
            }
        }

        recordedData = Data()
    }
}

#Preview {
    AskQuestionView()
}
