import SwiftUI
import WatchKit

/// Main recording view for the Omi Watch app.
/// Refactored to use the native watchOS Liquid Glass APIs for surfaces and shared identities.
struct WatchRecorderView: View {
    @ObservedObject var viewModel: WatchAudioRecorderViewModel
    @Namespace private var glassNamespace
    @State private var isPressed = false
    @State private var rippleScale: CGFloat = 1.0
    @State private var rippleOpacity: Double = 0.0

    private enum GlassID {
        static let container = "watch.recorder.glass.container"
        static let button = "watch.recorder.glass.button"
        static let status = "watch.recorder.glass.status"
    }

    var body: some View {
        ZStack {
            background
            recorderSurface
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            if viewModel.isRecording {
                startRippleAnimation()
            }
        }
        .onChange(of: viewModel.isRecording) { _, isRecording in
            isRecording ? startRippleAnimation() : stopRippleAnimation()
        }
    }

    private var background: some View {
        Color.black
            .ignoresSafeArea()
    }

    @ViewBuilder
    private var recorderSurface: some View {
        let layout = VStack(spacing: 0) {
            Spacer()
            recordButton
            Spacer()
            statusLabel
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 20)

        if #available(watchOS 26.0, *) {
            layout.glassEffectID(GlassID.container, in: glassNamespace)
        } else {
            layout
        }
    }

    private var recordButton: some View {
        Button(action: toggleRecording) {
            ZStack {
                if viewModel.isRecording {
                    rippleLayer
                }

                glassButtonSurface

                Image("OmiLogo")
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: 40, height: 40)
                    .scaleEffect(isPressed ? 1.08 : 1.0)
                    .opacity(isPressed ? 0.8 : 1.0)
                    .animation(.spring(response: 0.3, dampingFraction: 0.6), value: isPressed)
            }
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var glassButtonSurface: some View {
        let circle = Circle()
            .fill(.white)
            .frame(width: 86, height: 86)
            .scaleEffect(isPressed ? 1.08 : 1.0)
            .animation(.spring(response: 0.3, dampingFraction: 0.6), value: isPressed)

        if #available(watchOS 26.0, *) {
            circle
                .glassEffect(.regular.interactive())
                .glassEffectID(GlassID.button, in: glassNamespace)
        } else {
            circle
                .shadow(color: .white.opacity(0.35), radius: 10)
                .shadow(color: .blue.opacity(0.2), radius: 16)
        }
    }

    @ViewBuilder
    private var rippleLayer: some View {
        ForEach(0..<3, id: \.self) { index in
            let ripple = Circle()
                .strokeBorder(lineWidth: 2)
                .frame(width: 120, height: 120)
                .foregroundStyle(.white.opacity(0.4))
                .scaleEffect(rippleScale)
                .opacity(rippleOpacity)
                .animation(
                    Animation.easeOut(duration: 1.5)
                        .repeatForever(autoreverses: false)
                        .delay(Double(index) * 0.3),
                    value: rippleScale
                )

            if #available(watchOS 26.0, *) {
                ripple.glassEffect(.clear)
            } else {
                ripple
            }
        }
    }

    private var statusLabel: some View {
        Text(viewModel.isRecording ? "Listening" : "Tap to Record")
            .font(.system(size: 16, weight: .semibold, design: .rounded))
            .foregroundStyle(.white)
            .padding(.horizontal, 24)
            .padding(.vertical, 10)
            .background(statusBackground)
            .accessibilityLabel(viewModel.isRecording ? "Listening" : "Tap to Record")
    }

    @ViewBuilder
    private var statusBackground: some View {
        let capsule = Capsule()
            .fill(Color.white.opacity(0.2))

        if #available(watchOS 26.0, *) {
            capsule
                .glassEffect(.regular)
                .glassEffectID(GlassID.status, in: glassNamespace)
        } else {
            capsule
                .overlay(
                    Capsule()
                        .stroke(Color.white.opacity(0.3), lineWidth: 1)
                )
        }
    }

    private func toggleRecording() {
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
    }

    private func startRippleAnimation() {
        rippleScale = 1.0
        rippleOpacity = 0.8
        withAnimation(.easeOut(duration: 1.5).repeatForever(autoreverses: false)) {
            rippleScale = 2.6
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
