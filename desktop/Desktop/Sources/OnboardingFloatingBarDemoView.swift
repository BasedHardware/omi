import SwiftUI
import AppKit
import MarkdownUI

/// Onboarding step: prompts user to press ⌘ Enter, then reveals an embedded
/// floating bar inside the onboarding where they can ask a question.
struct OnboardingFloatingBarDemoView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void

    @State private var showBar = false
    @State private var inputText = ""
    @State private var responseText = ""
    @State private var isLoading = false
    @State private var showResponse = false
    @State private var querySubmitted = false
    @State private var doneResponding = false
    @State private var pulseAnimation = false
    @State private var keyMonitor: Any?
    @FocusState private var isInputFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Ask omi anything")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: onSkip) {
                    Text("Skip")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 16)

            Divider()
                .background(OmiColors.backgroundTertiary)

            Spacer()

            // Content
            VStack(spacing: 28) {
                // Icon with glow
                ZStack {
                    Circle()
                        .fill(OmiColors.purplePrimary.opacity(0.12))
                        .frame(width: 96, height: 96)
                        .blur(radius: 18)
                        .scaleEffect(pulseAnimation ? 1.15 : 1.0)
                        .animation(.easeInOut(duration: 2).repeatForever(autoreverses: true), value: pulseAnimation)

                    Image(systemName: "rectangle.and.text.magnifyingglass")
                        .font(.system(size: 40))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [OmiColors.purplePrimary, OmiColors.purpleSecondary],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                }
                .onAppear { pulseAnimation = true }

                VStack(spacing: 10) {
                    Text("The Floating Bar")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundColor(OmiColors.textPrimary)

                    Text("Ask anything and it responds using\neverything it knows about you.")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textSecondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }

                if showBar {
                    // Embedded floating bar
                    embeddedBarView
                        .frame(maxWidth: 480)
                        .transition(.move(edge: .bottom).combined(with: .opacity).combined(with: .scale(scale: 0.95)))
                } else {
                    // Keyboard shortcut hint
                    VStack(spacing: 12) {
                        Text("Try it now")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)

                        HStack(spacing: 8) {
                            keyCap("⌘")
                            keyCap("Enter")
                        }
                    }
                    .padding(.top, 4)
                    .transition(.opacity)
                }
            }
            .padding(.horizontal, 40)

            Spacer()

            // Bottom button
            if doneResponding {
                Button(action: onComplete) {
                    Text("Continue")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(maxWidth: 280)
                        .padding(.vertical, 12)
                        .background(OmiColors.purplePrimary)
                        .cornerRadius(12)
                }
                .buttonStyle(.plain)
                .padding(.bottom, 32)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OmiColors.backgroundPrimary)
        .onAppear { installKeyMonitor() }
        .onDisappear { removeKeyMonitor() }
    }

    // MARK: - Key Monitor

    private func installKeyMonitor() {
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            let mods = event.modifierFlags.intersection(NSEvent.ModifierFlags.deviceIndependentFlagsMask)
            if mods == .command && event.keyCode == 36 { // 36 = Return
                if !showBar {
                    withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                        showBar = true
                    }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                        isInputFocused = true
                    }
                    return nil
                }
            }
            return event
        }
    }

    private func removeKeyMonitor() {
        if let monitor = keyMonitor {
            NSEvent.removeMonitor(monitor)
            keyMonitor = nil
        }
    }

    // MARK: - Embedded Bar

    private var embeddedBarView: some View {
        VStack(spacing: 0) {
            if !querySubmitted {
                // Input view
                HStack(spacing: 6) {
                    ZStack(alignment: .topLeading) {
                        if inputText.isEmpty {
                            Text("Try asking: \"Who am I?\"")
                                .scaledFont(size: 13)
                                .foregroundColor(.secondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 8)
                        }

                        TextField("", text: $inputText)
                            .textFieldStyle(.plain)
                            .scaledFont(size: 13)
                            .foregroundColor(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 8)
                            .focused($isInputFocused)
                            .onSubmit {
                                submitQuery()
                            }
                    }
                    .padding(.horizontal, 4)
                    .frame(height: 40)

                    Button(action: submitQuery) {
                        Image(systemName: "arrow.up.circle.fill")
                            .scaledFont(size: 24)
                            .foregroundColor(
                                inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                    ? .secondary : .white
                            )
                    }
                    .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
            } else {
                // Response view
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 12) {
                        if isLoading {
                            ProgressView()
                                .scaleEffect(0.6)
                                .frame(width: 16, height: 16)
                            Text("thinking")
                                .scaledFont(size: 14)
                                .foregroundColor(.secondary)
                        } else {
                            Text("omi says")
                                .scaledFont(size: 14)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                    }

                    // Question
                    HStack(alignment: .top, spacing: 8) {
                        Text(inputText.isEmpty ? "Who am I?" : inputText)
                            .scaledFont(size: 13)
                            .foregroundColor(.white)
                            .lineLimit(1)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.white.opacity(0.1))
                    .cornerRadius(8)

                    // Response
                    if showResponse && !responseText.isEmpty {
                        ScrollView {
                            SelectableMarkdown(text: responseText, sender: .ai)
                                .textSelection(.enabled)
                                .environment(\.colorScheme, .dark)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(maxHeight: 200)
                        .padding(.horizontal, 4)
                    } else if isLoading {
                        TypingIndicator()
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 4)
                    }
                }
                .padding(16)
            }
        }
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 20)
                .fill(.ultraThinMaterial)
                .environment(\.colorScheme, .dark)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .strokeBorder(Color.white.opacity(0.15), lineWidth: 1)
        )
    }

    // MARK: - Query

    private func submitQuery() {
        let query = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return }
        querySubmitted = true
        isLoading = true

        Task {
            let systemPrompt = """
            You are omi, a personal AI that knows the user well from analyzing their screen activity. \
            The user is trying the floating bar for the first time during onboarding. \
            Give a warm, personalized response. If they ask "Who am I?", respond with what you know \
            about them from the onboarding conversation — their name, interests, what they've been working on. \
            Keep it brief (2-4 sentences) and friendly. If you don't know much yet, be honest but encouraging.
            """

            await chatProvider.sendMessage(query, systemPromptPrefix: systemPrompt)
            await observeResponse()
        }
    }

    @MainActor
    private func observeResponse() async {
        var attempts = 0
        while attempts < 60 {
            try? await Task.sleep(nanoseconds: 500_000_000)
            attempts += 1

            if let lastMessage = chatProvider.messages.last,
               lastMessage.sender == .ai {
                let text = lastMessage.text.trimmingCharacters(in: .whitespacesAndNewlines)
                if !text.isEmpty {
                    responseText = text
                    if !showResponse {
                        withAnimation(.easeIn(duration: 0.2)) {
                            showResponse = true
                        }
                    }
                }

                if !lastMessage.isStreaming && !chatProvider.isSending {
                    withAnimation(.easeInOut(duration: 0.3)) {
                        isLoading = false
                        doneResponding = true
                    }
                    return
                }
            }
        }

        withAnimation(.easeInOut(duration: 0.3)) {
            isLoading = false
            doneResponding = true
        }
    }

    // MARK: - Key Cap

    private func keyCap(_ key: String) -> some View {
        Text(key)
            .font(.system(size: 15, weight: .medium, design: .rounded))
            .foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundTertiary)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
                    )
                    .shadow(color: .black.opacity(0.2), radius: 1, x: 0, y: 1)
            )
    }
}
