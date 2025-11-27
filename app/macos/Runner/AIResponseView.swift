//
//  AIResponseView.swift
//  Runner
//
//  Created by Omi on 2025-09-26.
//

import Cocoa
import MarkdownUI
import SwiftUI

// MARK: - SwiftUI Views from FloatingControlBar

/// A view that wraps `NSVisualEffectView` for use in SwiftUI.
private struct ControlBarVisualEffectView: NSViewRepresentable {
    var material: NSVisualEffectView.Material
    var blendingMode: NSVisualEffectView.BlendingMode

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
    }
}

/// A spinning loading indicator.
private struct SpinnerView: View {
    @State private var isSpinning = false

    var body: some View {
        Image("app_launcher_icon")
            .resizable()
            .colorInvert()
            .rotationEffect(.degrees(isSpinning ? 360 : 0))
            .animation(.linear(duration: 1).repeatForever(autoreverses: false), value: isSpinning)
            .onAppear {
                withAnimation {
                    isSpinning = true
                }
            }
    }
}

/// A view modifier for the main background of the control bar.
private struct MainBackgroundStyle: ViewModifier {
    let cornerRadius: CGFloat

    func body(content: Content) -> some View {
        if #available(macOS 26.0, *) {
            content.glassEffect(in: RoundedRectangle(cornerRadius: cornerRadius))
        } else {
            content
                .background(
                    ControlBarVisualEffectView(material: .hudWindow, blendingMode: .behindWindow)
                )
                .cornerRadius(cornerRadius)
        }
    }
}

struct AIResponseView: View {
    @Binding var isLoading: Bool
    @Binding var responseText: String
    var userInput: String
    var screenshotURL: URL?
    var width: CGFloat
    var onClose: (() -> Void)?
    var onAskFollowUp: (() -> Void)?
    @State private var isCopied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                if isLoading {
                    SpinnerView()
                        .frame(width: 16, height: 16)
                        .background(Color.white)
                        .clipShape(Circle())
                    Text("thinking")
                        .font(.system(size: 14, weight: .regular))
                        .foregroundColor(.white.opacity(0.8))
                } else {
                    Text("AI response")
                        .font(.system(size: 14, weight: .regular))
                        .foregroundColor(.white.opacity(0.8))
                }
                Spacer()
                if !isLoading {
                    Button(action: { onAskFollowUp?() }) {
                        Text("Ask follow up")
                            .font(.system(size: 12, weight: .regular))
                            .foregroundColor(.primary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color.white.opacity(0.1))
                            .cornerRadius(8)
                    }
                    .buttonStyle(PlainButtonStyle())

                    Button(action: {
                        let pasteboard = NSPasteboard.general
                        pasteboard.clearContents()
                        pasteboard.setString(responseText, forType: .string)
                        withAnimation {
                            isCopied = true
                        }
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            withAnimation {
                                isCopied = false
                            }
                        }
                    }) {
                        if isCopied {
                            HStack(spacing: 4) {
                                Image(systemName: "checkmark")
                                Text("Copied")
                            }
                            .foregroundColor(.green)
                        } else {
                            Image(systemName: "square.on.square")
                                .foregroundColor(.secondary)
                        }
                    }
                    .buttonStyle(PlainButtonStyle())
                }

                Button(action: { onClose?() }) {
                    Image(systemName: "xmark")
                        .font(.system(size: 8, weight: .regular))
                        .foregroundColor(.secondary)
                        .frame(width: 16, height: 16)
                        .overlay(
                            Circle()
                                .strokeBorder(Color.white.opacity(0.3), lineWidth: 0.5)
                        )
                }
                .buttonStyle(PlainButtonStyle())
            }

            // User question bar
            HStack(spacing: 8) {
                if let url = screenshotURL, let nsImage = NSImage(contentsOf: url) {
                    Button(action: {
                        NSWorkspace.shared.open(url)
                    }) {
                        Image(nsImage: nsImage)
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(width: 24, height: 24)
                            .cornerRadius(4)
                    }
                    .buttonStyle(PlainButtonStyle())
                } else {
                    // As per the screenshot, but this is a placeholder.
                    // A better icon could be used if available in assets.
                    Image(systemName: "questionmark.circle.fill")
                        .foregroundColor(.red)
                }

                Text(userInput)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .foregroundColor(.white)

                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .strokeBorder(Color.white.opacity(0.2), lineWidth: 0.5)
            )

            if isLoading {
                Spacer()
                HStack {
                    Spacer()
                }
                Spacer()
            } else {
                ScrollView {
                    Markdown(responseText)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

            }
        }
        .padding()
        .frame(width: width, height: 300)
        .modifier(MainBackgroundStyle(cornerRadius: 20))
    }
}
