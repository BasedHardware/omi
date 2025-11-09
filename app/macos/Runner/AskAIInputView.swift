//
//  AskAIInputView.swift
//  Runner
//
//  Created by Omi on 2025-09-26.
//

import Cocoa
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

/// A view modifier for the main background of the control bar.
private struct MainBackgroundStyle: ViewModifier {
    let cornerRadius: CGFloat

    func body(content: Content) -> some View {
        content
            .background(
                ControlBarVisualEffectView(material: .menu, blendingMode: .withinWindow)
                    .opacity(0.7)
                    .cornerRadius(cornerRadius)
            )
    }
}

struct AskAIInputView: View {
    @Binding var userInput: String
    @State private var localInput: String = ""
    @State private var localScreenshotURL: URL?
    @FocusState private var isInputFocused: Bool

    var onSend: ((String, URL?) -> Void)?
    var onCancel: (() -> Void)?
    var onRemoveScreenshot: (() -> Void)?
    var width: CGFloat

    init(
        userInput: Binding<String>, screenshotURL: URL?, width: CGFloat,
        onSend: ((String, URL?) -> Void)? = nil, onCancel: (() -> Void)? = nil,
        onRemoveScreenshot: (() -> Void)? = nil
    ) {
        self._userInput = userInput
        self._localScreenshotURL = State(initialValue: screenshotURL)
        self.width = width
        self.onSend = onSend
        self.onCancel = onCancel
        self.onRemoveScreenshot = onRemoveScreenshot
    }

    var body: some View {
        HStack(spacing: 12) {
            if let url = localScreenshotURL, let nsImage = NSImage(contentsOf: url) {
                ZStack(alignment: .topTrailing) {
                    Button(action: {
                        NSWorkspace.shared.open(url)
                    }) {
                        Image(nsImage: nsImage)
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(width: 40, height: 40)
                            .cornerRadius(8)
                    }
                    .buttonStyle(PlainButtonStyle())

                    Button(action: {
                        localScreenshotURL = nil
                        onRemoveScreenshot?()
                    }) {
                        Image(systemName: "xmark")
                            .font(.system(size: 8, weight: .regular))
                            .foregroundColor(.white)
                            .frame(width: 16, height: 16)
                            .background(Color.black.opacity(0.6), in: Circle())
                            .overlay(
                                Circle()
                                    .strokeBorder(Color.white.opacity(0.3), lineWidth: 0.5)
                            )
                    }
                    .buttonStyle(PlainButtonStyle())
                    .offset(x: 6, y: -6)
                }
            }

            TextField("Ask a question...", text: $localInput)
                .textFieldStyle(PlainTextFieldStyle())
                .frame(height: 40)
                .padding(.horizontal, 12)
                .cornerRadius(20)
                .focused($isInputFocused)
                .onChange(of: localInput) { newValue in
                    userInput = newValue
                }
                .onAppear {
                    localInput = userInput
                    isInputFocused = true
                }

            Button(action: {
                onSend?(localInput, localScreenshotURL)
            }) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 24))
            }
            .disabled(localInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .buttonStyle(PlainButtonStyle())
            .keyboardShortcut(.defaultAction)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(width: width, height: 56)
        .modifier(MainBackgroundStyle(cornerRadius: 20))
    }
}
