import SwiftUI
import WatchKit

/// Main recording view for the Omi Watch app
/// Enhanced with watchOS 26 Liquid Glass effects for modern, fluid UI
struct WatchRecorderView: View {
    @ObservedObject var viewModel: WatchAudioRecorderViewModel
    @State private var isPressed = false
    @State private var pulseScale: CGFloat = 1.0
    @State private var rippleScale: CGFloat = 1.0
    @State private var rippleOpacity: Double = 0.0
    @State private var glassIntensity: Double = 0.0
    @Environment(\.isLuminanceReduced) private var isLuminanceReduced
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Background with Liquid Glass material
                Color.black
                    .ignoresSafeArea()
                    .overlay(
                        // Subtle gradient for depth
                        LinearGradient(
                            gradient: Gradient(colors: [
                                Color.white.opacity(isLuminanceReduced ? 0.02 : 0.05),
                                Color.clear
                            ]),
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )

                VStack(spacing: 0) {
                    Spacer()

                    // Recording control button with Liquid Glass effects
                    Button(action: {
                        // Haptic feedback for watchOS 26
                        WKInterfaceDevice.current().play(.click)

                        withAnimation(.spring(response: 0.3, dampingFraction: 0.6)) {
                            isPressed = true
                            glassIntensity = 1.0
                        }

                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.6)) {
                                isPressed = false
                                glassIntensity = 0.0
                            }
                        }

                        if viewModel.isRecording {
                            viewModel.stopRecording()
                        } else {
                            viewModel.startRecording()
                        }
                    }) {
                        ZStack {
                            // Pulsating ripple effect when recording with Liquid Glass
                            if viewModel.isRecording {
                                ForEach(0..<3, id: \.self) { index in
                                    Circle()
                                        .stroke(
                                            LinearGradient(
                                                gradient: Gradient(colors: [
                                                    Color.white.opacity(0.4),
                                                    Color.blue.opacity(0.2)
                                                ]),
                                                startPoint: .topLeading,
                                                endPoint: .bottomTrailing
                                            ),
                                            lineWidth: 2
                                        )
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

                            // Main button circle with Liquid Glass effect
                            Circle()
                                .fill(
                                    LinearGradient(
                                        gradient: Gradient(colors: [
                                            Color.white,
                                            Color.white.opacity(0.9)
                                        ]),
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    )
                                )
                                .frame(width: 80, height: 80)
                                .overlay(
                                    Circle()
                                        .stroke(Color.white.opacity(0.5), lineWidth: 1)
                                        .blur(radius: isPressed ? 2 : 0)
                                )
                                .shadow(color: Color.white.opacity(isPressed ? 0.4 : 0.2), radius: isPressed ? 12 : 8)
                                .scaleEffect(isPressed ? 1.08 : 1.0)
                                .animation(.spring(response: 0.3, dampingFraction: 0.6), value: isPressed)

                            // Logo with enhanced visual feedback
                            Image("OmiLogo")
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: 40, height: 40)
                                .scaleEffect(isPressed ? 1.08 : 1.0)
                                .opacity(isPressed ? 0.8 : 1.0)
                                .animation(.spring(response: 0.3, dampingFraction: 0.6), value: isPressed)
                        }
                    }
                    .buttonStyle(PlainButtonStyle())

                    Spacer()

                    // Status text with Liquid Glass styling
                    Text(viewModel.isRecording ? "Listening" : "Tap to Record")
                        .font(.system(size: 16, weight: .medium, design: .rounded))
                        .foregroundStyle(
                            LinearGradient(
                                gradient: Gradient(colors: [
                                    Color.white,
                                    Color.white.opacity(0.8)
                                ]),
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        .padding(.horizontal, 20)
                        .padding(.vertical, 8)
                        .background(
                            Capsule()
                                .fill(Color.white.opacity(0.1))
                                .overlay(
                                    Capsule()
                                        .stroke(Color.white.opacity(0.2), lineWidth: 0.5)
                                )
                        )
                        .padding(.bottom, 20)
                        .shadow(color: Color.black.opacity(0.3), radius: 4, y: 2)
                }
            }
        }
        .onAppear {
            if viewModel.isRecording {
                startRippleAnimation()
            }
            // Animate glass effect on appear
            withAnimation(.easeIn(duration: 0.5)) {
                glassIntensity = 0.5
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
