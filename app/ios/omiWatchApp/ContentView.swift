import SwiftUI

struct WatchRecorderView: View {
    @ObservedObject var viewModel: WatchAudioRecorderViewModel
    @State private var isPressed = false
    @State private var pulseScale: CGFloat = 1.0
    @State private var rippleScale: CGFloat = 1.0
    @State private var rippleOpacity: Double = 0.0
    
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
                    
                    Spacer()
                    
                    Text(viewModel.isRecording ? "Listening" : "Tap to Record")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.white)
                        .padding(.bottom, 20)
                }
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
