import SwiftUI
import MarkdownUI

/// Onboarding step that demonstrates the floating control bar.
/// Shows an embedded mock of the bar, suggests "Who am I?", and displays
/// a personalized AI response to demonstrate the feature.
struct OnboardingFloatingBarDemoView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void

    @State private var demoState: DemoState = .initial
    @State private var inputText: String = ""
    @State private var responseText: String = ""
    @State private var isLoading = false
    @State private var showResponse = false
    @State private var querySubmitted = false
    @State private var pulseAnimation = false
    @FocusState private var isInputFocused: Bool

    private enum DemoState {
        case initial    // Showing the bar in collapsed state with suggestion
        case expanded   // Bar expanded, user can type or click suggestion
        case responding // AI is responding
        case done       // Response complete, show finish button
    }

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

                    Text("Press \(Text("⌥ Space").fontWeight(.medium)) anywhere to summon it. Ask anything\nand it responds using everything it knows about you.")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textSecondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }

                // Embedded floating bar mockup
                embeddedBarView
                    .frame(maxWidth: 480)
            }
            .padding(.horizontal, 40)

            Spacer()

            // Bottom button — shown after AI responds
            if demoState == .done {
                Button(action: onComplete) {
                    Text("Start using omi")
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
        .onAppear {
            // Auto-expand after a brief delay
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    demoState = .expanded
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                    isInputFocused = true
                }
            }
        }
    }

    // MARK: - Embedded Bar Mockup

    private var embeddedBarView: some View {
        VStack(spacing: 0) {
            switch demoState {
            case .initial:
                // Collapsed bar
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.white.opacity(0.5))
                    .frame(width: 28, height: 4)
                    .padding(.vertical, 16)

            case .expanded:
                // Input view
                VStack(spacing: 0) {
                    HStack {
                        Spacer()
                        HStack(spacing: 4) {
                            Text("esc")
                                .scaledFont(size: 11)
                                .foregroundColor(.secondary)
                                .frame(width: 30, height: 16)
                                .background(Color.white.opacity(0.1))
                                .cornerRadius(4)
                            Text("to close")
                                .scaledFont(size: 11)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding(.top, 8)
                    .padding(.trailing, 16)

                    HStack(spacing: 6) {
                        ZStack(alignment: .topLeading) {
                            if inputText.isEmpty {
                                Text("Ask a question...")
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

                    // Suggestion chip
                    if !querySubmitted {
                        HStack {
                            Button(action: {
                                inputText = "Who am I?"
                                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                                    submitQuery()
                                }
                            }) {
                                HStack(spacing: 6) {
                                    Image(systemName: "sparkles")
                                        .font(.system(size: 11))
                                    Text("Try: \"Who am I?\"")
                                        .font(.system(size: 12, weight: .medium))
                                }
                                .foregroundColor(OmiColors.purplePrimary)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 7)
                                .background(OmiColors.purplePrimary.opacity(0.1))
                                .cornerRadius(16)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 16)
                                        .stroke(OmiColors.purplePrimary.opacity(0.3), lineWidth: 1)
                                )
                            }
                            .buttonStyle(.plain)

                            Spacer()
                        }
                        .padding(.horizontal, 16)
                        .padding(.bottom, 12)
                    }
                }

            case .responding, .done:
                // Response view
                VStack(alignment: .leading, spacing: 12) {
                    // Header
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
                        Text(querySubmitted ? (inputText.isEmpty ? "Who am I?" : inputText) : "")
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

    // MARK: - Query Submission

    private func submitQuery() {
        let query = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return }
        querySubmitted = true

        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            demoState = .responding
            isLoading = true
        }

        Task {
            await sendQuery(query)
        }
    }

    private func sendQuery(_ query: String) async {
        // Use ChatProvider to send the query through the ACP bridge
        // This gives a real AI response with full user context
        let systemPrompt = """
        You are omi, a personal AI that knows the user well from analyzing their screen activity. \
        The user is trying the floating bar for the first time during onboarding. \
        Give a warm, personalized response. If they ask "Who am I?", respond with what you know \
        about them from the onboarding conversation — their name, interests, what they've been working on. \
        Keep it brief (2-4 sentences) and friendly. If you don't know much yet, be honest but encouraging.
        """

        // Stream the response via ChatProvider
        await chatProvider.sendMessage(query, systemPromptPrefix: systemPrompt)

        // Monitor ChatProvider messages for the response
        await observeResponse()
    }

    @MainActor
    private func observeResponse() async {
        // Poll for the AI response from ChatProvider
        var attempts = 0
        while attempts < 60 { // Max 30 seconds
            try? await Task.sleep(nanoseconds: 500_000_000) // 0.5s
            attempts += 1

            // Check if the last message is from AI and is no longer streaming
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
                    // Response complete
                    withAnimation(.easeInOut(duration: 0.3)) {
                        isLoading = false
                        demoState = .done
                    }
                    return
                }
            }
        }

        // Timeout — show what we have
        await MainActor.run {
            withAnimation(.easeInOut(duration: 0.3)) {
                isLoading = false
                demoState = .done
            }
        }
    }
}
