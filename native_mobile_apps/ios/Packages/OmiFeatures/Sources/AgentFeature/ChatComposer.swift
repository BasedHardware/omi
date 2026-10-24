import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// The chat's composer, as in Messages: "+" (photo, camera, file) on the left, the rounded field
/// with the send arrow inside it, and one mic on the right. The arrow only shows once something is
/// typed (and as stop while Omi answers); the field keeps room for it, so it never jumps. The mic:
/// tap to dictate into the field (tap again to stop), or hold to talk and let go to send. The chat
/// places it with `.safeAreaInset(edge: .bottom)`, so it sits right on the keyboard.
struct ChatComposer: View {
    @Environment(ChatStore.self) private var chat
    @Binding var draft: String
    var focused: FocusState<Bool>.Binding
    let isDictating: Bool
    let canDictate: Bool
    let canSend: Bool
    /// The microphone level while dictating (the stop circle breathes with it).
    let level: Float
    /// Listening started by holding the mic: letting go sends.
    let sendsAfterDictation: Bool
    let onSend: () -> Void
    /// `thenSend`: held (talk to Omi) rather than tapped (dictate into the field).
    let onDictate: (_ thenSend: Bool) -> Void
    let onStopDictation: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            if let target = chat.replyingTo { replyLine(target) }
            if let context = chat.context { contextLine(context) }
            if !chat.attachments.isEmpty { AttachmentStrip() }
            HStack(alignment: .bottom, spacing: DS.Spacing.sm) {
                AttachmentButton()
                field
                if canDictate || isDictating {
                    ComposerMic(
                        isDictating: isDictating, level: level, sendsAfterDictation: sendsAfterDictation,
                        isEnabled: !chat.isStreaming || isDictating, onDictate: onDictate, onStop: onStopDictation
                    )
                }
            }
        }
        .padding(.horizontal, DS.Spacing.lg)
        .padding(.top, DS.Spacing.sm)
        .padding(.bottom, DS.Spacing.sm)
        .animation(DS.Motion.snappy, value: chat.replyingTo?.id)
    }

    private static let fieldHeight = DS.Size.composer
    private static let sendSize: CGFloat = 36

    private var field: some View {
        TextField(isDictating ? L("nativeVoiceListeningPlaceholder") : L("askAnything"), text: $draft, axis: .vertical)
            .font(DS.Typography.bubble)
            .lineLimit(1 ... 6)
            .focused(focused)
            .submitLabel(.send)
            .onSubmit(onSend)
            // On the field itself: set on the container it would also name the send button.
            .accessibilityIdentifier("chat.input")
            .padding(.leading, DS.Spacing.lg)
            // Always room for the arrow, so the text never reflows as it fades in.
            .padding(.trailing, Self.sendSize + DS.Spacing.sm)
            .padding(.vertical, 11)
            .frame(minHeight: Self.fieldHeight)
            .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: Self.fieldHeight / 2, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Self.fieldHeight / 2, style: .continuous).strokeBorder(DS.Palette.cardStroke, lineWidth: 0.5)
            }
            .overlay(alignment: .bottomTrailing) { sendButton.padding(4) }
    }

    /// Sends what is typed; stops while Omi answers. Hidden while there is nothing to send.
    private var sendButton: some View {
        let shows = chat.isStreaming || !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return Button(action: onSend) {
            Image(systemName: chat.isStreaming ? "stop.fill" : "arrow.up")
                .font(.system(size: chat.isStreaming ? 12 : 15, weight: .bold))
                .foregroundStyle(DS.Palette.onAgent)
                .frame(width: Self.sendSize, height: Self.sendSize)
                .background(DS.Palette.agent.opacity(canSend || chat.isStreaming ? 1 : 0.35), in: Circle())
                .contentTransition(.symbolEffect(.replace))
        }
        .buttonStyle(.plain)
        .disabled(!canSend && !chat.isStreaming)
        .opacity(shows ? 1 : 0)
        .scaleEffect(shows ? 1 : 0.85)
        .allowsHitTesting(shows)
        .accessibilityHidden(!shows)
        .animation(DS.Motion.snappy, value: shows)
        .accessibilityLabel(chat.isStreaming ? L("nativeStopAnswer") : L("nativeSend"))
        .accessibilityIdentifier("chat.send")
    }

    /// The message the question replies to, removable.
    private func replyLine(_ target: ChatMessage) -> some View {
        HStack(spacing: DS.Spacing.sm) {
            QuoteLine(quote: ChatQuote(replyingTo: target))
            Spacer(minLength: 0)
            Button { chat.replyingTo = nil } label: {
                Image(systemName: "xmark.circle.fill").foregroundStyle(DS.Palette.inkTertiary)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(L("nativeChatCancelReply"))
        }
        .padding(.horizontal, DS.Spacing.sm)
        .transition(.move(edge: .bottom).combined(with: .opacity))
        .accessibilityIdentifier("chat.replyingTo")
    }

    /// What the question is about (a conversation or a task), removable.
    private func contextLine(_ context: ChatContext) -> some View {
        HStack {
            Label(context.title, systemImage: context.kind == .conversation ? "bubble.left" : "checklist")
                .lineLimit(1)
            Spacer()
            Button { chat.context = nil } label: { Image(systemName: "xmark.circle.fill") }
                .accessibilityLabel(L("nativeRemoveContext"))
        }
        .font(DS.Typography.caption)
        .foregroundStyle(DS.Palette.agent)
        .padding(.horizontal, DS.Spacing.sm)
        .padding(.top, DS.Spacing.xs)
    }
}

/// Behind the composer: the page color over a blur, so messages scroll on under it and soften
/// instead of showing sharp around its edges; a short fade at its top edge instead of a line.
struct ComposerBackdrop: View {
    private static let fade: CGFloat = 14

    var body: some View {
        ZStack {
            Rectangle().fill(.ultraThinMaterial)
            DS.Palette.background.opacity(0.86)
        }
        .mask {
            VStack(spacing: 0) {
                LinearGradient(colors: [.clear, .black], startPoint: .top, endPoint: .bottom).frame(height: Self.fade)
                Color.black
            }
        }
        .padding(.top, -Self.fade)
        .ignoresSafeArea(.container, edges: .bottom)
        .allowsHitTesting(false)
    }
}

/// The one voice button: tap to dictate into the field (tap again to stop), hold to talk and let
/// go to send. While listening it turns into the stop circle and breathes with the voice.
private struct ComposerMic: View {
    let isDictating: Bool
    let level: Float
    let sendsAfterDictation: Bool
    let isEnabled: Bool
    let onDictate: (_ thenSend: Bool) -> Void
    let onStop: () -> Void
    @State private var holdTask: Task<Void, Never>?
    @State private var isHolding = false
    @State private var isPressed = false

    var body: some View {
        Image(systemName: isDictating ? "stop.fill" : "mic")
            .font(.system(size: isDictating ? 13 : 18, weight: isDictating ? .bold : .regular))
            .foregroundStyle(isDictating ? DS.Palette.onAccent : DS.Palette.ink)
            .frame(width: DS.Size.composer, height: DS.Size.composer)
            .background(isDictating ? DS.Palette.ink : DS.Palette.card, in: Circle())
            .overlay { if !isDictating { Circle().strokeBorder(DS.Palette.cardStroke, lineWidth: 0.5) } }
            .scaleEffect(isDictating ? 1 + CGFloat(min(0.15, level * 3)) : isPressed ? 0.92 : 1)
            .animation(.easeOut(duration: 0.1), value: level)
            .animation(DS.Motion.snappy, value: isPressed)
            .contentTransition(.symbolEffect(.replace))
            .opacity(isEnabled ? 1 : 0.4)
            .contentShape(Circle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in pressBegan() }
                    .onEnded { _ in pressEnded() },
                including: isEnabled ? .all : .none
            )
            .accessibilityElement()
            .accessibilityAddTraits(.isButton)
            .accessibilityLabel(isDictating ? (sendsAfterDictation ? L("nativeSend") : L("nativeStopDictation")) : L("nativeDictate"))
            .accessibilityHint(isDictating ? "" : L("nativeChatHoldToTalk"))
            .accessibilityAction {
                if isDictating { onStop() } else { onDictate(false) }
            }
            .accessibilityIdentifier(isDictating ? "chat.stopDictation" : "chat.dictate")
    }

    private func pressBegan() {
        guard !isPressed else { return }
        isPressed = true
        guard !isDictating else { return }
        holdTask = Task {
            do { try await Task.sleep(for: .milliseconds(350)) } catch { return }
            isHolding = true
            onDictate(true)
        }
    }

    private func pressEnded() {
        isPressed = false
        holdTask?.cancel()
        holdTask = nil
        if isHolding {
            // Letting go ends listening; the question goes out (`sendsAfterDictation`).
            isHolding = false
            onStop()
        } else if isDictating {
            onStop()
        } else {
            onDictate(false)
        }
    }
}
