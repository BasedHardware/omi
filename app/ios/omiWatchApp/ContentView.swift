import SwiftUI
import WatchKit

/// Main recording view for the Omi Watch app
/// Uses native watchOS 26 Liquid Glass effects via framework materials
struct WatchRecorderView: View {
    @ObservedObject var viewModel: WatchAudioRecorderViewModel
    @State private var isPressed = false
    @State private var pulseScale: CGFloat = 1.0
    @State private var rippleScale: CGFloat = 1.0
    @State private var rippleOpacity: Double = 0.0
    
    var body: some View {
        ZStack {
            // Native black background - framework handles the rest
            Color.black
                .ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Recording control button with native Liquid Glass
                Button(action: {
                    // Haptic feedback for watchOS 26
                    WKInterfaceDevice.current().play(.click)

                    withAnimation(.spring(response: 0.3, dampingFraction: 0.6)) {
                        isPressed = true
                    }

                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.6)) {
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
                        // Pulsating ripple effect when recording
                        if viewModel.isRecording {
                            ForEach(0..<3, id: \.self) { index in
                                Circle()
                                    .stroke(Color.white.opacity(0.3), lineWidth: 2)
                                    .frame(width: 100, height: 100)
                                    .scaleEffect(rippleScale)
                                    .opacity(rippleOpacity)
                                    .animation(
                                        Animation.easeOut(duration: 1.5)
                                            .repeatForever(autoreverses: false)
                                            .delay(Double(index) * 0.3),
                                        value: rippleScale
                                    )
                                    .onAppear {
                                        rippleScale = 2.5
                                        rippleOpacity = 0.8
                                    }
                            }
                        }

                        // Main button with native Liquid Glass material
                        Circle()
                            .fill(.white)
                            .frame(width: 80, height: 80)
                            .scaleEffect(isPressed ? 1.08 : 1.0)
                            .shadow(color: .black.opacity(0.3), radius: 8, y: 4)

                        // Logo with visual feedback
                        Image("OmiLogo")
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 40, height: 40)
                            .scaleEffect(isPressed ? 1.08 : 1.0)
                            .opacity(isPressed ? 0.8 : 1.0)
                    }
                    .animation(.spring(response: 0.3, dampingFraction: 0.6), value: isPressed)
                }
                .buttonStyle(.plain)

                Spacer()

                // Status text with native material background
                Text(viewModel.isRecording ? "Listening" : "Tap to Record")
                    .font(.system(size: 16, weight: .medium, design: .rounded))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 8)
                    .background(
                        Capsule()
                            .fill(.ultraThinMaterial)
                    )
                    .padding(.bottom, 20)
            }
        }
        .onAppear {
            if viewModel.isRecording {
                startRippleAnimation()
            }
        }
        .onChange(of: viewModel.isRecording) { isRecording in
            if isRecording {
                startRippleAnimation()
            } else {
                stopRippleAnimation()
            }
        }
    }
    
    private func startRippleAnimation() {
        rippleScale = 1.0
        rippleOpacity = 0.8
        withAnimation(.easeOut(duration: 1.5).repeatForever(autoreverses: false)) {
            rippleScale = 2.5
            rippleOpacity = 0.0
        }
    }
    
    private func stopRippleAnimation() {
        rippleScale = 1.0
        rippleOpacity = 0.0
    }
}

#Preview {
    WatchRecorderView(viewModel: WatchAudioRecorderViewModel())
}
