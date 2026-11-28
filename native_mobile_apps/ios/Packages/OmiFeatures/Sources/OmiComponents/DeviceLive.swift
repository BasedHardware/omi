import OmiDesign
import OmiService
import SwiftUI

/// The Omi itself: a calm ring while searching, a blue glow that breathes while it streams.
public struct DeviceHero: View {
    public enum State { case searching, connecting, streaming }
    let state: State

    public init(state: State) {
        self.state = state
    }
    @SwiftUI.State private var pulse = false

    public static let blue = Color(red: 0.25, green: 0.55, blue: 1.0)

    public var body: some View {
        ZStack {
            Circle()
                .stroke(state == .streaming ? Self.blue.opacity(0.5) : DS.Palette.ink.opacity(0.15), lineWidth: 2)
                .frame(width: 200, height: 200)
                .scaleEffect(pulse ? 1.12 : 0.92)
                .opacity(pulse ? 0 : 1)
            if state == .streaming {
                Circle()
                    .fill(Self.blue.opacity(0.35))
                    .frame(width: 150, height: 150)
                    .blur(radius: 30)
                    .scaleEffect(pulse ? 1.15 : 0.85)
            }
            OmiMedia.device
                .resizable()
                .scaledToFit()
                .frame(width: 128, height: 128)
                .overlay {
                    if state == .streaming {
                        Circle().fill(Self.blue).frame(width: 14, height: 14).blur(radius: 3)
                            .opacity(pulse ? 1 : 0.55)
                    }
                }
        }
        .frame(height: 210)
        .animation(.easeInOut(duration: state == .streaming ? 1.4 : 2).repeatForever(autoreverses: state == .streaming), value: pulse)
        .onAppear { pulse = true }
        .accessibilityHidden(true)
    }
}
