import SwiftUI

struct WatchRecorderView<Recorder: WatchRecorderControlling>: View {
    @ObservedObject var viewModel: Recorder
    @StateObject private var presentationController = RecordingPresentationController()
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                let hasRecoveryStatus = viewModel.pendingRecoverySegments > 0 || viewModel.recoveryError != nil
                // Black background
                Color.black
                    .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 0) {
                        Spacer()

                        if viewModel.isRecording {
                            Button(action: viewModel.stopRecording) {
                                Group {
                                    if dynamicTypeSize.isAccessibilitySize {
                                        Text("watch.accessibility.stopRecording")
                                    } else {
                                        Label("watch.accessibility.stopRecording", systemImage: "stop.fill")
                                    }
                                }
                                .font(.body.weight(.semibold))
                                .frame(maxWidth: .infinity, minHeight: 32)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.red)
                            .accessibilityIdentifier("watch_recording_stop")
                        } else {
                            Button(action: viewModel.startRecording) {
                                ZStack {
                                    Circle()
                                        .fill(Color.white)
                                        .frame(width: hasRecoveryStatus ? 44 : 80, height: hasRecoveryStatus ? 44 : 80)
                                    Image("OmiLogo")
                                        .resizable()
                                        .aspectRatio(contentMode: .fit)
                                        .frame(width: hasRecoveryStatus ? 24 : 40, height: hasRecoveryStatus ? 24 : 40)
                                }
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("watch_recording_start")
                            .accessibilityLabel(Text("watch.accessibility.startRecording"))
                        }

                        Spacer()

                        Group {
                            if viewModel.isRecording, let startedAt = viewModel.recordingStartedAt {
                                if presentationController.phase.showsRecordingRipple {
                                    Text("Listening")
                                        .font(.system(size: 16, weight: .medium))
                                        .accessibilityLabel(Text("watch.accessibility.recordingInProgress"))
                                } else {
                                    Text(startedAt, style: .timer)
                                        .font(.system(size: 22, weight: .semibold, design: .rounded))
                                        .monospacedDigit()
                                        .accessibilityLabel(Text("watch.accessibility.elapsedRecordingTime"))
                                        .accessibilityValue(Text(startedAt, style: .timer))
                                }
                            } else {
                                Text("Tap to Record")
                                    .font(.system(size: 16, weight: .medium))
                            }
                        }
                        .foregroundColor(.white)

                        if let error = viewModel.recoveryError {
                            Text(error).font(.footnote).multilineTextAlignment(.center)
                        }
                        if viewModel.pendingRecoverySegments > 0 {
                            if viewModel.recoveryError == nil {
                                Text("watch.recovery.pending").font(.footnote).multilineTextAlignment(.center)
                            }
                            Button("watch.recovery.retry") { viewModel.retryRecoveryTransfers() }
                                .buttonStyle(.bordered)
                                .font(.footnote)
                        }

                        Spacer()
                            .frame(height: hasRecoveryStatus ? 0 : 20)
                    }
                    .padding(.horizontal, 12)
                    .frame(minHeight: geometry.size.height)
                }
            }
        }
        .onAppear { viewModel.retryRecoveryTransfers() }
        .task(id: viewModel.recordingStartedAt) {
            await presentationController.update(
                isRecording: viewModel.isRecording,
                startedAt: viewModel.recordingStartedAt
            )
        }
    }
}

#if canImport(WatchConnectivity)
    #Preview {
        WatchRecorderView(viewModel: WatchAudioRecorderViewModel())
    }
#endif
