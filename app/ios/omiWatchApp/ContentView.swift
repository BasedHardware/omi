import SwiftUI

struct WatchRecorderView<Recorder: WatchRecorderControlling>: View {
    @ObservedObject var viewModel: Recorder
    @StateObject private var presentationController = RecordingPresentationController()
    @State private var isPressed = false
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Black background
                Color.black
                    .ignoresSafeArea()
                
                VStack(spacing: 0) {
                    Spacer()
                    
                    Button(action: {
                        withAnimation(.easeInOut(duration: 0.1)) {
                            isPressed = true
                        }
                        
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                            withAnimation(.easeInOut(duration: 0.1)) {
                                isPressed = false
                            }
                        }
                        
                        if viewModel.isRecording {
                            viewModel.stopRecording()
                        } else {
                            viewModel.startRecording()
                        }
                    }) {
                        ZStack {
                            if presentationController.phase.showsRecordingRipple {
                                RecordingRippleView()
                            }
                            
                            // Main button circle (white background)
                            Circle()
                                .fill(Color.white)
                                .frame(width: 80, height: 80)
                                .scaleEffect(isPressed ? 1.05 : 1.0)
                                .animation(.easeInOut(duration: 0.15), value: isPressed)
                            
                            Image("OmiLogo")
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: 40, height: 40)
                                .scaleEffect(isPressed ? 1.05 : 1.0)
                                .animation(.easeInOut(duration: 0.15), value: isPressed)
                        }
                    }
                    .buttonStyle(PlainButtonStyle())
                    .accessibilityLabel(
                        viewModel.isRecording
                            ? Text("watch.accessibility.stopRecording")
                            : Text("watch.accessibility.startRecording")
                    )
                    
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

                    Spacer()
                        .frame(height: 20)
                }
            }
        }
        .task(id: viewModel.recordingStartedAt) {
            await presentationController.update(
                isRecording: viewModel.isRecording,
                startedAt: viewModel.recordingStartedAt
            )
        }
    }
}

private struct RecordingRippleView: View {
    @State private var rippleScale: CGFloat = 1
    @State private var rippleOpacity: Double = 0.8

    var body: some View {
        ZStack {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .stroke(Color.white.opacity(0.3), lineWidth: 2)
                    .frame(width: 100, height: 100)
                    .scaleEffect(rippleScale)
                    .opacity(rippleOpacity)
                    .animation(
                        .easeOut(duration: 1.5)
                            .repeatForever(autoreverses: false)
                            .delay(Double(index) * 0.3),
                        value: rippleScale
                    )
            }
        }
        .onAppear {
            rippleScale = 2.5
            rippleOpacity = 0
        }
    }
}

#if canImport(WatchConnectivity)
    #Preview {
        WatchRecorderView(viewModel: WatchAudioRecorderViewModel())
    }
#endif
