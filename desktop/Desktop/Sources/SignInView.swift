import SwiftUI

struct SignInView: View {
    @ObservedObject var authState: AuthState

    var body: some View {
        ZStack {
            // Full background
            OmiColors.backgroundPrimary
                .ignoresSafeArea()

            // Centered sign in card
            VStack(spacing: 32) {
                Spacer()

                // Logo/Title
                VStack(spacing: 16) {
                    // Omi logo
                    if let logoImage = NSImage(contentsOf: Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png")!) {
                        Image(nsImage: logoImage)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 64, height: 64)
                    }

                    Text("omi")
                        .scaledFont(size: 48, weight: .bold)
                        .foregroundColor(OmiColors.textPrimary)

                    Text("Sign in to continue")
                        .font(.title3)
                        .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                // Sign in buttons
                VStack(spacing: 12) {
                    // Sign in with Apple
                    Button(action: {
                        Task {
                            do {
                                try await AuthService.shared.signInWithApple()
                            } catch {
                                let errorMsg = "Error: \(error.localizedDescription)"
                                authState.error = errorMsg
                                NSLog("OMI Sign in error: %@", errorMsg)
                            }
                        }
                    }) {
                        HStack(spacing: 8) {
                            Image(systemName: "applelogo")
                                .scaledFont(size: 18)
                            Text("Sign in with Apple")
                                .scaledFont(size: 17, weight: .medium)
                        }
                        .foregroundColor(.black)
                        .frame(maxWidth: .infinity)
                        .frame(height: 50)
                        .background(Color.white)
                        .cornerRadius(10)
                    }
                    .buttonStyle(.plain)
                    .disabled(authState.isLoading)

                    // Sign in with Google
                    Button(action: {
                        Task {
                            do {
                                try await AuthService.shared.signInWithGoogle()
                            } catch {
                                let errorMsg = "Error: \(error.localizedDescription)"
                                authState.error = errorMsg
                                NSLog("OMI Sign in error: %@", errorMsg)
                            }
                        }
                    }) {
                        HStack(spacing: 8) {
                            GoogleLogo()
                                .frame(width: 18, height: 18)
                            Text("Sign in with Google")
                                .scaledFont(size: 17, weight: .medium)
                        }
                        .foregroundColor(.black)
                        .frame(maxWidth: .infinity)
                        .frame(height: 50)
                        .background(Color.white)
                        .cornerRadius(10)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(authState.isLoading)

                    // Loading overlay for both buttons
                    if authState.isLoading {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: OmiColors.textPrimary))
                            .padding(.top, 8)
                    }

                    if let error = authState.error {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(OmiColors.error)
                            .multilineTextAlignment(.center)
                            .padding(.top, 4)
                    }
                }
                .frame(width: 320)

                Spacer()
                    .frame(height: 60)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}

// MARK: - Google Logo

/// Standard multicolor Google "G" logo
struct GoogleLogo: View {
    var body: some View {
        GeometryReader { geo in
            let size = min(geo.size.width, geo.size.height)
            let center = CGPoint(x: size / 2, y: size / 2)
            let outer = size / 2
            let inner = size * 0.28
            let barHeight = size * 0.16

            ZStack {
                // Blue (right arc: -45° to 90° clockwise, i.e. 1:30 to 4:30)
                ArcWedge(center: center, outerRadius: outer, innerRadius: inner,
                         startAngle: .degrees(-45), endAngle: .degrees(90))
                    .fill(Color(red: 66/255, green: 133/255, blue: 244/255))

                // Green (bottom-right arc: 90° to 180°)
                ArcWedge(center: center, outerRadius: outer, innerRadius: inner,
                         startAngle: .degrees(90), endAngle: .degrees(180))
                    .fill(Color(red: 52/255, green: 168/255, blue: 83/255))

                // Yellow (bottom-left arc: 180° to 270°)
                ArcWedge(center: center, outerRadius: outer, innerRadius: inner,
                         startAngle: .degrees(180), endAngle: .degrees(270))
                    .fill(Color(red: 251/255, green: 188/255, blue: 5/255))

                // Red (top-left arc: 270° to 360° - 45° = 315°)
                ArcWedge(center: center, outerRadius: outer, innerRadius: inner,
                         startAngle: .degrees(270), endAngle: .degrees(315))
                    .fill(Color(red: 234/255, green: 67/255, blue: 53/255))

                // Horizontal bar (blue, extends from center to right edge)
                Rectangle()
                    .fill(Color(red: 66/255, green: 133/255, blue: 244/255))
                    .frame(width: size * 0.52, height: barHeight)
                    .offset(x: size * 0.05)
            }
        }
        .aspectRatio(1, contentMode: .fit)
    }
}

/// Arc wedge shape for the Google "G" segments
struct ArcWedge: Shape {
    let center: CGPoint
    let outerRadius: CGFloat
    let innerRadius: CGFloat
    let startAngle: Angle
    let endAngle: Angle

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.addArc(center: center, radius: outerRadius,
                     startAngle: startAngle, endAngle: endAngle, clockwise: false)
        path.addArc(center: center, radius: innerRadius,
                     startAngle: endAngle, endAngle: startAngle, clockwise: true)
        path.closeSubpath()
        return path
    }
}

#Preview {
    SignInView(authState: AuthState.shared)
}
